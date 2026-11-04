from __future__ import annotations

import hashlib
import html
import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from .config import DIRECT_FEEDS, EXCLUDED_DOMAINS, SECTION_ORDER, SECTION_QUERIES, TRACKED_SITES, USER_AGENT

LOGGER = logging.getLogger(__name__)
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
BAD_FINAL_HOSTS = (
    "news.google.com", "google.com", "google-analytics.com", "googletagmanager.com", "googleapis.com", "gstatic.com", "googleusercontent.com", "schema.org", "w3.org", "bing.com", "msn.com", "angular.dev",
)
BAD_PATH_PARTS = ("analytics.js", "gtag/js", "collect?", "/rss/articles/", "fonts.googleapis", "fonts.gstatic", ".ttf", "/license")
NON_NEWS_TEXT_MARKERS = (
    "@font-face", "font-family", "google sans", "fonts.gstatic.com", "fonts.googleapis.com", "stylesheet", "text/css", "permission is hereby granted", "the software is provided", "mit license", "copyright (c) 2010-2026 google llc", "license • angular", "license - angular", "angular.dev/license", "skip to main content menu", "enable javascript", "accept cookies to continue",
)
DISCOVERY_SOURCES = {"Bing News", "Google News", "GDELT"}
MIN_ARTICLE_TEXT_CHARS = 700
DISCOVERY_WORKERS = 6
ARTICLE_WORKERS = 8
NON_ARTICLE_PATH_RE = re.compile(r"/(?:about(?:-us)?|team|leadership|authors?)(?:/|$)", re.I)
DIRECT_FEED_TERMS = ("crypto", "bitcoin", "ethereum", "stablecoin", "blockchain", "tokeniz", "tokenis", "digital asset", "defi", "web3", "ether", "xrp", "solana", "rwa")
CONTENT_TERMS = (
    "crypto", "bitcoin", "ethereum", "stablecoin", "token", "tokenization", "tokenisation", "blockchain", "defi", "web3", "digital asset", "layer 2", "layer2", "wallet", "protocol", "regulation", "sec", "cftc", "sfc", "hkma", "mica", "bank of england", "fca", "rwa", "smart contract", "staking", "rollup", "chain", "exchange", "market", "ether", "xrp", "solana", "treasury", "securities", "futures", "tokenized", "tokenised", "prediction market", "casp",
)
SPECIAL_SOURCE_NAMES = {
    "financefeeds.com": "FinanceFeeds", "coindesk.com": "CoinDesk", "cointelegraph.com": "Cointelegraph", "theblock.co": "The Block", "blockworks.co": "Blockworks", "decrypt.co": "Decrypt", "cryptoslate.com": "CryptoSlate", "thedefiant.io": "The Defiant", "ledgerinsights.com": "Ledger Insights", "glassnode.com": "Glassnode", "messari.io": "Messari", "sec.gov": "SEC", "cftc.gov": "CFTC", "treasury.gov": "US Treasury", "federalreserve.gov": "Federal Reserve", "sfc.hk": "Hong Kong SFC", "hkma.gov.hk": "Hong Kong HKMA", "bis.org": "BIS", "esma.europa.eu": "ESMA", "fca.org.uk": "FCA", "bankofengland.co.uk": "Bank of England", "bullish.com": "Bullish", "cmegroup.com": "CME Group", "backpack.exchange": "Backpack",
}


@dataclass
class RawItem:
    title: str
    url: str
    source_name: str
    source_url: str
    published_at: str
    summary: str = ""
    section_hint: str = ""
    query: str = ""
    article_text: str = ""
    google_wrapper_url: str = ""

    def stable_key(self) -> str:
        raw = f"{title_key(self.title)}|{norm_url(self.url)}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def window(days: int) -> tuple[datetime, datetime]:
    end = datetime.now(BEIJING_TZ).replace(microsecond=0)
    return end - timedelta(days=days), end


def norm_text(value: object) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def norm_url(value: str) -> str:
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(value.strip())
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path, urllib.parse.urlencode(query), ""))


