from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.text import WD_ALIGN_PARAGRAPH
from pypdf import PdfReader

from .config import RESEARCH_LOOKBACK_DAYS, RESEARCH_ORGANIZATION_SITES, RESEARCH_REPORT_TITLE, RESEARCH_SOURCE_URLS, USER_AGENT
from .docx_writer import (
    _set_run_font,
    _setup_document,
    _setup_section,
    _write_body,
    _write_key_point,
    _write_reference,
    _write_source,
    FONT_HEADING,
    HEADING_COLOR,
)
from .text_utils import has_half_width_quotes, normalize_chinese_punctuation

LOGGER = logging.getLogger(__name__)
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
REPORT_TERMS = ("crypto", "digital asset", "digital assets", "tokenization", "tokenisation", "stablecoin", "blockchain", "defi", "web3", "rwa", "bitcoin", "ethereum")
BLOCKED_URL_PARTS = ("/zh", "/zh-cn", "/cn/", "?lang=zh", "language=zh")


@dataclass
class ResearchCandidate:
    title: str
    url: str
    source_name: str
    published_at: str = ""
    snippet: str = ""


def _chat(messages: list[dict[str, str]], timeout: int = 300) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")
    base_url = os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0.1, "stream": False, "response_format": {"type": "json_object"}},
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"DeepSeek API error {response.status_code}: {response.text[:800]}")
    return response.json()["choices"][0]["message"]["content"]


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def _norm_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _safe_filename(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return (name or "research_report")[:120]


def _host(url: str) -> str:
    return urllib.parse.urlsplit(url or "").netloc.lower().replace("www.", "")


def _is_english_url(url: str) -> bool:
    low = url.lower()
    return not any(part in low for part in BLOCKED_URL_PARTS)


def _looks_relevant(text: str) -> bool:
    low = text.lower()
    return any(term in low for term in REPORT_TERMS)


def _bing_rss_url(query: str) -> str:
    return "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "format": "rss", "setlang": "en", "mkt": "en-US"})


def _parse_rss_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BEIJING_TZ)
    except Exception:
        return None


def _add_candidate(out: list[ResearchCandidate], seen: set[str], *, title: str, url: str, source_name: str, published_at: str = "", snippet: str = "") -> None:
    url = _norm_text(url)
    title = _norm_text(title) or url.rsplit("/", 1)[-1]
    if not url.startswith("http") or url in seen or not _is_english_url(url):
        return
    if re.search(r"[\u4e00-\u9fff]", title + snippet + url):
        return
    if not _looks_relevant(title + " " + snippet + " " + url):
        return
    seen.add(url)
    out.append(ResearchCandidate(title=title, url=url, source_name=source_name, published_at=published_at, snippet=snippet))


