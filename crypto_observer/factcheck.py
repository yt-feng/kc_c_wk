from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from .config import HK_TERMS, MAX_NEWS_AGE_DAYS, SECTION_COUNTS, US_TERMS
from .sources import is_chinese_item, is_final_url_allowed, parse_datetime, title_key
from .text_utils import has_half_width_quotes

BAD_BODY_TERMS = (
    "permission is hereby granted",
    "the software is provided",
    "mit license",
    "copyright (c) 2010-2026 google llc",
    "license • angular",
    "license - angular",
    "angular.dev/license",
    "@font-face",
    "font-family",
    "fonts.gstatic.com",
    "fonts.googleapis.com",
    "stylesheet",
)
DISCOVERY_SOURCE_NAMES = {"Bing News", "Google News", "GDELT"}
UNSUPPORTED_EDITORIAL_PHRASES = (
    "未决问题",
    "整体来看",
    "这一立法动向反映出",
    "从更广阔的市场视角看",
    "未来数周",
    "仍需后续观察",
    "正成为不可忽视",
    "这至少表明",
    "可能引发管辖权重叠",
    "将面临更严格的合规要求",
)
ATTRIBUTION_RISK_PHRASES = ("业内人士指出", "分析师认为", "分析师指出", "市场观察人士", "投资者认为")
UNSUPPORTED_QUESTION_PHRASES = ("能否", "是否能够", "是否会", "会否", "是否可以")


@dataclass
class FactCheckResult:
    ok: bool
    errors: list[str]
    warnings: list[str]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _host(url: str) -> str:
    return urlsplit(url or "").netloc.lower().replace("www.", "")


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    low = (text or "").lower()
    return any(term.lower() in low for term in terms)


def _region(row: dict[str, object]) -> str:
    text = " ".join(str(row.get(k, "")) for k in ("region", "title_cn", "source_title", "lead_cn", "source_name", "url"))
    if _contains_any(text, US_TERMS):
        return "美国"
    if _contains_any(text, HK_TERMS):
        return "香港"
    if any(x in text.lower() for x in ("eu", "europe", "esma", "mica", "欧盟")):
        return "欧盟"
    return str(row.get("region") or "其他")


def _has_bad_title_punct(title: str) -> bool:
    return any(ch in title for ch in ("，", ",", "；", ";", "：", ":", "—", "–"))


def _has_relative_time(text: str) -> bool:
    return any(x in text for x in ("今年", "去年", "明年", "本周", "上周", "下周", "周五", "近日", "日前", "最近"))


def _min_body_chars(section: str) -> int:
    return 500 if section == "意见领袖" else 650


def _min_body_paragraphs(section: str) -> int:
    return 4 if section == "意见领袖" else 5


def _body_fingerprint(text: str) -> str:
    compact = re.sub(r"\W+", "", (text or "").lower())[:1800]
    return hashlib.sha1(compact.encode("utf-8")).hexdigest() if compact else ""


def _has_unsupported_editorial_text(text: str) -> bool:
    return any(phrase in text for phrase in UNSUPPORTED_EDITORIAL_PHRASES)


def _has_attribution_risk(text: str) -> bool:
    return any(phrase in text for phrase in ATTRIBUTION_RISK_PHRASES)


def _has_question_risk(text: str) -> bool:
    return any(phrase in text for phrase in UNSUPPORTED_QUESTION_PHRASES)


