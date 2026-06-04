from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any

import requests

from .config import HK_TERMS, SECTION_COUNTS, SECTION_ORDER, US_TERMS
from .sources import RawItem, host, is_final_url_allowed, title_key
from .text_utils import normalize_chinese_punctuation

LOGGER = logging.getLogger(__name__)
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
TITLE_SPLIT_RE = re.compile(r"[，,；;：:—–-]+")
COUNTRY_WORDS = ("美国", "韩国", "英国", "日本", "欧盟", "印度", "泰国", "新加坡", "香港", "澳大利亚", "加拿大", "巴西", "法国", "德国")
FRONTIER_TERMS = ("defi", "layer", "layer 2", "l2", "ethereum", "protocol", "blockchain", "upgrade", "mainnet", "testnet", "tokenization", "tokenisation", "interoperability", "restaking", "rollup", "staking", "wallet", "security", "infrastructure", "verkle", "glamsterdam", "pectra", "fusaka", "smart contract")
POLICY_TERMS = ("regulation", "regulatory", "sec", "cftc", "treasury", "federal reserve", "fed", "congress", "senate", "house", "white house", "irs", "fincen", "sfc", "hkma", "bank of england", "fca", "eu", "european", "esma", "mica", "law", "rule", "guidance", "framework", "enforcement", "license", "licence", "stablecoin bill", "digital asset bill")
OPINION_TERMS = ("said", "says", "told", "argued", "warned", "expects", "believes", "according to", "interview", "opinion", "analyst", "ceo", "founder", "cio", "investor", "economist", "chair", "president")
BAD_TEXT_TERMS = (
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
    "skip to main content menu",
)
PRICE_ONLY_TERMS = ("price outlook", "price prediction", "reach $", "target price", "can reach", "forecast 2026", "2026-2030")


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


def _chat(messages: list[dict[str, str]], timeout: int = 240) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")
    base_url = os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0.0, "stream": False, "response_format": {"type": "json_object"}},
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"DeepSeek API error {response.status_code}: {response.text[:800]}")
    return response.json()["choices"][0]["message"]["content"]


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(term in low for term in terms)


def _body(item: RawItem) -> str:
    return f"{item.title} {item.summary} {item.query} {getattr(item, 'article_text', '')}"


def _text_fp(item: RawItem) -> str:
    text = re.sub(r"\W+", "", (getattr(item, "article_text", "") or "").lower())[:2200]
    return hashlib.sha1(text.encode("utf-8")).hexdigest() if text else ""


def _safe_candidate(item: RawItem) -> bool:
    text = _body(item).lower()
    article_text = getattr(item, "article_text", "") or ""
    if not is_final_url_allowed(item.url):
        return False
    if len(article_text) < 900:
        return False
    if _has_any(text, BAD_TEXT_TERMS):
        return False
    if host(item.url) in {"angular.dev", "fonts.googleapis.com", "fonts.gstatic.com"}:
        return False
    if "compound" in text and "angular" in text:
        return False
    return True


def _section_match(item: RawItem, section: str) -> bool:
    text = _body(item).lower()
    if not _safe_candidate(item):
        return False
    if section == "政策风向":
        if _has_any(text, PRICE_ONLY_TERMS):
            return False
        return _has_any(text, POLICY_TERMS) and any(x in text for x in ("regulator", "regulation", "regulatory", "law", "rule", "guidance", "framework", "court", "sec", "cftc", "treasury", "sfc", "hkma", "mica", "bank of england", "fca", "congress"))
    if section in ("行业前沿", "市场动态"):
        hit_count = sum(1 for term in FRONTIER_TERMS if term in text)
        strong_upgrade = any(x in text for x in ("glamsterdam", "pectra", "fusaka", "upgrade", "mainnet", "testnet", "rollup", "verkle"))
        return hit_count >= 2 or strong_upgrade
    if section == "意见领袖":
        if _has_any(text, PRICE_ONLY_TERMS) and not _has_any(text, OPINION_TERMS):
            return False
        return _has_any(text, OPINION_TERMS)
    return False


