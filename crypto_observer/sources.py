from __future__ import annotations

import hashlib
import html
import logging
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from .config import EXCLUDED_DOMAINS, SECTION_ORDER, SECTION_QUERIES, TRACKED_SITES, USER_AGENT

LOGGER = logging.getLogger(__name__)
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
BAD_FINAL_HOSTS = (
    "news.google.com",
    "google.com",
    "google-analytics.com",
    "googletagmanager.com",
    "googleapis.com",
    "gstatic.com",
    "googleusercontent.com",
    "schema.org",
    "w3.org",
    "bing.com",
    "msn.com",
    "angular.dev",
)
BAD_PATH_PARTS = (
    "analytics.js",
    "gtag/js",
    "collect?",
    "/rss/articles/",
    "fonts.googleapis",
    "fonts.gstatic",
    ".ttf",
    "/license",
)
NON_NEWS_TEXT_MARKERS = (
    "@font-face",
    "font-family",
    "google sans",
    "fonts.gstatic.com",
    "fonts.googleapis.com",
    "stylesheet",
    "text/css",
    "permission is hereby granted",
    "the software is provided",
    "mit license",
    "copyright (c) 2010-2026 google llc",
    "license • angular",
    "license - angular",
    "angular.dev/license",
    "skip to main content menu",
)
DISCOVERY_SOURCES = {"Bing News", "Google News", "GDELT"}
MIN_ARTICLE_TEXT_CHARS = 900
CONTENT_TERMS = (
    "crypto", "bitcoin", "ethereum", "stablecoin", "token", "tokenization", "tokenisation", "blockchain", "defi", "web3", "digital asset", "layer 2", "layer2", "wallet", "protocol", "regulation", "sec", "cftc", "sfc", "hkma", "mica", "bank of england", "fca", "rwa", "smart contract", "staking", "rollup", "chain", "exchange", "market", "ether", "xrp", "solana", "treasury", "securities", "futures", "tokenized", "tokenised"
)
SPECIAL_SOURCE_NAMES = {
    "financefeeds.com": "FinanceFeeds",
    "coindesk.com": "CoinDesk",
    "cointelegraph.com": "Cointelegraph",
    "theblock.co": "The Block",
    "blockworks.co": "Blockworks",
    "decrypt.co": "Decrypt",
    "cryptoslate.com": "CryptoSlate",
    "thedefiant.io": "The Defiant",
    "glassnode.com": "Glassnode",
    "messari.io": "Messari",
    "sec.gov": "SEC",
    "cftc.gov": "CFTC",
    "treasury.gov": "US Treasury",
    "federalreserve.gov": "Federal Reserve",
    "sfc.hk": "Hong Kong SFC",
    "hkma.gov.hk": "Hong Kong HKMA",
    "bis.org": "BIS",
    "bullish.com": "Bullish",
    "cmegroup.com": "CME Group",
    "backpack.exchange": "Backpack",
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
    if value is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(str(value))).strip()


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
    return dt is None or start <= dt <= end


def host(url: str) -> str:
    return urllib.parse.urlsplit(url or "").netloc.lower().replace("www.", "")


def source_name_from_url(url: str, html_text: str = "") -> str:
    soup = BeautifulSoup(html_text or "", "html.parser")
    for selector, attr in (
        ('meta[property="og:site_name"]', "content"),
        ('meta[name="application-name"]', "content"),
        ('meta[name="twitter:site"]', "content"),
    ):
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
    if low.count("https://") > 12 and len(text) < 3000:
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


def parse_rss(xml_text: str, query: str, start: datetime, end: datetime, source_name: str, source_url: str, section_hint: str) -> list[RawItem]:
    out: list[RawItem] = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return out
    for entry in root.findall("./channel/item"):
        title = strip_html(entry.findtext("title") or "")
        link = norm_url(entry.findtext("link") or "")
        summary = strip_html(entry.findtext("description") or "")
        pub_date = entry.findtext("pubDate") or ""
        source_el = entry.find("source")
        publisher = strip_html(source_el.text if source_el is not None else "")
        source_attr_url = norm_url(source_el.attrib.get("url", "")) if source_el is not None else ""
        published = ""
        if pub_date:
            try:
                published = parsedate_to_datetime(pub_date).astimezone(BEIJING_TZ).isoformat()
            except Exception:
                dt = parse_datetime(pub_date)
                published = dt.isoformat() if dt else pub_date
        if not title or not link or not in_window(published, start, end):
            continue
        if is_chinese_item(title, summary, link):
            continue
        name = publisher or source_name
        item = RawItem(title=title, url=link, source_name=name, source_url=source_attr_url or source_url, published_at=published, summary=summary, section_hint=section_hint, query=query)
        if is_google_news_url(link):
            item.google_wrapper_url = link
        out.append(item)
    return out


