from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests

from .config import SECTION_COUNTS, SECTION_ORDER, US_TERMS
from .sources import RawItem

LOGGER = logging.getLogger(__name__)
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def _chat(messages: list[dict[str, str]], timeout: int = 180) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")
    base_url = os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "stream": False,
            "response_format": {"type": "json_object"},
        },
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"DeepSeek API error {response.status_code}: {response.text[:800]}")
    data = response.json()
    return data["choices"][0]["message"]["content"]


def _compact_item(item: RawItem) -> dict[str, str]:
    return {
        "title": item.title[:260],
        "url": item.url[:500],
        "source_name": item.source_name[:120],
        "published_at": item.published_at[:60],
        "summary": item.summary[:500],
        "section_hint": item.section_hint[:40],
        "query": item.query[:180],
    }


def _build_prompt(items: list[RawItem], start_label: str, end_label: str) -> list[dict[str, str]]:
    rules = "；".join([f"{name}{count}条" for name, count in SECTION_COUNTS.items()])
    payload = [_compact_item(x) for x in items]
    system = "你是加密货币周刊的资深中文编译编辑。只基于给定英文候选来源写作，不得编造。只能输出严格 JSON。"
    user = f"""
请从候选资讯中为《加密货币观察》选择并全文编译最近三天的内容。统计窗口：{start_label} 至 {end_label} 北京时间。
栏目数量：{rules}。政策风向必须至少包含一条美国相关资讯。排除中文网站、中文来源、无法确认日期或与加密货币无关的内容；尽量分散来源网站。

写作要求：
1. 每篇文章要按“编译稿”写成完整中文文章，不要写成摘要、要点或“简析”。
2. 普通条目正文为 3-5 个自然段；【专题研究】为 5-8 个自然段。每段应围绕事实、背景、影响和后续观察展开。
3. 只能使用候选条目中可支持的信息。没有来源支持的数字、机构、人物观点、时间和结论不得写入。
4. 标题用中文重写，正文保持客观、专业、可读。事实核验字段说明该条由哪些来源字段支持。
5. 同一事件只选一条；同一网站不要过度集中。

输出 JSON 对象，字段必须为：
{{"items":[{{"section":"政策风向","title_cn":"中文标题","source_title":"英文原题","event_date":"YYYY-MM-DD","lead_cn":"导语，80-140字","body_paragraphs":["正文第一段","正文第二段","正文第三段"],"source_name":"来源","url":"URL","published_at":"发布时间","fact_check":"说明为什么该条可由来源支持"}}],"notes":["..."]}}

候选 JSON：
{json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _is_us(text: str) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in US_TERMS)


def _section_score(item: RawItem, section: str) -> int:
    text = f"{item.title} {item.summary} {item.query}".lower()
    score = 0
    if item.section_hint == section:
        score += 5
    section_terms = {
        "政策风向": ("regulation", "sec", "cftc", "treasury", "policy", "law", "enforcement", "mica", "stablecoin"),
        "行业前沿": ("defi", "layer", "ethereum", "protocol", "blockchain", "upgrade", "launch", "tokenization"),
        "市场动态": ("etf", "market", "funding", "raises", "exchange", "bitcoin", "price", "inflow", "acquisition"),
        "意见领袖": ("says", "opinion", "interview", "ceo", "founder", "analyst", "investor", "predicts"),
        "专题研究": ("report", "research", "outlook", "analysis", "on-chain", "weekly"),
    }
    for term in section_terms.get(section, ()):
        if term in text:
            score += 1
    if section == "政策风向" and _is_us(text):
        score += 3
    return score


def _fallback(items: list[RawItem]) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    used_urls: set[str] = set()
    for section in SECTION_ORDER:
        ranked = sorted(items, key=lambda x: _section_score(x, section), reverse=True)
        count = SECTION_COUNTS[section]
        for item in ranked:
            if len([x for x in selected if x["section"] == section]) >= count:
                break
            if item.url in used_urls:
                continue
            if _section_score(item, section) <= 0 and item.section_hint != section:
                continue
            used_urls.add(item.url)
            lead = item.summary or item.title
            selected.append({
                "section": section,
                "title_cn": item.title,
                "source_title": item.title,
                "event_date": (item.published_at or "")[:10] or "-",
                "lead_cn": lead[:180],
                "body_paragraphs": [
                    (item.summary or item.title)[:300],
                    "自动草稿：该条由新闻标题、摘要、来源和发布时间筛选得到。由于未调用模型进行全文编译，正文仅保留来源摘要和复核提示。",
                    "发布前应打开原始链接核对事件时间、主体、数字和监管表述，并根据原文补充完整背景、影响和后续观察。",
                ],
                "source_name": item.source_name,
                "url": item.url,
                "published_at": item.published_at,
                "fact_check": "fallback 草稿，保留原始来源用于人工核验。",
            })
    return {"items": selected, "notes": ["DeepSeek 未配置或调用失败，已生成 fallback 草稿。"]}


def _paragraphs_from_row(row: dict[str, Any]) -> list[str]:
    raw = row.get("body_paragraphs")
    if isinstance(raw, list):
        paragraphs = [str(x).strip() for x in raw if str(x).strip()]
    else:
        paragraphs = []
    if not paragraphs:
        summary = str(row.get("summary_cn") or row.get("lead_cn") or "").strip()
        analysis = str(row.get("analysis_cn") or "").strip()
        paragraphs = [x for x in [summary, analysis] if x]
    return paragraphs or ["-"]


def normalize_report(data: dict[str, Any]) -> dict[str, Any]:
    rows = data.get("items") or []
    clean: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        section = str(row.get("section", "")).strip()
        if section not in SECTION_ORDER:
            continue
        clean.append({
            "section": section,
            "title_cn": str(row.get("title_cn") or row.get("title") or "-").strip(),
            "source_title": str(row.get("source_title") or "-").strip(),
            "event_date": str(row.get("event_date") or "-").strip(),
            "lead_cn": str(row.get("lead_cn") or row.get("summary_cn") or "-").strip(),
            "body_paragraphs": _paragraphs_from_row(row),
            "source_name": str(row.get("source_name") or "-").strip(),
            "url": str(row.get("url") or "-").strip(),
            "published_at": str(row.get("published_at") or "-").strip(),
            "fact_check": str(row.get("fact_check") or "-").strip(),
        })
    return {"items": clean, "notes": [str(x) for x in data.get("notes", []) if x]}


def compile_report(items: list[RawItem], start_label: str, end_label: str) -> dict[str, Any]:
    if not items:
        return {"items": [], "notes": ["No raw candidates collected."]}
    if not os.getenv("DEEPSEEK_API_KEY"):
        return normalize_report(_fallback(items))
    try:
        content = _chat(_build_prompt(items, start_label, end_label))
        return normalize_report(_extract_json(content))
    except Exception as exc:
        LOGGER.warning("DeepSeek compile failed, using fallback: %s", exc)
        return normalize_report(_fallback(items))
