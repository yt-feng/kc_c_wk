from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime
from urllib.parse import urlsplit

from .config import SECTION_COUNTS, US_TERMS
from .sources import is_chinese_item, parse_datetime


@dataclass
class FactCheckResult:
    ok: bool
    errors: list[str]
    warnings: list[str]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _host(url: str) -> str:
    return urlsplit(url or "").netloc.lower().replace("www.", "")


def _contains_us(text: str) -> bool:
    low = (text or "").lower()
    return any(term.lower() in low for term in US_TERMS)


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
    if policy_rows and not any(_contains_us(" ".join(str(row.get(k, "")) for k in row.keys())) for row in policy_rows):
        errors.append("政策风向 requires at least one US-related item")

    hosts: list[str] = []
    for idx, row in enumerate(items, start=1):
        if not isinstance(row, dict):
            errors.append(f"item {idx} is not an object")
            continue
        title = str(row.get("title_cn") or row.get("source_title") or "")
        summary = str(row.get("summary_cn") or "")
        url = str(row.get("url") or "")
        published_at = str(row.get("published_at") or "")
        if not (url.startswith("http://") or url.startswith("https://")):
            errors.append(f"item {idx} has invalid url: {url}")
        h = _host(url)
        if h:
            hosts.append(h)
        if is_chinese_item(title, summary, url):
            errors.append(f"item {idx} appears to use a Chinese source or Chinese source text")
        dt = parse_datetime(published_at)
        if dt and not (start <= dt <= end):
            errors.append(f"item {idx} published_at is outside lookback window: {published_at}")
        if not dt:
            warnings.append(f"item {idx} published_at could not be parsed: {published_at}")
        if not str(row.get("fact_check") or "").strip():
            warnings.append(f"item {idx} has empty fact_check note")

    host_counts = Counter(hosts)
    if len(host_counts) < 4 and len(items) >= 8:
        warnings.append(f"source diversity is low: only {len(host_counts)} unique domains")
    for h, n in host_counts.items():
        if n >= 5:
            warnings.append(f"domain {h} appears {n} times; consider diversifying sources")

    return FactCheckResult(ok=not errors, errors=errors, warnings=warnings)
