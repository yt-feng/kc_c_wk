from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from .config import REPORT_TITLE, SECTION_ORDER


def _set_font(run, size: int = 11, bold: bool = False) -> None:
    run.font.name = "Microsoft YaHei"
    run.font.size = Pt(size)
    run.bold = bold


def _add_para(doc: Document, text: str, size: int = 11, bold: bool = False) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text)
    _set_font(run, size=size, bold=bold)


def write_docx(report: dict[str, Any], output_path: str | Path, metadata: dict[str, Any] | None = None) -> Path:
    metadata = metadata or {}
    items = [x for x in report.get("items", []) if isinstance(x, dict)]
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = Document()
    styles = doc.styles
    styles["Normal"].font.name = "Microsoft YaHei"
    styles["Normal"].font.size = Pt(11)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(f"《{REPORT_TITLE}》周刊")
    _set_font(run, size=18, bold=True)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    generated_at = metadata.get("generated_at") or datetime.now().strftime("%Y-%m-%d %H:%M")
    period = metadata.get("period") or "最近三天"
    run = subtitle.add_run(f"统计区间：{period}；生成时间：{generated_at}")
    _set_font(run, size=10)

    doc.add_paragraph()
    toc = doc.add_paragraph()
    run = toc.add_run("目录")
    _set_font(run, size=14, bold=True)
    for section in SECTION_ORDER:
        for row in items:
            if row.get("section") == section:
                p = doc.add_paragraph(style=None)
                r = p.add_run(f"· {row.get('title_cn', '-')}")
                _set_font(r, size=10)

    doc.add_page_break()
    for section in SECTION_ORDER:
        heading = doc.add_paragraph()
        r = heading.add_run(f"【{section}】")
        _set_font(r, size=15, bold=True)
        section_rows = [row for row in items if row.get("section") == section]
        if not section_rows:
            _add_para(doc, "暂无满足自动筛选条件的资讯。", size=11)
            continue
        for idx, row in enumerate(section_rows, start=1):
            p = doc.add_paragraph()
            r = p.add_run(str(row.get("title_cn") or "-"))
            _set_font(r, size=13, bold=True)
            _add_para(doc, str(row.get("summary_cn") or "-"), size=11)
            analysis = str(row.get("analysis_cn") or "").strip()
            if analysis:
                _add_para(doc, "简析：" + analysis, size=11)
            src = row.get("source_name") or "-"
            date = row.get("published_at") or row.get("event_date") or "-"
            url = row.get("url") or "-"
            _add_para(doc, f"信息来源：{src}；发布时间：{date}\nURL：{url}", size=9)
            fc = str(row.get("fact_check") or "").strip()
            if fc:
                _add_para(doc, "事实核验：" + fc, size=9)
            if idx != len(section_rows):
                doc.add_paragraph()

    notes = report.get("notes") or []
    fact = metadata.get("factcheck") or {}
    doc.add_page_break()
    h = doc.add_paragraph()
    r = h.add_run("自动运行与核验摘要")
    _set_font(r, size=14, bold=True)
    _add_para(doc, f"原始候选数：{metadata.get('raw_count', '-')}", size=10)
    _add_para(doc, f"入选条目数：{len(items)}", size=10)
    _add_para(doc, f"Fact check OK：{fact.get('ok', '-')}", size=10)
    for msg in fact.get("errors", [])[:20]:
        _add_para(doc, "错误：" + str(msg), size=9)
    for msg in fact.get("warnings", [])[:20]:
        _add_para(doc, "提醒：" + str(msg), size=9)
    for msg in notes[:20]:
        _add_para(doc, "备注：" + str(msg), size=9)

    doc.save(path)
    return path