def _section_score(item: RawItem, section: str) -> int:
    text = _body(item).lower()
    score = 10 if item.section_hint == section else 0
    if section == "政策风向":
        score += sum(2 for term in POLICY_TERMS if term in text)
        if _has_any(text, US_TERMS) or _has_any(text, HK_TERMS):
            score += 8
        if any(x in text for x in ("approved", "issued", "final", "effective", "signed", "enacted")):
            score += 5
        if any(x in text for x in ("proposal", "proposed", "petition")):
            score -= 4
    elif section in ("行业前沿", "市场动态"):
        score += sum(2 for term in FRONTIER_TERMS if term in text)
        if any(x in text for x in ("glamsterdam", "pectra", "fusaka", "verkle", "upgrade")):
            score += 8
        if _has_any(text, PRICE_ONLY_TERMS):
            score -= 5
    elif section == "意见领袖":
        score += sum(2 for term in OPINION_TERMS if term in text)
        if any(x in text for x in ("interview", "said", "told", "argued", "warned")):
            score += 6
    return score


def _select_items_by_section(items: list[RawItem]) -> tuple[list[RawItem], list[str]]:
    selected: list[RawItem] = []
    notes: list[str] = []
    used_urls: set[str] = set()
    used_titles: set[str] = set()
    used_texts: set[str] = set()
    safe_items = [x for x in items if _safe_candidate(x)]
    for section in SECTION_ORDER:
        candidates = [x for x in safe_items if _section_match(x, section)]
        candidates.sort(key=lambda x: _section_score(x, section), reverse=True)
        count = 0
        for item in candidates:
            url_key = item.url.strip().lower()
            title = title_key(item.title)
            fp = _text_fp(item)
            if url_key in used_urls or title in used_titles or (fp and fp in used_texts):
                continue
            selected.append(item)
            used_urls.add(url_key)
            if title:
                used_titles.add(title)
            if fp:
                used_texts.add(fp)
            count += 1
            if count >= SECTION_COUNTS[section]:
                break
        if count < SECTION_COUNTS[section]:
            notes.append(f"{section} only selected {count}/{SECTION_COUNTS[section]} verified non-duplicate articles")
    return selected, notes


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
    text = _body(item)
    if _has_any(text, US_TERMS):
        return "美国"
    if _has_any(text, HK_TERMS):
        return "香港"
    low = text.lower()
    if "mica" in low or "esma" in low or "europe" in low or "eu " in low:
        return "欧盟"
    return "其他"


def _key_points_from_row(row: dict[str, Any]) -> list[str]:
    raw = row.get("key_points")
    if isinstance(raw, list):
        return [normalize_punctuation(str(x).strip()) for x in raw if str(x).strip()][:3]
    return []


def _paragraphs_from_row(row: dict[str, Any]) -> list[str]:
    raw = row.get("body_paragraphs")
    if isinstance(raw, list):
        paragraphs = [normalize_punctuation(str(x).strip()) for x in raw if str(x).strip()]
    else:
        paragraphs = []
    if not paragraphs:
        paragraphs = [normalize_punctuation(str(row.get("lead_cn") or row.get("summary_cn") or "-").strip())]
    return paragraphs or ["-"]


def normalize_report(data: dict[str, Any]) -> dict[str, Any]:
    rows = data.get("items") if isinstance(data.get("items"), list) else [data]
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
    return {"items": clean, "notes": [str(x) for x in data.get("notes", []) if x] if isinstance(data, dict) else []}


