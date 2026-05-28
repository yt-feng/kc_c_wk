from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests

from .config import HK_TERMS, SECTION_COUNTS, SECTION_ORDER, US_TERMS
from .sources import RawItem
from .text_utils import normalize_chinese_punctuation

LOGGER = logging.getLogger(__name__)
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
TITLE_SPLIT_RE = re.compile(r"[，,；;：:—–-]+")
COUNTRY_WORDS = ("美国", "韩国", "英国", "日本", "欧盟", "印度", "泰国", "新加坡", "香港", "澳大利亚", "加拿大", "巴西", "法国", "德国")


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
        json={"model": model, "messages": messages, "temperature": 0.1, "stream": False, "response_format": {"type": "json_object"}},
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"DeepSeek API error {response.status_code}: {response.text[:800]}")
    return response.json()["choices"][0]["message"]["content"]


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
    system = "你是加密货币周刊的资深中文编译编辑。只基于给定英文来源写作，不得编造。只输出严格 JSON。"
    user = f"""
请为《加密货币观察》选择并全文编译内容。统计窗口：{start_label} 至 {end_label} 北京时间；新闻发布时间不得早于当前时间一周前。
栏目数量：{rules}。政策风向优先美国、香港的正式监管动向，3篇不要全是同一地区。
写作要求：使用流畅、自然、专业且基调一致的中文；每篇写1至3个关键点；专业术语首次出现写“中文（English，缩写）”；除特朗普等极高知名度人物外，英文人名不翻译，首次写Firstname Lastname，此后写Lastname；不要使用“今年”“本周五”“近日”等相对时间；标题要专业、有信息量、单句直述，不用逗号、冒号、分号、破折号拆成两句；全文使用全角中文标点，引号必须使用中文全角引号“”和‘’，不得使用半角引号；意见领袖栏目可写“XXX认为”“XXX指出”。
正文要求：普通条目3至5段，专题研究5至8段。只能使用候选来源可支持的信息，不得新增来源外的数字、机构、人物观点、时间和结论。
输出 JSON：{{"items":[{{"section":"政策风向","title_cn":"中文标题","source_title":"英文原题","event_date":"YYYY-MM-DD","key_points":["关键点一","关键点二"],"lead_cn":"导语","body_paragraphs":["正文第一段","正文第二段"],"source_name":"来源","url":"URL","published_at":"发布时间","region":"美国/香港/欧盟/其他","fact_check":"核验说明"}}],"notes":["..."]}}
候选 JSON：
{json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(t.lower() in low for t in terms)


def _section_score(item: RawItem, section: str) -> int:
    text = f"{item.title} {item.summary} {item.query}".lower()
    score = 5 if item.section_hint == section else 0
    section_terms = {
        "政策风向": ("regulation", "sec", "cftc", "treasury", "policy", "law", "enforcement", "mica", "stablecoin", "sfc", "hkma", "guidance", "framework", "rule", "approved", "final"),
        "行业前沿": ("defi", "layer", "ethereum", "protocol", "blockchain", "upgrade", "launch", "tokenization"),
        "市场动态": ("etf", "market", "funding", "raises", "exchange", "bitcoin", "price", "inflow", "acquisition"),
        "意见领袖": ("says", "opinion", "interview", "ceo", "founder", "analyst", "investor", "predicts"),
        "专题研究": ("report", "research", "outlook", "analysis", "on-chain", "weekly"),
    }
    score += sum(1 for term in section_terms.get(section, ()) if term in text)
    if section == "政策风向" and (_has_any(text, US_TERMS) or _has_any(text, HK_TERMS)):
        score += 4
    if section == "政策风向" and any(t in text for t in ("proposal", "proposed", "petition")):
        score -= 2
    return score


def normalize_punctuation(text: str) -> str:
    return normalize_chinese_punctuation(text)


def clean_title(title: str) -> str:
    value = re.sub(r"\s+", "", str(title or "")).strip(" ，,；;：:。.!！?？—–-")
    if not value:
        return "-"
    value = re.sub(r"（[^）]{1,20}）", "", value)
    value = re.sub(r"\([^)]{1,30}\)", "", value)
    parts = [p for p in TITLE_SPLIT_RE.split(value) if p]
    if len(parts) >= 2:
        first, second = parts[0], "".join(parts[1:])
        country = next((c for c in COUNTRY_WORDS if c in first), "")
        if second.startswith("政府") and country:
            value = country + second
        elif second.startswith(("将", "拟", "计划", "重新", "继续", "开始", "考虑", "寻求")) and country and len(first) <= 18:
            value = country + second
        elif second.startswith("寻求"):
            value = first + second.replace("寻求", "", 1)
        elif second.startswith("旨在"):
            value = first + second.replace("旨在", "", 1)
        elif second.startswith("以"):
            value = first + second.replace("以", "", 1)
        else:
            value = first + second
    value = TITLE_SPLIT_RE.sub("", value)
    value = value.replace("明确化", "明确").replace("寻求数字资产监管明确", "明确数字资产监管").replace("寻求监管明确", "明确监管")
    return normalize_chinese_punctuation(value.strip(" ，,；;：:。.!！?？—–-")) or "-"


def _infer_region(item: RawItem) -> str:
    text = f"{item.title} {item.summary} {item.query} {item.source_name}"
    if _has_any(text, US_TERMS):
        return "美国"
    if _has_any(text, HK_TERMS):
        return "香港"
    low = text.lower()
    if "mica" in low or "esma" in low or "europe" in low:
        return "欧盟"
    return "其他"


def _fallback(items: list[RawItem]) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    used_urls: set[str] = set()
    for section in SECTION_ORDER:
        ranked = sorted(items, key=lambda x: _section_score(x, section), reverse=True)
        for item in ranked:
            if len([x for x in selected if x["section"] == section]) >= SECTION_COUNTS[section]:
                break
            if item.url in used_urls or (_section_score(item, section) <= 0 and item.section_hint != section):
                continue
            used_urls.add(item.url)
            lead = normalize_punctuation(item.summary or item.title)
            selected.append({
                "section": section,
                "title_cn": clean_title(item.title),
                "source_title": item.title,
                "event_date": (item.published_at or "")[:10] or "-",
                "key_points": ["该条由新闻标题、摘要和发布时间筛选得到，发布前需人工复核。"],
                "lead_cn": lead[:180],
                "body_paragraphs": [lead[:300], "自动草稿：该条由新闻标题、摘要、来源和发布时间筛选得到。", "发布前应打开原始链接核对事件时间、主体、数字和监管表述。"],
                "source_name": item.source_name,
                "url": item.url,
                "published_at": item.published_at,
                "region": _infer_region(item),
                "fact_check": "fallback 草稿，保留原始来源用于人工核验。",
            })
    return {"items": selected, "notes": ["DeepSeek 未配置或调用失败，已生成 fallback 草稿。"]}


def _paragraphs_from_row(row: dict[str, Any]) -> list[str]:
    raw = row.get("body_paragraphs")
    if isinstance(raw, list):
        paragraphs = [normalize_punctuation(str(x).strip()) for x in raw if str(x).strip()]
    else:
        paragraphs = []
    if not paragraphs:
        paragraphs = [normalize_punctuation(str(row.get("lead_cn") or row.get("summary_cn") or "-").strip())]
    return paragraphs or ["-"]


def _key_points_from_row(row: dict[str, Any]) -> list[str]:
    raw = row.get("key_points")
    if isinstance(raw, list):
        return [normalize_punctuation(str(x).strip()) for x in raw if str(x).strip()][:3]
    return []


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
            "title_cn": clean_title(str(row.get("title_cn") or row.get("title") or "-")),
            "source_title": str(row.get("source_title") or "-").strip(),
            "event_date": str(row.get("event_date") or "-").strip(),
            "key_points": _key_points_from_row(row),
            "lead_cn": normalize_punctuation(str(row.get("lead_cn") or row.get("summary_cn") or "-").strip()),
            "body_paragraphs": _paragraphs_from_row(row),
            "source_name": str(row.get("source_name") or "-").strip(),
            "url": str(row.get("url") or "-").strip(),
            "published_at": str(row.get("published_at") or "-").strip(),
            "region": str(row.get("region") or "其他").strip(),
            "fact_check": normalize_punctuation(str(row.get("fact_check") or "-").strip()),
        })
    return {"items": clean, "notes": [str(x) for x in data.get("notes", []) if x]}


def compile_report(items: list[RawItem], start_label: str, end_label: str) -> dict[str, Any]:
    if not items:
        return {"items": [], "notes": ["No raw candidates collected."]}
    if not os.getenv("DEEPSEEK_API_KEY"):
        return normalize_report(_fallback(items))
    try:
        return normalize_report(_extract_json(_chat(_build_prompt(items, start_label, end_label))))
    except Exception as exc:
        LOGGER.warning("DeepSeek compile failed, using fallback: %s", exc)
        return normalize_report(_fallback(items))
