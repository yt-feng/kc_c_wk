from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from .config import REPORT_TITLE, SECTION_ORDER

FONT_BODY = "宋体"
FONT_HEADING = "黑体"
FONT_LATIN = "Times New Roman"


def _set_run_font(run, east_asia: str = FONT_BODY, size: float = 12, bold: bool = False, italic: bool = False) -> None:
    run.font.name = FONT_LATIN
    run._element.rPr.rFonts.set(qn("w:eastAsia"), east_asia)
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic


def _format_paragraph(paragraph, *, first_line: bool = False, align: int | None = None, before: float = 0, after: float = 6) -> None:
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    if first_line:
        fmt.first_line_indent = Pt(24)
    if align is not None:
        paragraph.alignment = align


def _add_text(doc: Document, text: str, *, font: str = FONT_BODY, size: float = 12, bold: bool = False, first_line: bool = False, align: int | None = None, before: float = 0, after: float = 6) -> None:
    p = doc.add_paragraph()
    _format_paragraph(p, first_line=first_line, align=align, before=before, after=after)
    r = p.add_run(text)
    _set_run_font(r, east_asia=font, size=size, bold=bold)


def _setup_document(doc: Document) -> None:
    section = doc.sections[0]
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.18)
    section.right_margin = Cm(3.18)
    styles = doc.styles
    styles["Normal"].font.name = FONT_LATIN
    styles["Normal"]._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_BODY)
    styles["Normal"].font.size = Pt(12)


def _items_by_section(items: list[dict[str, Any]], section: str) -> list[dict[str, Any]]:
    return [row for row in items if row.get("section") == section]


def _body_paragraphs(row: dict[str, Any]) -> list[str]:
    paragraphs = row.get("body_paragraphs")
    if isinstance(paragraphs, list):
        cleaned = [str(x).strip() for x in paragraphs if str(x).strip()]
    else:
        cleaned = []
    if not cleaned:
        for key in ("lead_cn", "summary_cn", "analysis_cn"):
            value = str(row.get(key) or "").strip()
            if value and value != "-":
                cleaned.append(value)
    return cleaned or ["-"]


def _write_toc(doc: Document, items: list[dict[str, Any]]) -> None:
    title = doc.add_paragraph()
    _format_paragraph(title, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=18)
    r = title.add_run("目  录")
    _set_run_font(r, east_asia=FONT_HEADING, size=16, bold=True)

    for section in SECTION_ORDER:
        p = doc.add_paragraph()
        _format_paragraph(p, before=8, after=4)
        r = p.add_run(f"【{section}】")
        _set_run_font(r, east_asia=FONT_HEADING, size=12, bold=True)
        rows = _items_by_section(items, section)
        if not rows:
            p = doc.add_paragraph()
            _format_paragraph(p, after=2)
            r = p.add_run("· 暂无满足自动筛选条件的资讯")
            _set_run_font(r, east_asia=FONT_BODY, size=11)
            continue
        for row in rows:
            p = doc.add_paragraph()
            _format_paragraph(p, after=2)
            r = p.add_run(f"· {row.get('title_cn', '-')}")
            _set_run_font(r, east_asia=FONT_BODY, size=11)


def _write_section_heading(doc: Document, section: str) -> None:
    p = doc.add_paragraph()
    _format_paragraph(p, before=0, after=12)
    r = p.add_run(f"【{section}】")
    _set_run_font(r, east_asia=FONT_HEADING, size=16, bold=True)


def _write_article(doc: Document, row: dict[str, Any]) -> None:
    title = str(row.get("title_cn") or "-").strip()
    p = doc.add_paragraph()
    _format_paragraph(p, before=4, after=8)
    r = p.add_run(title)
    _set_run_font(r, east_asia=FONT_HEADING, size=14, bold=True)

    lead = str(row.get("lead_cn") or "").strip()
    if lead and lead != "-":
        _add_text(doc, lead, font=FONT_BODY, size=12, first_line=True, after=6)

    for paragraph in _body_paragraphs(row):
        if paragraph == lead:
            continue
        _add_text(doc, paragraph, font=FONT_BODY, size=12, first_line=True, after=6)

    source_name = str(row.get("source_name") or "-").strip()
    source_title = str(row.get("source_title") or "-").strip()
    url = str(row.get("url") or "-").strip()
    source_line = f"（信息来源：{source_name}）"
    _add_text(doc, source_line, font=FONT_BODY, size=10.5, align=WD_ALIGN_PARAGRAPH.RIGHT, after=2)
    if source_title and source_title != "-":
        _add_text(doc, f"原文标题：{source_title}", font=FONT_BODY, size=9, after=1)
    if url and url != "-":
        _add_text(doc, f"原文链接：{url}", font=FONT_BODY, size=9, after=10)


def write_docx(report: dict[str, Any], output_path: str | Path, metadata: dict[str, Any] | None = None) -> Path:
    metadata = metadata or {}
    items = [x for x in report.get("items", []) if isinstance(x, dict)]
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = Document()
    _setup_document(doc)

    _write_toc(doc, items)
    doc.add_page_break()

    first_section = True
    for section in SECTION_ORDER:
        if not first_section:
            doc.add_section(WD_SECTION_START.NEW_PAGE)
        first_section = False
        _write_section_heading(doc, section)
        rows = _items_by_section(items, section)
        if not rows:
            _add_text(doc, "暂无满足自动筛选条件的资讯。", size=12, first_line=True)
            continue
        for idx, row in enumerate(rows, start=1):
            _write_article(doc, row)
            if idx != len(rows):
                doc.add_paragraph()

    doc.core_properties.title = f"{REPORT_TITLE}周刊"
    doc.core_properties.subject = str(metadata.get("period") or "最近三天")
    doc.save(path)
    return path
