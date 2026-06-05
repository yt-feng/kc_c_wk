from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections import Counter
from typing import Any

import requests

from .config import HK_TERMS, SECTION_COUNTS, SECTION_ORDER, US_TERMS
from .sources import RawItem, host, is_final_url_allowed, title_key
from .text_utils import normalize_chinese_punctuation

LOGGER = logging.getLogger(__name__)
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
TITLE_SPLIT_RE = re.compile(r"[，,；;：:—–-]+")
COUNTRY_WORDS = ("美国", "韩国", "英国", "日本", "欧盟", "印度", "泰国", "新加坡", "香港", "澳大利亚", "加拿大", "巴西", "法国", "德国", "阿联酋", "以色列")
POLICY_TERMS = ("regulation", "regulatory", "regulator", "sec", "cftc", "treasury", "fincen", "ofac", "federal reserve", "congress", "senate", "house", "fca", "bank of england", "sfc", "hkma", "esma", "mica", "law", "act", "bill", "rule", "guidance", "framework", "license", "licence", "consultation", "court", "approved", "issued", "passed", "final")
FRONTIER_TERMS = ("ethereum", "solana", "chainlink", "protocol", "mainnet", "testnet", "upgrade", "glamsterdam", "pectra", "fusaka", "alpenglow", "rollup", "layer 2", "oracle", "cross-chain", "interoperability", "tokenized treasury", "tokenisation", "tokenization", "rwa", "smart contract", "wallet", "staking", "settlement", "validator", "infrastructure", "defi")
MARKET_TERMS = ("raises", "funding", "fund", "venture", "ipo", "files", "acquisition", "acquire", "merger", "stake", "investment", "revenue", "earnings", "volume", "supply", "adoption", "futures", "etf", "exchange", "payment", "prediction market", "polymarket", "kalshi", "institutional")
OPINION_TERMS = ("said", "says", "told", "argued", "warned", "expects", "believes", "according to", "interview", "opinion", "analyst", "ceo", "founder", "cio", "chair", "president", "governor", "economist", "investor", "executive")
BAD_TEXT_TERMS = ("permission is hereby granted", "the software is provided", "mit license", "angular.dev/license", "@font-face", "font-family", "fonts.gstatic.com", "fonts.googleapis.com", "stylesheet", "skip to main content menu", "enable javascript", "accept cookies to continue")
DISCOVERY_SOURCE_NAMES = {"Bing News", "Google News", "GDELT"}

# These phrases were the source of unsupported additions in generated drafts.
# They are allowed only when the English source explicitly contains a matching attribution/context.
HARD_UNSUPPORTED_PHRASES = (
    "未决问题", "整体来看", "这一立法动向反映出", "从更广阔的市场视角看", "未来数周", "仍需后续观察",
    "正成为不可忽视", "表明美国政府对", "这至少表明", "可能引发管辖权重叠", "将面临更严格的合规要求",
)
CONDITIONAL_ATTRIBUTION_RULES = (
    ("业内人士", ("industry", "market participant", "market participants", "trader", "traders", "业内")),
    ("分析师认为", ("analyst", "analysts", "分析师")),
    ("分析师指出", ("analyst", "analysts", "分析师")),
    ("市场观察人士", ("market observer", "market observers", "observers")),
    ("投资者认为", ("investor", "investors")),
)
QUESTION_PHRASES = ("能否", "是否能够", "是否会", "会否", "是否可以")


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def _chat(messages: list[dict[str, str]], timeout: int = 300) -> str:
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
    return any(term.lower() in low for term in terms)


def _count_terms(text: str, terms: tuple[str, ...]) -> int:
    low = text.lower()
    return sum(1 for term in terms if term.lower() in low)


def _body(item: RawItem) -> str:
    return f"{item.title} {item.summary} {item.query} {getattr(item, 'article_text', '')}"


def _source_text(raw: RawItem) -> str:
    return f"{raw.title}\n{raw.summary}\n{getattr(raw, 'article_text', '')}"


