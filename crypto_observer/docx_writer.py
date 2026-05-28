from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.section import WD_SECTION_START
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .config import REPORT_TITLE, SECTION_ORDER

FONT_BODY = "仿宋"
FONT_TOC_ITEM = "楷体"
FONT_HEADING = "黑体"
FONT_LATIN = "Times New Roman"


STYLE_ARTICLE_TITLE = "文章一级标题"
STYLE_BODY = "正文内容"
STYLE_SOURCE = "信息来源"


def _ensure_style(doc: Document, name: str):
    styles = doc.styles
    if name in styles:
        return styles[name]
    return styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)


def _set_rfonts(obj, east_asia: str, ascii_font: str = FONT_LATIN) -> None:
    rpr = obj._element.get_or_add_rPr()
    rfonts = rpr.rFonts
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), ascii_font)
    rfonts.set(qn("w:hAnsi"), ascii_font)
    rfonts.set(qn("w:cs"), FONT_LATIN)
    rfonts.set(qn("w:eastAsia"), east_asia)


def _set_run_font(run, east_asia: str = FONT_BODY, size: float = 14, bold: bool = False, color: str | None = None) -> None:
    run.font.name = FONT_LATIN
    _set_rfonts(run, east_asia)
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def _set_style_font(style, east_asia: str, size: float, bold: bool | None = None, color: str | None = None) -> None:
    style.font.name = FONT_LATIN
    _set_rfonts(style, east_asia)
    style.font.size = Pt(size)
    if bold is not None:
        style.font.bold = bold
    if color:
        style.font.color.rgb = RGBColor.from_string(color)


def _set_doc_grid(section, line_pitch: int = 312) -> None:
    sect_pr = section._sectPr
    for child in sect_pr.findall(qn("w:docGrid")):
        sect_pr.remove(child)
    doc_grid = OxmlElement("w:docGrid")
    doc_grid.set(qn("w:type"), "lines")
    doc_grid.set(qn("w:linePitch"), str(line_pitch))
    sect_pr.append(doc_grid)


def _setup_section(section) -> None:
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.18)
    section.right_margin = Cm(3.18)
    section.header_distance = Cm(1.50)
    section.footer_distance = Cm(1.75)
    _set_doc_grid(section)


def _setup_document(doc: Document) -> None:
    for section in doc.sections:
        _setup_section(section)

    normal = doc.styles["Normal"]
    _set_style_font(normal, FONT_BODY, 14)
    normal.paragraph_format.first_line_indent = Pt(10)
    normal.paragraph_format.space_before = None
    normal.paragraph_format.space_after = None
    normal.paragraph_format.line_spacing = None

    heading1 = doc.styles["Heading 1"]
    _set_style_font(heading1, FONT_HEADING, 15, color="2F5496")
    heading1.paragraph_format.space_before = Pt(3)
    heading1.paragraph_format.space_after = Pt(12)
    heading1.paragraph_format.first_line_indent = Pt(0)
    heading1.paragraph_format.line_spacing = None

    article_title = _ensure_style(doc, STYLE_ARTICLE_TITLE)
    _set_style_font(article_title, FONT_HEADING, 15)
    article_title.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    article_title.paragraph_format.space_before = None
    article_title.paragraph_format.space_after = None
    article_title.paragraph_format.line_spacing = None

    body = _ensure_style(doc, STYLE_BODY)
    body.base_style = normal
    _set_style_font(body, FONT_BODY, 14)
    body.paragraph_format.first_line_indent = Pt(28.1)
    body.paragraph_format.space_before = None
    body.paragraph_format.space_after = None
    body.paragraph_format.line_spacing = None

    source = _ensure_style(doc, STYLE_SOURCE)
    source.base_style = normal
    _set_style_font(source, FONT_BODY, 10.5)
    source.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    source.paragraph_format.space_before = Pt(2.5)
    source.paragraph_format.space_after = Pt(5)
    source.paragraph_format.first_line_indent = None
    source.paragraph_format.line_spacing = None


def _clear_line_spacing(paragraph) -> None:
    paragraph.paragraph_format.line_spacing = None


def _add_paragraph(doc: Document, text: str, *, style: str | None = None, font: str = FONT_BODY, size: float = 14, bold: bool = False, align: int | None = None, color: str | None = None) -> None:
    p = doc.add_paragraph(style=style)
    if align is not None:
        p.alignment = align
    _clear_line_spacing(p)
    r = p.add_run(text)
    _set_run_font(r, east_asia=font, size=size, bold=bold, color=color)


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


def _key_points(row: dict[str, Any]) -> list[str]:
    raw = row.get("key_points")
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()][:3]
    return []