def _extract_pdf_links_from_page(name: str, page_url: str, seen: set[str]) -> list[ResearchCandidate]:
    candidates: list[ResearchCandidate] = []
    try:
        response = requests.get(page_url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"}, timeout=25, allow_redirects=True)
        response.raise_for_status()
    except Exception as exc:
        LOGGER.debug("research source page fetch failed for %s: %s", page_url, exc)
        return candidates
    soup = BeautifulSoup(response.text, "html.parser")
    page_text = _norm_text(soup.get_text(" "))[:1500]
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(response.url, a.get("href") or "")
        anchor = _norm_text(a.get_text(" "))
        href_low = href.lower()
        if ".pdf" in href_low or "download" in href_low or "report" in href_low:
            _add_candidate(candidates, seen, title=anchor or name, url=href, source_name=name, snippet=page_text)
    return candidates


def search_research_pdfs(lookback_days: int = RESEARCH_LOOKBACK_DAYS) -> list[ResearchCandidate]:
    start = datetime.now(BEIJING_TZ) - timedelta(days=lookback_days)
    candidates: list[ResearchCandidate] = []
    seen: set[str] = set()
    topics = '(crypto OR "digital assets" OR tokenization OR tokenisation OR stablecoin OR blockchain OR DeFi OR Web3 OR RWA) (report OR research OR outlook) filetype:pdf'
    for org, domain in RESEARCH_ORGANIZATION_SITES.items():
        query = f"site:{domain} {topics}"
        try:
            xml_text = requests.get(_bing_rss_url(query), headers={"User-Agent": USER_AGENT}, timeout=20).text
            root = ET.fromstring(xml_text.encode("utf-8"))
        except Exception as exc:
            LOGGER.debug("research search failed for %s: %s", org, exc)
            continue
        for item in root.findall("./channel/item"):
            title = _norm_text(item.findtext("title"))
            url = _norm_text(item.findtext("link"))
            snippet = _norm_text(item.findtext("description"))
            dt = _parse_rss_date(item.findtext("pubDate") or "")
            if dt and dt < start:
                continue
            if ".pdf" not in url.lower() and "pdf" not in snippet.lower() and "report" not in (title + snippet).lower():
                continue
            _add_candidate(candidates, seen, title=title, url=url, source_name=org, published_at=dt.isoformat() if dt else "", snippet=snippet)
    for name, url in RESEARCH_SOURCE_URLS.items():
        candidates.extend(_extract_pdf_links_from_page(name, url, seen))
    return candidates[:100]


def _resolve_pdf_url(url: str) -> str | None:
    if not url.startswith("http"):
        return None
    if ".pdf" in url.lower():
        return url
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"}, timeout=25, allow_redirects=True)
        response.raise_for_status()
    except Exception:
        return None
    content_type = response.headers.get("content-type", "").lower()
    if "application/pdf" in content_type or response.content[:2048].find(b"%PDF") >= 0:
        return response.url
    soup = BeautifulSoup(response.text, "html.parser")
    best: str | None = None
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(response.url, a.get("href") or "")
        text = _norm_text(a.get_text(" "))
        if ".pdf" in href.lower() and _looks_relevant(href + " " + text):
            best = href
            break
    return best


def _download_pdf(candidate: ResearchCandidate, output_dir: Path) -> Path | None:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        pdf_url = _resolve_pdf_url(candidate.url)
        if not pdf_url:
            return None
        response = requests.get(pdf_url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"}, timeout=60, allow_redirects=True)
        response.raise_for_status()
        content = response.content
        if not content.startswith(b"%PDF") and b"%PDF" not in content[:2048]:
            return None
        candidate.url = response.url
        digest = hashlib.sha1(candidate.url.encode("utf-8")).hexdigest()[:8]
        name = f"{_safe_filename(candidate.source_name)}_{_safe_filename(candidate.title)}_{digest}.pdf"
        path = output_dir / name
        path.write_bytes(content)
        return path
    except Exception as exc:
        LOGGER.debug("pdf download failed for %s: %s", candidate.url, exc)
        return None


def _extract_pdf_text(path: Path, max_chars: int = 50000) -> str:
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages[:90]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            parts.append(text)
        if sum(len(x) for x in parts) >= max_chars:
            break
    return _norm_text("\n".join(parts))[:max_chars]


def _score_candidate(candidate: ResearchCandidate, text: str) -> int:
    combined = f"{candidate.title} {candidate.snippet} {candidate.url} {text[:3000]}".lower()
    score = sum(5 for term in REPORT_TERMS if term in combined)
    if candidate.source_name in RESEARCH_SOURCE_URLS or candidate.source_name in RESEARCH_ORGANIZATION_SITES:
        score += 5
    if "report" in combined or "research" in combined:
        score += 4
    if "2026" in combined:
        score += 3
    if len(text) > 12000:
        score += 5
    return score


def _choose_pdf(output_dir: Path) -> tuple[ResearchCandidate | None, Path | None, str]:
    candidates = search_research_pdfs()
    scored: list[tuple[int, ResearchCandidate, Path, str]] = []
    for candidate in candidates:
        pdf_path = _download_pdf(candidate, output_dir)
        if not pdf_path:
            continue
        text = _extract_pdf_text(pdf_path)
        low = text.lower()
        if len(text) < 4000 or not any(term in low for term in REPORT_TERMS):
            try:
                pdf_path.unlink(missing_ok=True)
            except Exception:
                pass
            continue
        scored.append((_score_candidate(candidate, text), candidate, pdf_path, text))
    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        _, candidate, pdf_path, text = scored[0]
        return candidate, pdf_path, text
    return None, None, ""


def _compile_research(candidate: ResearchCandidate, pdf_path: Path, extracted_text: str) -> dict[str, Any]:
    if not os.getenv("DEEPSEEK_API_KEY"):
        chunks = [normalize_chinese_punctuation(extracted_text[i : i + 550]) for i in range(0, min(len(extracted_text), 9000), 550)]
        return {
            "title_cn": normalize_chinese_punctuation(candidate.title),
            "source_title": candidate.title,
            "source_name": candidate.source_name,
            "source_url": candidate.url,
            "pdf_path": str(pdf_path),
            "key_points": ["该专题研究由英文 PDF 原文自动提取并生成草稿，发布前需人工复核。"],
            "body_paragraphs": chunks[:24],
            "fact_check": "fallback 草稿，保留英文 PDF 原文。",
        }
    prompt = f"""
请将以下英文研究报告编译翻译成中文专题研究稿，目标为15至20页 Word 篇幅。要求：
1. 不是摘要，必须保留报告的核心结构、主要发现、背景、数据逻辑、影响分析和结论。
2. 输出18至28个自然段，每段180至320个中文字符。
3. 开头给3个关键点，每个约40至70字。
4. 专业术语首次出现写“中文（English，缩写）”；英文机构名保留英文。
5. 使用流畅、自然、专业中文，全角中文标点和中文全角引号，不使用半角引号。
6. 不编造报告中没有的信息。
输出 JSON：{{"title_cn":"中文标题","source_title":"英文原题","source_name":"机构","source_url":"URL","key_points":["关键点"],"body_paragraphs":["段落"],"fact_check":"核验说明"}}
英文报告元数据：{json.dumps(asdict(candidate), ensure_ascii=False)}
英文报告正文节选：
{extracted_text[:36000]}
""".strip()
    data = _extract_json(_chat([{"role": "system", "content": "你是专业金融研究报告中文编译编辑。只输出严格 JSON。"}, {"role": "user", "content": prompt}], timeout=360))
    paragraphs = [normalize_chinese_punctuation(str(x)) for x in data.get("body_paragraphs", []) if str(x).strip()]
    return {
        "title_cn": normalize_chinese_punctuation(str(data.get("title_cn") or candidate.title)),
        "source_title": candidate.title,
        "source_name": candidate.source_name,
        "source_url": candidate.url,
        "pdf_path": str(pdf_path),
        "key_points": [normalize_chinese_punctuation(str(x)) for x in data.get("key_points", [])[:3]],
        "body_paragraphs": paragraphs,
        "fact_check": normalize_chinese_punctuation(str(data.get("fact_check") or "基于英文 PDF 原文编译。")),
    }


def write_research_docx(research: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    _setup_document(doc)
    section = doc.sections[0]
    _setup_section(section)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(RESEARCH_REPORT_TITLE)
    _set_run_font(r, east_asia=FONT_HEADING, size=16, color=HEADING_COLOR)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(normalize_chinese_punctuation(str(research.get("title_cn") or "-")))
    _set_run_font(r, east_asia=FONT_HEADING, size=15)

    for point in research.get("key_points", [])[:3]:
        _write_key_point(doc, str(point))

    doc.add_section(WD_SECTION_START.NEW_PAGE)
    for para in research.get("body_paragraphs", []):
        _write_body(doc, str(para))

    _write_source(doc, str(research.get("source_name") or "-"))
    _write_reference(doc, f"原文标题：{research.get('source_title') or '-'}")
    _write_reference(doc, f"原文链接：{research.get('source_url') or '-'}")
    _write_reference(doc, f"PDF文件：{research.get('pdf_path') or '-'}")
    doc.core_properties.title = f"{RESEARCH_REPORT_TITLE}_{datetime.now(BEIJING_TZ).strftime('%Y%m%d')}"
    doc.save(path)
    return path


def check_research(research: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    paragraphs = research.get("body_paragraphs") or []
    text = " ".join(str(x) for x in paragraphs)
    if len(paragraphs) < 18:
        errors.append(f"专题研究正文段落过少：{len(paragraphs)}，应至少18段")
    if len(text) < 9000:
        warnings.append(f"专题研究正文可能不足15页：当前约{len(text)}个字符")
    if has_half_width_quotes(text):
        errors.append("专题研究正文包含半角引号")
    if not str(research.get("pdf_path") or "").endswith(".pdf"):
        errors.append("未保存英文原文 PDF")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def generate_research(output_root: Path, run_date: datetime) -> dict[str, Any]:
    source_dir = output_root / "research_sources" / run_date.strftime("%Y%m%d")
    candidate, pdf_path, text = _choose_pdf(source_dir)
    if not candidate or not pdf_path:
        raise RuntimeError("No suitable English PDF research report found")
    research = _compile_research(candidate, pdf_path, text)
    output_file = output_root / f"专题研究_{run_date.strftime('%Y%m%d')}.docx"
    write_research_docx(research, output_file)
    fact = check_research(research)
    return {"research": research, "factcheck": fact, "outputs": {"docx": str(output_file), "pdf": str(pdf_path)}}