def _text_fp(item: RawItem) -> str:
    text = re.sub(r"\W+", "", (getattr(item, "article_text", "") or "").lower())[:2200]
    return hashlib.sha1(text.encode("utf-8")).hexdigest() if text else ""


def _safe_candidate(item: RawItem) -> bool:
    text = _body(item).lower()
    if not is_final_url_allowed(item.url) or item.source_name in DISCOVERY_SOURCE_NAMES:
        return False
    if len(getattr(item, "article_text", "") or "") < 700:
        return False
    if _has_any(text, BAD_TEXT_TERMS):
        return False
    if host(item.url) in {"angular.dev", "fonts.googleapis.com", "fonts.gstatic.com"}:
        return False
    return not ("compound" in text and "angular" in text)


def _section_match(item: RawItem, section: str) -> bool:
    text = _body(item).lower()
    if not _safe_candidate(item):
        return False
    if section == "政策风向":
        return _count_terms(text, POLICY_TERMS) >= 2
    if section == "行业前沿":
        return _count_terms(text, FRONTIER_TERMS) >= 2
    if section == "市场动态":
        return _count_terms(text, MARKET_TERMS) >= 1 or (_count_terms(text, FRONTIER_TERMS) >= 2 and any(x in text for x in ("launch", "adoption", "settlement", "payment")))
    if section == "意见领袖":
        return _count_terms(text, OPINION_TERMS) >= 1
    return False


def _section_score(item: RawItem, section: str) -> int:
    text = _body(item).lower()
    score = 8 if item.section_hint == section else 0
    terms = {"政策风向": POLICY_TERMS, "行业前沿": FRONTIER_TERMS, "市场动态": MARKET_TERMS, "意见领袖": OPINION_TERMS}.get(section, ())
    score += _count_terms(text, terms) * 2
    if section == "政策风向" and (_has_any(text, US_TERMS) or _has_any(text, HK_TERMS)):
        score += 8
    if section == "政策风向" and any(x in text for x in ("approved", "issued", "passed", "adopted", "signed", "final", "effective", "court", "bill", "act", "law", "guidance", "consultation")):
        score += 6
    if section == "行业前沿" and any(x in text for x in ("upgrade", "mainnet", "validator", "settlement", "tokenized treasury", "cross-chain", "infrastructure", "launch")):
        score += 6
    if section == "市场动态" and any(x in text for x in ("acquire", "funding", "ipo", "revenue", "futures", "etf", "adoption", "prediction market")):
        score += 6
    if section == "意见领袖" and any(x in text for x in ("interview", "said", "told", "warned", "argued")):
        score += 6
    if len(getattr(item, "article_text", "") or "") > 2500:
        score += 2
    return score


def _candidate_payload(items: list[RawItem]) -> tuple[list[dict[str, Any]], dict[str, RawItem]]:
    payload, id_map = [], {}
    for idx, item in enumerate(items):
        if not _safe_candidate(item):
            continue
        possible = [section for section in SECTION_ORDER if _section_match(item, section)]
        if not possible and len(getattr(item, "article_text", "") or "") < 2000:
            continue
        cid = f"A{idx:03d}"
        id_map[cid] = item
        payload.append({
            "id": cid,
            "title": item.title[:260],
            "url": item.url[:500],
            "source_name": item.source_name[:120],
            "published_at": item.published_at[:80],
            "summary": item.summary[:850],
            "article_excerpt": (getattr(item, "article_text", "") or "")[:1800],
            "section_hint": item.section_hint,
            "possible_sections": possible,
            "domain": host(item.url),
            "scores": {section: _section_score(item, section) for section in SECTION_ORDER},
        })
    return payload, id_map