def _write_toc(doc: Document, items: list[dict[str, Any]]) -> None:
    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("目  录")
    _set_run_font(r, east_asia=FONT_HEADING, size=16)

    for section in SECTION_ORDER:
        p = doc.add_paragraph()
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.space_before = None
        p.paragraph_format.space_after = None
        r = p.add_run(f"【{section}】")
        _set_run_font(r, east_asia=FONT_HEADING, size=16, color="0066FF")

        rows = _items_by_section(items, section)
        if not rows:
            _write_toc_item(doc, "暂无满足自动筛选条件的资讯")
            continue
        for row in rows:
            _write_toc_item(doc, str(row.get("title_cn") or "-"))


def _write_toc_item(doc: Document, title: str) -> None:
    p = doc.add_paragraph(style="List Paragraph")
    p.paragraph_format.left_indent = Pt(0)
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.space_before = None
    p.paragraph_format.space_after = None
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    p.paragraph_format.line_spacing = 1.5
    r = p.add_run(f"· {title}")
    _set_run_font(r, east_asia=FONT_TOC_ITEM, size=14)


def _write_section_heading(doc: Document, section: str) -> None:
    _add_paragraph(doc, f"【{section}】", style="Heading 1", font=FONT_HEADING, size=15, color="2F5496")


def _write_article_title(doc: Document, title: str) -> None:
    _add_paragraph(doc, title, style=STYLE_ARTICLE_TITLE, font=FONT_HEADING, size=15, align=WD_ALIGN_PARAGRAPH.CENTER)


def _write_key_point(doc: Document, point: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.left_indent = Pt(0)
    p.paragraph_format.space_before = None
    p.paragraph_format.space_after = None
    _clear_line_spacing(p)
    r = p.add_run(f"· {point}")
    _set_run_font(r, east_asia=FONT_BODY, size=14)


def _write_body(doc: Document, paragraph: str, *, bold: bool = False) -> None:
    p = doc.add_paragraph(style=STYLE_BODY)
    p.paragraph_format.first_line_indent = Pt(28.1)
    p.paragraph_format.space_before = None
    p.paragraph_format.space_after = None
    _clear_line_spacing(p)
    r = p.add_run(paragraph)
    _set_run_font(r, east_asia=FONT_BODY, size=14, bold=bold)


def _write_source(doc: Document, source_name: str) -> None:
    p = doc.add_paragraph(style=STYLE_SOURCE)
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_before = Pt(2.5)
    p.paragraph_format.space_after = Pt(5)
    _clear_line_spacing(p)
    r = p.add_run(f"（信息来源：{source_name}）")
    _set_run_font(r, east_asia=FONT_BODY, size=10.5)


def _write_article(doc: Document, row: dict[str, Any]) -> None:
    title = str(row.get("title_cn") or "-").strip()
    _write_article_title(doc, title)

    for point in _key_points(row):
        _write_key_point(doc, point)

    lead = str(row.get("lead_cn") or "").strip()
    if lead and lead != "-":
        _write_body(doc, lead)

    for paragraph in _body_paragraphs(row):
        if paragraph == lead:
            continue
        _write_body(doc, paragraph)

    source_name = str(row.get("source_name") or "-").strip()
    source_title = str(row.get("source_title") or "-").strip()
    url = str(row.get("url") or "-").strip()
    _write_source(doc, source_name)
    if source_title and source_title != "-":
        _write_body(doc, f"原文标题：{source_title}")
    if url and url != "-":
        _write_body(doc, f"原文链接：{url}")


def write_docx(report: dict[str, Any], output_path: str | Path, metadata: dict[str, Any] | None = None) -> Path:
    metadata = metadata or {}
    items = [x for x in report.get("items", []) if isinstance(x, dict)]
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = Document()
    _setup_document(doc)
    _write_toc(doc, items)

    first_section = True
    for section in SECTION_ORDER:
        if first_section:
            body_section = doc.add_section(WD_SECTION_START.NEW_PAGE)
            _setup_section(body_section)
        else:
            next_section = doc.add_section(WD_SECTION_START.NEW_PAGE)
            _setup_section(next_section)
        first_section = False
        _write_section_heading(doc, section)
        rows = _items_by_section(items, section)
        if not rows:
            _write_body(doc, "暂无满足自动筛选条件的资讯。")
            continue
        for idx, row in enumerate(rows, start=1):
            _write_article(doc, row)
            if idx != len(rows):
                doc.add_paragraph()

    doc.core_properties.title = f"{REPORT_TITLE}周刊"
    doc.core_properties.subject = str(metadata.get("period") or "最近三天")
    doc.save(path)
    return path