def check_report(report: dict[str, object], start: datetime, end: datetime) -> FactCheckResult:
    items = report.get("items") or []
    if not isinstance(items, list):
        return FactCheckResult(False, ["report.items is not a list"], [])

    errors: list[str] = []
    warnings: list[str] = []
    counts = Counter(str(row.get("section", "")) for row in items if isinstance(row, dict))

    for section, expected in SECTION_COUNTS.items():
        actual = counts.get(section, 0)
        if actual != expected:
            errors.append(f"{section} requires {expected} items, got {actual}")

    policy_rows = [row for row in items if isinstance(row, dict) and row.get("section") == "政策风向"]
    if policy_rows and not any(_contains_any(" ".join(str(v) for v in row.values()), US_TERMS) for row in policy_rows):
        errors.append("政策风向 requires at least one US-related item")
    policy_regions = [_region(row) for row in policy_rows]
    if len(policy_regions) >= 3 and len(set(policy_regions)) == 1:
        warnings.append(f"政策风向 3 篇均来自同一地区：{policy_regions[0]}，建议加入美国或香港以外的正式监管动向")
    if policy_rows and not any(r in ("美国", "香港") for r in policy_regions):
        warnings.append("政策风向未覆盖美国或香港，建议优先补充美国、香港监管动向")

    hosts: list[str] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    seen_bodies: set[str] = set()
    oldest_allowed = end - timedelta(days=MAX_NEWS_AGE_DAYS)
    for idx, row in enumerate(items, start=1):
        if not isinstance(row, dict):
            errors.append(f"item {idx} is not an object")
            continue
        section = str(row.get("section") or "")
        title = str(row.get("title_cn") or "")
        source_title = str(row.get("source_title") or "")
        source_name = str(row.get("source_name") or "")
        url = str(row.get("url") or "")
        published_at = str(row.get("published_at") or "")
        paragraphs = row.get("body_paragraphs") or []
        if not isinstance(paragraphs, list):
            paragraphs = []
        body = " ".join(str(x) for x in [row.get("lead_cn", ""), *paragraphs])
        points = row.get("key_points") or []
        all_cn_text = " ".join([title, body, " ".join(str(x) for x in points)])
        low = " ".join([title, source_title, source_name, url, body]).lower()

        url_key = url.strip().lower()
        if url_key in seen_urls:
            errors.append(f"item {idx} duplicates URL already used: {url}")
        seen_urls.add(url_key)
        title_fp = title_key(source_title or title)
        if title_fp and title_fp in seen_titles:
            errors.append(f"item {idx} duplicates title already used: {source_title or title}")
        if title_fp:
            seen_titles.add(title_fp)
        body_fp = _body_fingerprint(body)
        if body_fp and body_fp in seen_bodies:
            errors.append(f"item {idx} duplicates body text already used")
        if body_fp:
            seen_bodies.add(body_fp)

        if source_name in DISCOVERY_SOURCE_NAMES:
            errors.append(f"item {idx} uses discovery source instead of publisher: {source_name}")
        if any(term in low for term in BAD_BODY_TERMS):
            errors.append(f"item {idx} appears to use license/CSS/non-news content")
        if _has_unsupported_editorial_text(all_cn_text):
            errors.append(f"item {idx} contains unsupported editorial-summary phrasing; remove source-external commentary")
        if _has_attribution_risk(all_cn_text):
            warnings.append(f"item {idx} contains generic attribution wording; verify the source explicitly supports it")
        if _has_question_risk(all_cn_text):
            warnings.append(f"item {idx} contains question-style future/unknown wording; ensure the source explicitly raises it")
        if not (url.startswith("http://") or url.startswith("https://")):
            errors.append(f"item {idx} has invalid url: {url}")
        if not is_final_url_allowed(url):
            errors.append(f"item {idx} has blocked or non-publisher url: {url}")
        h = _host(url)
        if h:
            hosts.append(h)
        if is_chinese_item(source_title, source_name, url):
            errors.append(f"item {idx} appears to use a Chinese source")
        dt = parse_datetime(published_at)
        if dt and not (oldest_allowed <= dt <= end):
            errors.append(f"item {idx} published_at is outside {MAX_NEWS_AGE_DAYS}-day freshness window: {published_at}")
        if not dt:
            warnings.append(f"item {idx} published_at could not be parsed: {published_at}")
        if _has_bad_title_punct(title):
            warnings.append(f"item {idx} title may be two-part or use disallowed punctuation: {title}")
        if _has_relative_time(body + title):
            warnings.append(f"item {idx} contains relative time wording; replace with exact date")
        if has_half_width_quotes(all_cn_text):
            errors.append(f"item {idx} contains half-width quotation marks; use Chinese full-width quotes")
        if len(paragraphs) < _min_body_paragraphs(section):
            errors.append(f"item {idx} body is too short: {len(paragraphs)} paragraphs, expected at least {_min_body_paragraphs(section)}")
        if len(body) < _min_body_chars(section):
            errors.append(f"item {idx} body is too short: {len(body)} chars, expected at least {_min_body_chars(section)}")
        if not isinstance(points, list) or not (1 <= len(points) <= 3):
            warnings.append(f"item {idx} should include 1 to 3 key_points")
        if not str(row.get("fact_check") or "").strip():
            warnings.append(f"item {idx} has empty fact_check note")

    host_counts = Counter(hosts)
    if len(host_counts) < 4 and len(items) >= 8:
        warnings.append(f"source diversity is low: only {len(host_counts)} unique domains")
    for h, n in host_counts.items():
        if n >= 5:
            warnings.append(f"domain {h} appears {n} times; consider diversifying sources")

    return FactCheckResult(ok=not errors, errors=errors, warnings=warnings)