def title_key(value: str) -> str:
    text = norm_text(value).lower()
    text = re.sub(r"\s+-\s+[^-]{2,60}$", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)[:180]


def strip_html(value: str | None) -> str:
    return norm_text(BeautifulSoup(value or "", "html.parser").get_text(" "))


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if re.fullmatch(r"\d{14}", value):
            dt = datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        else:
            dt = date_parser.parse(value)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BEIJING_TZ)


def in_window(date_value: str | None, start: datetime, end: datetime) -> bool:
    dt = parse_datetime(date_value)
    return dt is not None and start <= dt <= end


def host(url: str) -> str:
    return urllib.parse.urlsplit(url or "").netloc.lower().replace("www.", "")


def source_name_from_url(url: str, html_text: str = "") -> str:
    soup = BeautifulSoup(html_text or "", "html.parser")
    for selector, attr in (('meta[property="og:site_name"]', "content"), ('meta[name="application-name"]', "content"), ('meta[name="twitter:site"]', "content")):
        node = soup.select_one(selector)
        if node and node.get(attr):
            value = norm_text(node.get(attr)).lstrip("@")
            if value and "google" not in value.lower() and value not in DISCOVERY_SOURCES:
                return value
    h = host(url)
    if h in SPECIAL_SOURCE_NAMES:
        return SPECIAL_SOURCE_NAMES[h]
    parts = h.split(".")
    core = parts[-2] if len(parts) >= 2 else h
    return core.replace("-", " ").title() or "Unknown Source"


def is_google_news_url(url: str) -> bool:
    return host(url).endswith("news.google.com")


def is_final_url_allowed(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url or "")
    h = parsed.netloc.lower().replace("www.", "")
    full = (url or "").lower()
    if parsed.scheme not in ("http", "https") or not h:
        return False
    if any(h == bad or h.endswith("." + bad) for bad in BAD_FINAL_HOSTS):
        return False
    if any(part in full for part in BAD_PATH_PARTS):
        return False
    if NON_ARTICLE_PATH_RE.search(parsed.path):
        return False
    if any(domain in h or domain in full for domain in EXCLUDED_DOMAINS):
        return False
    return True


def is_chinese_item(title: str, summary: str, url: str) -> bool:
    if CHINESE_RE.search(title or "") or CHINESE_RE.search(summary or ""):
        return True
    h = host(url)
    if h.endswith(".cn"):
        return True
    full = url.lower()
    return any(domain in h or domain in full for domain in EXCLUDED_DOMAINS)


def is_article_text_allowed(title: str, text: str, url: str) -> bool:
    low = f"{title} {text} {url}".lower()
    if not is_final_url_allowed(url):
        return False
    if len(text or "") < MIN_ARTICLE_TEXT_CHARS:
        return False
    if any(marker in low for marker in NON_NEWS_TEXT_MARKERS):
        return False
    if low.count("https://") > 14 and len(text) < 3200:
        return False
    if not any(term in low for term in CONTENT_TERMS):
        return False
    if "compound" in low and "angular" in low:
        return False
    return True