def fetch_google(query: str, start: datetime, end: datetime, section_hint: str) -> list[RawItem]:
    try:
        text = request_text(google_news_url(query, (end - start).days or 1), 15)
        return parse_rss(text, query, start, end, "Google News", "https://news.google.com/", section_hint)
    except Exception as exc:
        LOGGER.debug("google news failed: %s", exc)
        return []


def fetch_bing(query: str, start: datetime, end: datetime, section_hint: str) -> list[RawItem]:
    try:
        text = request_text(bing_news_url(query), 15)
        return parse_rss(text, query, start, end, "Bing News", "https://www.bing.com/news/search", section_hint)
    except Exception as exc:
        LOGGER.debug("bing news failed: %s", exc)
        return []


def fetch_gdelt(query: str, start: datetime, end: datetime, section_hint: str) -> list[RawItem]:
    params = urllib.parse.urlencode({
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": "50",
        "sort": "hybridrel",
        "startdatetime": start.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S"),
        "enddatetime": end.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S"),
    })
    url = f"https://api.gdeltproject.org/api/v2/doc/doc?{params}"
    try:
        data = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=15).json()
    except Exception as exc:
        LOGGER.debug("gdelt failed: %s", exc)
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
    for selector in ("article", "main", "[role=main]", ".article", ".post", ".entry-content", ".story", ".content"):
        for node in soup.select(selector):
            text = norm_text(node.get_text(" "))
            if len(text) > 500:
                candidates.append(text)
    body = norm_text(soup.get_text(" "))
    if len(body) > 500:
        candidates.append(body)
    candidates.sort(key=len, reverse=True)
    return candidates


def _extract_direct_urls_from_html(html_text: str) -> list[str]:
    decoded = html.unescape(html_text or "")
    found = re.findall(r"https?://[^\s\"'<>\\]+", decoded)
    out: list[str] = []
    for raw in found:
        url = norm_url(urllib.parse.unquote(raw).rstrip("),.;"))
        if not is_final_url_allowed(url):
            continue
        if url not in out:
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
        text = next(iter(_best_article_candidates(r.text)), "")
        publisher = source_name_from_url(final_url, r.text)
        if not is_article_text_allowed("", text, final_url):
            return "", final_url, publisher
        return text[:9000], final_url, publisher
    except Exception as exc:
        LOGGER.debug("article fetch failed for %s: %s", url, exc)
        return "", url, ""


def _prefer_item(current: RawItem, candidate: RawItem) -> RawItem:
    current_good = is_final_url_allowed(current.url)
    candidate_good = is_final_url_allowed(candidate.url)
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
    by_url: dict[str, RawItem] = {}
    by_title: dict[str, RawItem] = {}
    for item in items:
        key = item.stable_key()
        tkey = title_key(item.title)
        if tkey and tkey in by_title:
            merged = _prefer_item(by_title[tkey], item)
            by_title[tkey] = merged
            by_url[merged.stable_key()] = merged
            continue
        if key in by_url:
            by_url[key] = _prefer_item(by_url[key], item)
            continue
        by_url[key] = item
        if tkey:
            by_title[tkey] = item
    seen: set[int] = set()
    out: list[RawItem] = []
    for item in by_url.values():
        if id(item) not in seen:
            seen.add(id(item))
            out.append(item)
    return out


def enrich_articles(items: list[RawItem], limit: int = 120) -> list[RawItem]:
    enriched: list[RawItem] = []
    for idx, item in enumerate(items):
        if idx < limit:
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
        if is_article_text_allowed(item.title, item.article_text or "", item.url):
            enriched.append(item)
        if idx < limit:
            time.sleep(0.03)
    return enriched


def collect(days: int = 3, max_items: int = 360) -> tuple[list[RawItem], list[str]]:
    start, end = window(days)
    items: list[RawItem] = []
    errors: list[str] = []
    queries: list[tuple[str, str]] = []
    for section in SECTION_ORDER:
        for q in SECTION_QUERIES.get(section, ()):
            queries.append((section, q))
    for _, site_query in TRACKED_SITES.items():
        queries.append(("", site_query))
    for section, query in queries:
        before = len(items)
        items.extend(fetch_bing(query, start, end, section))
        items.extend(fetch_gdelt(query, start, end, section))
        items.extend(fetch_google(query, start, end, section))
        if len(items) == before:
            errors.append(f"no candidates for query: {query}")
        time.sleep(0.05)
    final = dedupe(items)
    final.sort(key=lambda x: parse_datetime(x.published_at) or start, reverse=True)
    enriched = enrich_articles(final[:max_items])
    if len(enriched) < 20:
        errors.append(f"only {len(enriched)} verified source articles with reachable original URLs and body text")
    return enriched[:max_items], errors[:80]