def _build_translate_prompt(raw: RawItem, section: str) -> list[dict[str, str]]:
    article_text = (getattr(raw, "article_text", "") or "")[:9000]
    para_rule = "6至10个自然段" if section != "意见领袖" else "5至8个自然段"
    payload = {
        "section": section,
        "source_title": raw.title,
        "source_name": raw.source_name,
        "url": raw.url,
        "published_at": raw.published_at,
        "summary": raw.summary,
        "article_text": article_text,
    }
    system = "你是专业新闻翻译编辑。任务是把英文原文忠实翻译成中文，不得添加原文没有的内容。只输出严格 JSON。"
    user = f"""
请将下面英文新闻原文直接翻译编译成中文稿。不是评论，不是分析，不是补写背景。
硬性要求：
1. 只能翻译 article_text 和 summary 中已经出现的信息；不得新增未出现的机构、数字、日期、观点、预测、市场反应、监管后续安排或因果判断。
2. 保留原文事实顺序和限定语，宁可少写，也不要扩写。
3. 正文写成{para_rule}，每段只表达原文中的事实或原文明确观点。
4. 关键点 1至3条，也必须来自原文。
5. 专业术语首次出现写“中文（English，缩写）”；英文人名不翻译，首次写 Firstname Lastname，此后写 Lastname。
6. 使用全角中文标点和中文全角引号，不使用半角引号。URL 必须原样输出。
7. fact_check 写明“逐段翻译自原文”，并说明没有加入来源外内容。
输出 JSON：{{"section":"{section}","title_cn":"中文标题","source_title":"英文原题","event_date":"YYYY-MM-DD","key_points":["关键点一"],"lead_cn":"导语","body_paragraphs":["正文第一段","正文第二段"],"source_name":"来源","url":"URL","published_at":"发布时间","region":"地区","fact_check":"核验说明"}}
来源材料 JSON：
{json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _fallback_item(raw: RawItem, section: str) -> dict[str, Any]:
    source_text = normalize_punctuation((getattr(raw, "article_text", "") or raw.summary or raw.title)[:3200])
    paragraphs = [source_text[i : i + 420] for i in range(0, min(len(source_text), 2520), 420)] or [source_text]
    return {
        "section": section,
        "title_cn": clean_title(raw.title),
        "source_title": raw.title,
        "event_date": (raw.published_at or "")[:10] or "-",
        "key_points": ["该条为原文正文自动切分草稿，发布前需人工逐段核对。"],
        "lead_cn": paragraphs[0][:220],
        "body_paragraphs": paragraphs,
        "source_name": raw.source_name,
        "url": raw.url,
        "published_at": raw.published_at,
        "region": _infer_region(raw),
        "fact_check": "fallback 草稿，仅使用已抓取原文正文。",
    }


def _compile_one(raw: RawItem, section: str) -> dict[str, Any]:
    if not os.getenv("DEEPSEEK_API_KEY"):
        return _fallback_item(raw, section)
    try:
        data = _extract_json(_chat(_build_translate_prompt(raw, section), timeout=240))
        rows = normalize_report(data)["items"]
        item = rows[0] if rows else _fallback_item(raw, section)
    except Exception as exc:
        LOGGER.warning("DeepSeek translation failed, using source-text fallback: %s", exc)
        item = _fallback_item(raw, section)
    item["section"] = section
    item["url"] = raw.url
    item["source_title"] = raw.title
    item["source_name"] = raw.source_name
    item["published_at"] = raw.published_at
    item["region"] = item.get("region") or _infer_region(raw)
    return item


def compile_report(items: list[RawItem], start_label: str, end_label: str) -> dict[str, Any]:
    selected, notes = _select_items_by_section(items)
    if not selected:
        return {"items": [], "notes": ["No verified non-duplicate source articles."]}
    compiled: list[dict[str, Any]] = []
    for raw in selected:
        section = raw.section_hint if raw.section_hint in SECTION_ORDER and _section_match(raw, raw.section_hint) else ""
        if not section:
            section = next((s for s in SECTION_ORDER if _section_match(raw, s)), "")
        if not section:
            notes.append(f"skipped item without matching section: {raw.title}")
            continue
        compiled.append(_compile_one(raw, section))
    return {"items": compiled, "notes": notes}