def _build_selection_prompt(candidates: list[dict[str, Any]], start_label: str, end_label: str) -> list[dict[str, str]]:
    rules = "；".join(f"{section}{SECTION_COUNTS[section]}篇" for section in SECTION_ORDER)
    system = "你是《加密货币观察》的资深中文编辑。你只从候选英文原文中选题，不能杜撰候选之外的信息。只输出严格 JSON。"
    user = f"""
请按照样刊标准选择本期《加密货币观察》文章。统计窗口：{start_label} 至 {end_label}（北京时间）。栏目数量：{rules}。
【政策风向】选监管、立法、法院、官方指南、牌照、正式征询或明确政策进展，优先美国、香港但地区要分散，至少一篇美国。
【行业前沿】选协议升级、代币化结算、DeFi、RWA、跨链、预言机、钱包、安全、验证者、支付基础设施等技术/产品进展。
【市场动态】选融资、并购、IPO、交易产品、机构采用、收入、稳定币供给、预测市场、交易所和市场基础设施等商业动态，避免纯价格预测。
【意见领袖】必须体现人物或机构观点，能写出“XXX认为/指出/表示/警告”。
不要选重复主题、CSS/许可证/字体页、价格预测软文、中文来源、搜索引擎包装页。最终只可使用候选 id。
输出 JSON：{{"items":[{{"id":"A000","section":"政策风向","editor_reason":"原因"}}],"notes":["..."]}}
候选 JSON：{json.dumps(candidates[:180], ensure_ascii=False, separators=(",", ":"))}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _dedupe_selected(rows: list[dict[str, Any]], id_map: dict[str, RawItem]) -> tuple[list[tuple[str, RawItem]], list[str]]:
    selected, notes = [], []
    used_urls, used_titles, used_texts = set(), set(), set()
    counts: Counter[str] = Counter()
    for row in rows:
        cid, section = str(row.get("id") or ""), str(row.get("section") or "")
        item = id_map.get(cid)
        if not item or section not in SECTION_ORDER or counts[section] >= SECTION_COUNTS[section]:
            continue
        url_key, title, fp = item.url.strip().lower(), title_key(item.title), _text_fp(item)
        if url_key in used_urls or (title and title in used_titles) or (fp and fp in used_texts):
            notes.append(f"deduped selection: {item.title}")
            continue
        if not _section_match(item, section) and len(getattr(item, "article_text", "") or "") < 2000:
            notes.append(f"section mismatch skipped: {section}/{item.title}")
            continue
        selected.append((section, item))
        counts[section] += 1
        used_urls.add(url_key)
        if title:
            used_titles.add(title)
        if fp:
            used_texts.add(fp)
    return selected, notes


def _fallback_select(items: list[RawItem]) -> tuple[list[tuple[str, RawItem]], list[str]]:
    selected, notes = [], ["DeepSeek selection unavailable; used deterministic scoring fallback."]
    used_urls, used_titles, used_texts = set(), set(), set()
    safe_items = [x for x in items if _safe_candidate(x)]
    for section in SECTION_ORDER:
        candidates = [x for x in safe_items if _section_match(x, section)]
        candidates.sort(key=lambda x: _section_score(x, section), reverse=True)
        for item in candidates:
            if len([x for x in selected if x[0] == section]) >= SECTION_COUNTS[section]:
                break
            url_key, title, fp = item.url.strip().lower(), title_key(item.title), _text_fp(item)
            if url_key in used_urls or (title and title in used_titles) or (fp and fp in used_texts):
                continue
            selected.append((section, item))
            used_urls.add(url_key)
            if title:
                used_titles.add(title)
            if fp:
                used_texts.add(fp)
    return selected, notes


def clean_title(title: str) -> str:
    value = re.sub(r"\s+", "", str(title or "")).strip(" ，,；;：:。.!！?？—–-")
    if not value:
        return "-"
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
        else:
            value = first + second
    return normalize_chinese_punctuation(TITLE_SPLIT_RE.sub("", value).strip(" ，,；;：:。.!！?？—–-")) or "-"


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


def _sentence_list(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[。！？；])", text or "") if x.strip()]


def _unsupported_sentence(sentence: str, raw: RawItem) -> bool:
    source = _source_text(raw).lower()
    if any(phrase in sentence for phrase in HARD_UNSUPPORTED_PHRASES):
        return True
    for phrase, source_markers in CONDITIONAL_ATTRIBUTION_RULES:
        if phrase in sentence and not any(marker in source for marker in source_markers):
            return True
    if any(phrase in sentence for phrase in QUESTION_PHRASES) and not any(marker in source for marker in ("whether", "question", "unclear", "uncertain", "remains to be seen", "?")):
        return True
    return False


def _remove_unsupported_sentences(text: str, raw: RawItem) -> str:
    sentences = _sentence_list(text)
    if not sentences:
        return text
    kept = [s for s in sentences if not _unsupported_sentence(s, raw)]
    return "".join(kept).strip()


def _key_points_from_row(row: dict[str, Any], raw: RawItem | None = None) -> list[str]:
    raw_points = row.get("key_points")
    points = [normalize_chinese_punctuation(str(x).strip()) for x in raw_points if str(x).strip()] if isinstance(raw_points, list) else []
    if raw is not None:
        points = [_remove_unsupported_sentences(x, raw) for x in points]
        points = [x for x in points if x]
    return points[:3]


def _paragraphs_from_row(row: dict[str, Any], raw: RawItem | None = None) -> list[str]:
    raw_paragraphs = row.get("body_paragraphs")
    paragraphs = [normalize_chinese_punctuation(str(x).strip()) for x in raw_paragraphs if str(x).strip()] if isinstance(raw_paragraphs, list) else []
    if raw is not None:
        paragraphs = [_remove_unsupported_sentences(x, raw) for x in paragraphs]
        paragraphs = [x for x in paragraphs if x]
    if not paragraphs:
        fallback = normalize_chinese_punctuation(str(row.get("lead_cn") or row.get("summary_cn") or "-").strip())
        if raw is not None:
            fallback = _remove_unsupported_sentences(fallback, raw)
        paragraphs = [fallback or "-"]
    return paragraphs or ["-"]


def normalize_report(data: dict[str, Any], raw: RawItem | None = None) -> dict[str, Any]:
    rows = data.get("items") if isinstance(data.get("items"), list) else [data]
    clean = []
    for row in rows:
        if not isinstance(row, dict) or str(row.get("section", "")).strip() not in SECTION_ORDER:
            continue
        clean.append({
            "section": str(row.get("section", "")).strip(),
            "title_cn": clean_title(str(row.get("title_cn") or row.get("title") or "-")),
            "source_title": str(row.get("source_title") or "-").strip(),
            "event_date": str(row.get("event_date") or "-").strip(),
            "key_points": _key_points_from_row(row, raw=raw),
            "lead_cn": normalize_chinese_punctuation(str(row.get("lead_cn") or "").strip()),
            "body_paragraphs": _paragraphs_from_row(row, raw=raw),
            "source_name": str(row.get("source_name") or "-").strip(),
            "url": str(row.get("url") or "-").strip(),
            "published_at": str(row.get("published_at") or "-").strip(),
            "region": str(row.get("region") or "其他").strip(),
            "fact_check": normalize_chinese_punctuation(str(row.get("fact_check") or "-").strip()),
        })
    return {"items": clean, "notes": [str(x) for x in data.get("notes", []) if x] if isinstance(data, dict) else []}


def _build_translate_prompt(raw: RawItem, section: str) -> list[dict[str, str]]:
    paragraph_rule = "7至10个自然段" if section != "意见领袖" else "6至9个自然段"
    payload = {"section": section, "source_title": raw.title, "source_name": raw.source_name, "url": raw.url, "published_at": raw.published_at, "summary": raw.summary, "article_text": (getattr(raw, "article_text", "") or "")[:12000]}
    system = "你是《加密货币观察》的中文编译编辑。你需要写出与样刊一致的专业中文周刊稿，但只能忠实编译原文。只输出严格 JSON。"
    user = f"""
