from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import requests

from .config import HK_TERMS, SECTION_COUNTS, SECTION_ORDER, US_TERMS
from .sources import RawItem, is_final_url_allowed
from .text_utils import normalize_chinese_punctuation

LOGGER = logging.getLogger(__name__)
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
TITLE_SPLIT_RE = re.compile(r"[，,；;：:—–-]+")
COUNTRY_WORDS = ("美国", "韩国", "英国", "日本", "欧盟", "印度", "泰国", "新加坡", "香港", "澳大利亚", "加拿大", "巴西", "法国", "德国")
FRONTIER_TERMS = ("defi", "layer", "ethereum", "protocol", "blockchain", "upgrade", "launch", "tokenization", "interoperability", "restaking", "rollup", "staking", "wallet", "security", "infrastructure")


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


def _compact_item(item: RawItem) -> dict[str, str]:
    article_text = getattr(item, "article_text", "") or ""
    return {
        "title": item.title[:260],
        "url": item.url[:500],
        "source_name": item.source_name[:120],
        "published_at": item.published_at[:60],
        "summary": item.summary[:700],
        "article_excerpt": article_text[:1600],
        "section_hint": item.section_hint[:40],
        "query": item.query[:180],
    }


def _candidate_items(items: list[RawItem]) -> list[RawItem]:
    return [x for x in items if is_final_url_allowed(x.url) and len(getattr(x, "article_text", "") or "") >= 900]


