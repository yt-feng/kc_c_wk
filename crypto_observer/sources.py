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

    def stable_key(self) -> str:
        raw = f"{norm_text(self.title)}|{norm_url(self.url)}"
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
    return urllib.parse.urlsplit(url).netloc.lower().replace("www.", "")


def is_chinese_item(title: str, summary: str, url: str) -> bool:
    if CHINESE_RE.search(title or "") or CHINESE_RE.search(summary or ""):
        return True
    h = host(url)
    if h.endswith(".cn"):
        return True
    full = url.lower()
    return any(domain in h or domain in full for domain in EXCLUDED_DOMAINS)


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
        out.append(RawItem(title=title, url=link, source_name=name, source_url=source_attr_url or source_url, published_at=published, summary=summary, section_hint=section_hint, query=query))
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
        domain = article.get("domain") or host(link)
        dt = parse_datetime(article.get("seendate"))
        published = dt.isoformat() if dt else ""
        if title and link and in_window(published, start, end) and not is_chinese_item(title, domain, link):
            out.append(RawItem(title, link, domain, "https://www.gdeltproject.org/", published, domain, section_hint, query))
    return out


def _best_article_candidates(html_text: str) -> list[str]:
    soup = BeautifulSoup(html_text or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "footer", "header", "nav", "aside"]):
        tag.decompose()
    candidates = []
    for selector in ("article", "main", "[role=main]", ".article", ".post", ".entry-content", ".story", ".content"):
        for node in soup.select(selector):
            text = norm_text(node.get_text(" "))
            if len(text) > 300:
                candidates.append(text)
    body = norm_text(soup.get_text(" "))
    if len(body) > 300:
        candidates.append(body)
    candidates.sort(key=len, reverse=True)
    return candidates


def fetch_article_text(url: str, timeout: int = 18) -> tuple[str, str]:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"}, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        final_url = norm_url(r.url)
        text = next(iter(_best_article_candidates(r.text)), "")
        if "news.google.com" in host(url) and len(text) < 500:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = urllib.parse.urljoin(final_url, a["href"])
                if href.startswith("http") and "news.google.com" not in host(href):
                    return fetch_article_text(href, timeout=timeout)
        return text[:6000], final_url
    except Exception as exc:
        LOGGER.debug("article fetch failed for %s: %s", url, exc)
        return "", url


def enrich_articles(items: list[RawItem], limit: int = 80) -> list[RawItem]:
    enriched: list[RawItem] = []
    for idx, item in enumerate(items):
        if idx < limit:
            text, final_url = fetch_article_text(item.url)
            if text and not is_chinese_item(item.title, text[:500], final_url):
                item.article_text = text
                item.url = final_url or item.url
        enriched.append(item)
        if idx < limit:
            time.sleep(0.03)
    return enriched


def dedupe(items: Iterable[RawItem]) -> list[RawItem]:
    seen: set[str] = set()
    out: list[RawItem] = []
    for item in items:
        key = item.stable_key()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def collect(days: int = 3, max_items: int = 360) -> tuple[list[RawItem], list[str]]:
    start, end = window(days)
    items: list[RawItem] = []
    errors: list[str] = []
    queries: list[tuple[str, str]] = []
    for section in SECTION_ORDER:
        for q in SECTION_QUERIES.get(section, ()):
            queries.append((section, q))
    for name, site_query in TRACKED_SITES.items():
        queries.append(("", site_query))
    for section, query in queries:
        before = len(items)
        items.extend(fetch_google(query, start, end, section))
        items.extend(fetch_bing(query, start, end, section))
        items.extend(fetch_gdelt(query, start, end, section))
        if len(items) == before:
            errors.append(f"no candidates for query: {query}")
        time.sleep(0.05)
    final = dedupe(items)
    final.sort(key=lambda x: parse_datetime(x.published_at) or start, reverse=True)
    return enrich_articles(final[:max_items]), errors[:80]