请基于英文原文，为【{section}】栏目编译一篇中文稿。对齐样刊风格，但必须逐条忠实于来源链接。
硬性要求：
1. 只能使用 article_text 和 summary 中明确出现的信息；不得添加来源外事实、推断、预测、行业评论、监管影响或未决问题。
2. 正文写成{paragraph_rule}，每段约120至240字；可以重组原文顺序，但每一句都必须能在原文中找到直接依据。
3. 开头输出2至3条关键点；关键点也必须来自原文，不能写“分析师认为”“业内人士指出”，除非原文有对应分析师或业内人士归属。
4. 不要自动补写“未决问题”“整体来看”“业内人士指出”“这表明……”“未来数周……仍需观察”等总结性段落。
5. 如果原文没有提出问题，不要写“能否/是否/会否”等疑问句；如果原文没有监管重叠或更严格合规要求，不要写相关判断。
6. 【意见领袖】应体现观点归属，但只能使用原文出现的人名、机构名和观点。
7. 专业术语首次出现写“中文（English，缩写）”；英文人名不翻译；使用全角中文标点和全角引号；URL原样输出。
8. fact_check 必须写明“逐段对照原文删除未支撑内容”。
输出 JSON：{{"section":"{section}","title_cn":"中文标题","source_title":"英文原题","event_date":"YYYY-MM-DD或空","key_points":["关键点一"],"lead_cn":"可为空","body_paragraphs":["正文第一段"],"source_name":"来源","url":"URL","published_at":"发布时间","region":"地区","fact_check":"核验说明"}}
来源材料 JSON：{json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _build_verify_prompt(raw: RawItem, section: str, item: dict[str, Any]) -> list[dict[str, str]]:
    payload = {
        "source_title": raw.title,
        "source_name": raw.source_name,
        "url": raw.url,
        "summary": raw.summary,
        "article_text": (getattr(raw, "article_text", "") or "")[:14000],
        "draft": item,
    }
    system = "你是严格事实核验编辑。你的任务是删除不受原文支持的中文句子，不是润色扩写。只输出严格 JSON。"
    user = f"""
请对照英文原文核验中文稿。规则：
1. draft 中任何不能被 article_text 或 summary 直接支持的句子，必须删除或改写为原文直接支持的表述。
2. 特别删除：未决问题、整体评价、行业评论、监管影响推断、合规要求推断、未来走势、来源中没有主体的“分析师认为/业内人士指出”。
3. 不要新增任何事实或判断，不要补写背景。
4. 保留原 JSON 结构，输出修订后的同一篇文章。
输出 JSON：{{"section":"{section}","title_cn":"中文标题","source_title":"英文原题","event_date":"YYYY-MM-DD或空","key_points":["关键点一"],"lead_cn":"可为空","body_paragraphs":["正文第一段"],"source_name":"来源","url":"URL","published_at":"发布时间","region":"地区","fact_check":"逐句对照原文核验，已删除未支撑内容"}}
核验材料 JSON：{json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _fallback_item(raw: RawItem, section: str) -> dict[str, Any]:
    source_text = normalize_chinese_punctuation((getattr(raw, "article_text", "") or raw.summary or raw.title)[:4200])
    paragraphs = [source_text[i : i + 420] for i in range(0, min(len(source_text), 2940), 420)] or [source_text]
    return {"section": section, "title_cn": clean_title(raw.title), "source_title": raw.title, "event_date": (raw.published_at or "")[:10] or "-", "key_points": ["该条为原文正文自动切分草稿，发布前需人工逐段核对。"], "lead_cn": "", "body_paragraphs": paragraphs, "source_name": raw.source_name, "url": raw.url, "published_at": raw.published_at, "region": _infer_region(raw), "fact_check": "fallback 草稿，仅使用已抓取原文正文。"}


def _compile_one(raw: RawItem, section: str) -> dict[str, Any]:
    if not os.getenv("DEEPSEEK_API_KEY"):
        item = _fallback_item(raw, section)
    else:
        try:
            rows = normalize_report(_extract_json(_chat(_build_translate_prompt(raw, section), timeout=320)), raw=raw)["items"]
            item = rows[0] if rows else _fallback_item(raw, section)
            try:
                verified_rows = normalize_report(_extract_json(_chat(_build_verify_prompt(raw, section, item), timeout=260)), raw=raw)["items"]
                if verified_rows:
                    item = verified_rows[0]
            except Exception as verify_exc:
                LOGGER.warning("DeepSeek verification failed, using post-processed draft: %s", verify_exc)
        except Exception as exc:
            LOGGER.warning("DeepSeek translation failed, using fallback: %s", exc)
            item = _fallback_item(raw, section)
    item.update({"section": section, "url": raw.url, "source_title": raw.title, "source_name": raw.source_name, "published_at": raw.published_at})
    item["region"] = item.get("region") or _infer_region(raw)
    item["key_points"] = _key_points_from_row(item, raw=raw)
    item["body_paragraphs"] = _paragraphs_from_row(item, raw=raw)
    item["fact_check"] = "逐句对照原文核验，已删除未支撑内容。"
    return item


def _select_with_model(items: list[RawItem], start_label: str, end_label: str) -> tuple[list[tuple[str, RawItem]], list[str]]:
    candidates, id_map = _candidate_payload(items)
    if not candidates:
        return [], ["No safe candidates after source filtering."]
    data = _extract_json(_chat(_build_selection_prompt(candidates, start_label, end_label), timeout=300))
    rows = data.get("items") if isinstance(data.get("items"), list) else []
    selected, notes = _dedupe_selected(rows, id_map)
    if isinstance(data.get("notes"), list):
        notes.extend(str(x) for x in data.get("notes", []) if x)
    return selected, notes


def _fill_missing_sections(selected: list[tuple[str, RawItem]], all_items: list[RawItem], notes: list[str]) -> list[tuple[str, RawItem]]:
    used_urls = {item.url.strip().lower() for _, item in selected}
    used_titles = {title_key(item.title) for _, item in selected if title_key(item.title)}
    used_texts = {_text_fp(item) for _, item in selected if _text_fp(item)}
    counts = Counter(section for section, _ in selected)
    safe_items = [x for x in all_items if _safe_candidate(x)]
    for section in SECTION_ORDER:
        candidates = [x for x in safe_items if _section_match(x, section)]
        candidates.sort(key=lambda x: _section_score(x, section), reverse=True)
        for item in candidates:
            if counts[section] >= SECTION_COUNTS[section]:
                break
            url_key, title, fp = item.url.strip().lower(), title_key(item.title), _text_fp(item)
            if url_key in used_urls or (title and title in used_titles) or (fp and fp in used_texts):
                continue
            selected.append((section, item)); counts[section] += 1; used_urls.add(url_key)
            if title: used_titles.add(title)
            if fp: used_texts.add(fp)
        if counts[section] < SECTION_COUNTS[section]:
            notes.append(f"{section} only selected {counts[section]}/{SECTION_COUNTS[section]} verified non-duplicate articles")
    return selected


def compile_report(items: list[RawItem], start_label: str, end_label: str) -> dict[str, Any]:
    if not items:
        return {"items": [], "notes": ["No source items collected."]}
    try:
        selected, notes = _select_with_model(items, start_label, end_label) if os.getenv("DEEPSEEK_API_KEY") else _fallback_select(items)
    except Exception as exc:
        LOGGER.warning("Selection failed, using fallback: %s", exc)
        selected, notes = _fallback_select(items)
    selected = _fill_missing_sections(selected, items, notes)
    return {"items": [_compile_one(raw, section) for section, raw in selected], "notes": notes}