def _build_selection_prompt(items: list[RawItem], start_label: str, end_label: str) -> list[dict[str, str]]:
    rules = "；".join([f"{name}{count}条" for name, count in SECTION_COUNTS.items()])
    payload = [_compact_item(x) for x in _candidate_items(items)[:120]]
    system = "你是加密货币周刊的选题编辑。只能根据候选英文原文选题，不得补充外部信息。只输出严格 JSON。"
    user = f"""
请为《加密货币观察》从候选中选出本期文章。统计窗口：{start_label} 至 {end_label} 北京时间；新闻发布时间不得早于当前时间一周前。
栏目数量：{rules}。
硬性规则：
1. 只能选择候选 JSON 中给出的文章，url 必须原样复制候选中的 url。
2. 只选择 article_excerpt 明确支持的新闻，不要根据标题猜测。
3. 政策风向优先美国、香港的正式监管动向，3篇不要全是同一地区。
4. 【行业前沿】与【市场动态】采用同一选题标准，优先技术、协议、基础设施、DeFi、Layer 2、代币化、安全、钱包、质押、升级和产品发布，不优先选择 ETF、价格、融资、交易所、并购、资金流等纯市场事件。
5. 排除中文网站和中文来源；尽量分散来源网站。
这里只做选题，不要写正文。标题必须忠实概括原文，不得夸大。
输出 JSON：{{"items":[{{"section":"政策风向","title_cn":"中文标题","source_title":"英文原题","event_date":"YYYY-MM-DD","source_name":"来源","url":"URL","published_at":"发布时间","region":"美国/香港/欧盟/其他","fact_check":"说明候选正文中哪些信息支持该选题"}}],"notes":["..."]}}
候选 JSON：
{json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _build_translate_prompt(row: dict[str, Any], raw: RawItem) -> list[dict[str, str]]:
    section = str(row.get("section") or "")
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
2. 如果原文没有说“公开信”“联合指南”“价格上涨”“计划邀请作证”等内容，绝对不要写。
3. 保留原文事实顺序和限定语，宁可少写，也不要扩写。
4. 正文写成{para_rule}，每段只表达原文中的事实或原文明确观点。
5. 关键点 1至3条，也必须来自原文。
6. 专业术语首次出现写“中文（English，缩写）”；英文人名不翻译，首次写 Firstname Lastname，此后写 Lastname。
7. 使用全角中文标点和中文全角引号，不使用半角引号。URL 必须原样输出。
8. fact_check 写明“逐段翻译自原文”，并说明没有加入来源外内容。
输出 JSON：{{"section":"{section}","title_cn":"中文标题","source_title":"英文原题","event_date":"YYYY-MM-DD","key_points":["关键点一"],"lead_cn":"导语","body_paragraphs":["正文第一段","正文第二段"],"source_name":"来源","url":"URL","published_at":"发布时间","region":"地区","fact_check":"核验说明"}}
来源材料 JSON：
{json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(t.lower() in low for t in terms)


def _section_score(item: RawItem, section: str) -> int:
    text = f"{item.title} {item.summary} {item.query} {item.article_text[:1200]}".lower()
    score = 5 if item.section_hint == section else 0
    section_terms = {
        "政策风向": ("regulation", "sec", "cftc", "treasury", "policy", "law", "enforcement", "mica", "stablecoin", "sfc", "hkma", "guidance", "framework", "rule", "approved", "final"),
        "行业前沿": FRONTIER_TERMS,
        "市场动态": FRONTIER_TERMS,
        "意见领袖": ("says", "opinion", "interview", "ceo", "founder", "analyst", "investor", "predicts"),
    }
    score += sum(1 for term in section_terms.get(section, ()) if term in text)
    if section in ("行业前沿", "市场动态") and any(term in text for term in ("etf", "price", "funding", "raises", "acquisition", "ipo", "exchange", "inflow", "outflow")):
        score -= 2
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
    text = f"{item.title} {item.summary} {item.query} {item.source_name} {item.article_text[:500]}"
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
    safe_items = _candidate_items(items)
    for section in SECTION_ORDER:
        ranked = sorted(safe_items, key=lambda x: _section_score(x, section), reverse=True)
        for item in ranked:
            if len([x for x in selected if x["section"] == section]) >= SECTION_COUNTS[section]:
                break
            if item.url in used_urls or (_section_score(item, section) <= 0 and item.section_hint != section):
                continue
            used_urls.add(item.url)
            source_text = normalize_punctuation((getattr(item, "article_text", "") or item.summary or item.title)[:3000])
            paragraphs = [source_text[i : i + 360] for i in range(0, min(len(source_text), 2160), 360)] or [source_text]
            selected.append({
                "section": section,
                "title_cn": clean_title(item.title),
                "source_title": item.title,
                "event_date": (item.published_at or "")[:10] or "-",
                "key_points": ["该条为原文正文自动切分草稿，发布前需人工逐段核对。"],
                "lead_cn": paragraphs[0][:220],
                "body_paragraphs": paragraphs,
                "source_name": item.source_name,
                "url": item.url,
                "published_at": item.published_at,
                "region": _infer_region(item),
                "fact_check": "fallback 草稿，仅使用已抓取原文正文。",
            })
    return {"items": selected, "notes": ["DeepSeek 未配置或调用失败，已生成逐段原文草稿。"]}


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
    rows = data.get("items") if isinstance(data.get("items"), list) else [data]
    clean: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        section = str(row.get("section", "")).strip()
        if section not in SECTION_ORDER:
            continue
        url = str(row.get("url") or "-").strip()
        clean.append({
            "section": section,
            "title_cn": clean_title(str(row.get("title_cn") or row.get("title") or "-")),
            "source_title": str(row.get("source_title") or "-").strip(),
            "event_date": str(row.get("event_date") or "-").strip(),
            "key_points": _key_points_from_row(row),
            "lead_cn": normalize_punctuation(str(row.get("lead_cn") or row.get("summary_cn") or "-").strip()),
            "body_paragraphs": _paragraphs_from_row(row),
            "source_name": str(row.get("source_name") or "-").strip(),
            "url": url,
            "published_at": str(row.get("published_at") or "-").strip(),
            "region": str(row.get("region") or "其他").strip(),
            "fact_check": normalize_punctuation(str(row.get("fact_check") or "-").strip()),
        })
    return {"items": clean, "notes": [str(x) for x in data.get("notes", []) if x] if isinstance(data, dict) else []}


def _find_raw(row: dict[str, Any], items: list[RawItem]) -> RawItem | None:
    url = str(row.get("url") or "").strip()
    title = str(row.get("source_title") or row.get("title_cn") or "").lower()
    for item in items:
        if url and item.url == url and is_final_url_allowed(item.url) and item.article_text:
            return item
    for item in items:
        if title and is_final_url_allowed(item.url) and item.article_text and (title in item.title.lower() or item.title.lower() in title):
            return item
    return None


def _expand_selected_report(selected: dict[str, Any], items: list[RawItem]) -> dict[str, Any]:
    expanded: list[dict[str, Any]] = []
    notes = list(selected.get("notes", [])) if isinstance(selected.get("notes"), list) else []
    for row in selected.get("items", []):
        if not isinstance(row, dict):
            continue
        raw = _find_raw(row, items)
        if raw is None:
            notes.append(f"skipped item without verified source text: {row.get('title_cn')}")
            continue
        try:
            data = _extract_json(_chat(_build_translate_prompt(row, raw), timeout=240))
            one = normalize_report(data)["items"]
            if one:
                item = one[0]
                item["url"] = raw.url
                item["source_title"] = raw.title
                item["source_name"] = raw.source_name
                item["published_at"] = raw.published_at
                expanded.append(item)
        except Exception as exc:
            LOGGER.warning("DeepSeek item translation failed, using source-text fallback: %s", exc)
            normalized = normalize_report({"items": [_fallback([raw])["items"][0]]})["items"]
            if normalized:
                expanded.append(normalized[0])
            notes.append(f"item translation failed: {row.get('title_cn')}")
    return {"items": expanded, "notes": notes}


def compile_report(items: list[RawItem], start_label: str, end_label: str) -> dict[str, Any]:
    safe_items = _candidate_items(items)
    if not safe_items:
        return {"items": [], "notes": ["No verified source articles with reachable original URLs and body text."]}
    if not os.getenv("DEEPSEEK_API_KEY"):
        return normalize_report(_fallback(safe_items))
    try:
        selected = normalize_report(_extract_json(_chat(_build_selection_prompt(safe_items, start_label, end_label), timeout=240)))
        return _expand_selected_report(selected, safe_items)
    except Exception as exc:
        LOGGER.warning("DeepSeek compile failed, using fallback: %s", exc)
        return normalize_report(_fallback(safe_items))