def request_text(url: str, timeout: int = 20) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/xml,text/html,application/json,*/*"}, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text


def google_news_url(query: str, days: int) -> str:
    q = f"{query} when:{max(days, 1)}d"
    params = urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return f"https://news.google.com/rss/search?{params}"


def bing_news_url(query: str) -> str:
    return "https://www.bing.com/news/search?" + urllib.parse.urlencode({"q": query, "format": "rss", "mkt": "en-US", "setlang": "en"})


def _feed_child(entry: ET.Element, *names: str) -> ET.Element | None:
    return next((node for node in entry if node.tag.rsplit("}", 1)[-1] in names), None)


def _feed_text(entry: ET.Element, *names: str) -> str:
    node = _feed_child(entry, *names)
    return " ".join(node.itertext()).strip() if node is not None else ""


def _publisher_link(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if host(value) == "bing.com" and parsed.path.lower() == "/news/apiclick.aspx":
        candidate = urllib.parse.parse_qs(parsed.query).get("url", [""])[0]
        if is_final_url_allowed(candidate):
            return norm_url(candidate)
    return value


def parse_rss(xml_text: str, query: str, start: datetime, end: datetime, source_name: str, source_url: str, section_hint: str) -> list[RawItem]:
    out: list[RawItem] = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError as exc:
        LOGGER.warning("Invalid feed from %s: %s", source_name, exc)
        return out
    for entry in root.iter():
        if entry.tag.rsplit("}", 1)[-1] not in ("item", "entry"):
            continue
        title = strip_html(_feed_text(entry, "title"))
        link = _feed_text(entry, "link")
        for node in entry:
            if node.tag.rsplit("}", 1)[-1] == "link" and node.get("rel", "alternate") == "alternate" and node.get("href"):
                link = node.get("href", "")
                break
        link = _publisher_link(norm_url(urllib.parse.urljoin(source_url, link))) if link else ""
        summary = strip_html(_feed_text(entry, "description", "summary"))
        # Atom updated is a modification time, not proof of a new publication.
        pub_date = _feed_text(entry, "pubDate") or _feed_text(entry, "published") or _feed_text(entry, "date")
        source_el = _feed_child(entry, "source")
        publisher = strip_html(_feed_text(source_el, "title") or source_el.text or "") if source_el is not None else ""
        source_attr_url = norm_url(source_el.attrib.get("url", "")) if source_el is not None else ""
        dt = parse_datetime(pub_date)
        published = dt.isoformat() if dt else ""
        if not title or not link or not in_window(published, start, end):
            continue
        if is_chinese_item(title, summary, link):
            continue
        name = publisher or source_name
        item = RawItem(title=title, url=link, source_name=name, source_url=source_attr_url or source_url, published_at=published, summary=summary, section_hint=section_hint, query=query)
        # Only a publisher's own full-content field can provide article text;
        # search descriptions and cross-domain syndicated content cannot.
        content = strip_html(_feed_text(entry, "encoded", "content"))
        if host(source_url) == host(link) and is_article_text_allowed(title, content, link) and not is_chinese_item(title, content, link):
            item.article_text = content[:14000]
        if is_google_news_url(link):
            item.google_wrapper_url = link
        out.append(item)
    return out


def fetch_direct_feed(name: str, url: str, start: datetime, end: datetime) -> list[RawItem]:
    try:
        items = parse_rss(request_text(url, 20), "publisher feed", start, end, name, url, "")
        return [item for item in items if is_final_url_allowed(item.url) and any(term in f"{item.title} {item.summary} {item.article_text}".lower() for term in DIRECT_FEED_TERMS)]
    except Exception as exc:
        LOGGER.warning("Publisher feed failed for %s: %s", name, exc)
        return []


def fetch_google(query: str, start: datetime, end: datetime, section_hint: str) -> list[RawItem]:
    try:
        return parse_rss(request_text(google_news_url(query, (end - start).days or 1), 15), query, start, end, "Google News", "https://news.google.com/", section_hint)
    except Exception as exc:
        LOGGER.warning("Google News discovery failed for %r: %s", query, exc)
        return []


def fetch_bing(query: str, start: datetime, end: datetime, section_hint: str) -> list[RawItem]:
    try:
        return parse_rss(request_text(bing_news_url(query), 15), query, start, end, "Bing News", "https://www.bing.com/news/search", section_hint)
    except Exception as exc:
        LOGGER.warning("Bing News discovery failed for %r: %s", query, exc)
        return []


def fetch_gdelt(query: str, start: datetime, end: datetime, section_hint: str) -> list[RawItem]:
    params = urllib.parse.urlencode({"query": query, "mode": "artlist", "format": "json", "maxrecords": "80", "sort": "hybridrel", "startdatetime": start.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S"), "enddatetime": end.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")})
    url = f"https://api.gdeltproject.org/api/v2/doc/doc?{params}"
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        LOGGER.warning("GDELT discovery failed for %r: %s", query, exc)
        return []
    out: list[RawItem] = []
    for article in data.get("articles") or []:
        title = strip_html(article.get("title") or "")
        link = norm_url(article.get("url") or "")
        domain = article.get("domain") or source_name_from_url(link)
        dt = parse_datetime(article.get("seendate"))
        published = dt.isoformat() if dt else ""
        if title and link and in_window(published, start, end) and not is_chinese_item(title, domain, link):
            out.append(RawItem(title, link, domain, "https://www.gdeltproject.org/", published, domain, section_hint, query))
    return out


def _best_article_candidates(html_text: str) -> list[str]:
    soup = BeautifulSoup(html_text or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "footer", "header", "nav", "aside", "form"]):
        tag.decompose()
    candidates: list[str] = []
    seen: set[str] = set()
    # Prefer article bodies to the full page, which often contains unrelated
    # cookie, navigation, or licence text rejected by the content validator.
    for selector in ("[itemprop=articleBody]", ".entry-content", ".article-content", ".post-content", ".article-body", ".story-body", "article", "main", "[role=main]", ".article", ".post", ".story", ".content"):
        matches: list[str] = []
        for node in soup.select(selector):
            text = norm_text(node.get_text(" "))
            if len(text) > 500 and text not in seen:
                matches.append(text)
                seen.add(text)
        candidates.extend(sorted(matches, key=len, reverse=True))
    body = norm_text(soup.get_text(" "))
    if len(body) > 500 and body not in seen:
        candidates.append(body)
    return candidates


def _extract_direct_urls_from_html(html_text: str) -> list[str]:
    decoded = html.unescape(html_text or "")
    found = re.findall(r"https?://[^\s\"'<>\\]+", decoded)
    out: list[str] = []
    for raw in found:
        url = norm_url(urllib.parse.unquote(raw).rstrip("),.;"))
        if is_final_url_allowed(url) and url not in out:
            out.append(url)
    return out


def fetch_article_text(url: str, timeout: int = 18) -> tuple[str, str, str]:
    try:
        if not url.startswith("http"):
            return "", url, ""
        r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"}, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        final_url = norm_url(r.url)
        content_type = r.headers.get("content-type", "").lower()
        if "text/css" in content_type or "font" in content_type:
            return "", final_url, ""
        if is_google_news_url(url):
            for candidate in _extract_direct_urls_from_html(r.text):
                if is_final_url_allowed(candidate):
                    return fetch_article_text(candidate, timeout=timeout)
            return "", url, ""
        if not is_final_url_allowed(final_url):
            return "", final_url, ""
        text = next((candidate for candidate in _best_article_candidates(r.text) if is_article_text_allowed("", candidate, final_url)), "")
        publisher = source_name_from_url(final_url, r.text)
        return text[:14000], final_url, publisher
    except Exception as exc:
        LOGGER.debug("article fetch failed for %s: %s", url, exc)
        return "", url, ""


def _prefer_item(current: RawItem, candidate: RawItem) -> RawItem:
    current_good, candidate_good = is_final_url_allowed(current.url), is_final_url_allowed(candidate.url)
    if not current_good and candidate_good:
        candidate.google_wrapper_url = current.google_wrapper_url or current.url
        if not candidate.summary and current.summary:
            candidate.summary = current.summary
        return candidate
    if current_good and not candidate_good:
        current.google_wrapper_url = current.google_wrapper_url or candidate.url
        return current
    if len(candidate.summary or "") > len(current.summary or ""):
        current.summary = candidate.summary
    if not current.article_text and candidate.article_text:
        current.article_text = candidate.article_text
    return current


def dedupe(items: Iterable[RawItem]) -> list[RawItem]:
    by_url: dict[str, int] = {}
    by_title: dict[str, int] = {}
    out: list[RawItem] = []
    for item in items:
        key, tkey = norm_url(item.url), title_key(item.title)
        index = by_url.get(key)
        if index is None and tkey:
            index = by_title.get(tkey)
        if index is None:
            index = len(out)
            out.append(item)
        else:
            out[index] = _prefer_item(out[index], item)
        by_url[key] = index
        by_url[norm_url(out[index].url)] = index
        if tkey:
            by_title[tkey] = index
    return out


def enrich_articles(items: list[RawItem], limit: int = 240) -> list[RawItem]:
    def enrich_one(pair: tuple[int, RawItem]) -> RawItem | None:
        idx, item = pair
        if idx < limit and is_final_url_allowed(item.url):
            text, final_url, publisher = fetch_article_text(item.url)
            if final_url and is_final_url_allowed(final_url):
                if item.url != final_url:
                    item.google_wrapper_url = item.google_wrapper_url or item.url
                item.url = final_url
                item.source_url = f"https://{host(final_url)}/"
            if publisher:
                item.source_name = publisher
            elif item.source_name in DISCOVERY_SOURCES:
                item.source_name = source_name_from_url(item.url)
            if text and is_article_text_allowed(item.title, text, item.url) and not is_chinese_item(item.title, text[:500], item.url):
                item.article_text = text
        if item.source_name in DISCOVERY_SOURCES:
            item.source_name = source_name_from_url(item.url)
        if is_article_text_allowed(item.title, item.article_text or "", item.url) and not is_chinese_item(item.title, item.article_text or "", item.url):
            return item
        return None

    with ThreadPoolExecutor(max_workers=ARTICLE_WORKERS) as executor:
        return [item for item in executor.map(enrich_one, enumerate(items)) if item is not None]


def _discover_query(task: tuple[str, str], start: datetime, end: datetime) -> tuple[str, list[tuple[str, list[RawItem]]]]:
    section, query = task
    return query, [
        ("Bing News", fetch_bing(query, start, end, section)),
        ("GDELT", fetch_gdelt(query, start, end, section)),
        ("Google News", fetch_google(query, start, end, section)),
    ]


def collect(days: int = 7, max_items: int = 500) -> tuple[list[RawItem], list[str]]:
    start, end = window(days)
    items: list[RawItem] = []
    errors: list[str] = []
    counts: Counter[str] = Counter()
    queries: list[tuple[str, str]] = []
    for section in SECTION_ORDER:
        for q in SECTION_QUERIES.get(section, ()): queries.append((section, q))
    for _, site_query in TRACKED_SITES.items(): queries.append(("", site_query))
    with ThreadPoolExecutor(max_workers=DISCOVERY_WORKERS) as executor:
        feed_results = executor.map(lambda feed: (feed[0], fetch_direct_feed(feed[0], feed[1], start, end)), DIRECT_FEEDS.items())
        for name, discovered in feed_results:
            counts[f"publisher:{name}"] += len(discovered)
            items.extend(discovered)
        for query, results in executor.map(lambda task: _discover_query(task, start, end), queries):
            for name, discovered in results:
                counts[name] += len(discovered)
                items.extend(discovered)
            if not any(discovered for _, discovered in results):
                errors.append(f"no candidates for query: {query}")
    final = dedupe(items)
    LOGGER.info("Discovery counts by source: %s", dict(counts))
    LOGGER.info("Discovery candidates: raw=%d deduplicated=%d wrappers=%d publisher_bodies=%d", len(items), len(final), sum(is_google_news_url(item.url) for item in final), sum(bool(item.article_text) for item in final))
    # Spend body requests on original publishers; unresolved Google wrappers
    # otherwise occupy the entire recent-item limit and yield no article text.
    wrappers = [item for item in final if not is_final_url_allowed(item.url)]
    final = [item for item in final if is_final_url_allowed(item.url)]
    final.sort(key=lambda x: parse_datetime(x.published_at) or start, reverse=True)
    final.extend(wrappers)
    attempted = sum(is_final_url_allowed(item.url) for item in final[:min(max_items, 260)])
    enriched = enrich_articles(final[:max_items], limit=min(max_items, 260))
    summary = f"collection stages: discovered={len(items)}, deduplicated={len(final)}, body_attempted={attempted}, verified={len(enriched)}; sources={dict(counts)}"
    LOGGER.info(summary)
    errors.insert(0, summary)
    if len(enriched) < 12:
        errors.append(f"only {len(enriched)} verified source articles with reachable original URLs and body text")
    return enriched[:max_items], errors[:80]
