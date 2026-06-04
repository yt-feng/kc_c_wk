from __future__ import annotations

import re

PUNCT_MAP = str.maketrans({",": "，", ";": "；", ":": "：", "?": "？", "!": "！"})
URL_RE = re.compile(r"https?://[^\s）)】>]+")


def normalize_fullwidth_quotes(text: str) -> str:
    value = str(text or "")
    result = []
    open_double = True
    open_single = True
    for idx, ch in enumerate(value):
        if ch == chr(34):
            result.append("“" if open_double else "”")
            open_double = not open_double
        elif ch == chr(39):
            prev_ch = value[idx - 1] if idx > 0 else ""
            next_ch = value[idx + 1] if idx + 1 < len(value) else ""
            keep_apostrophe = prev_ch.isascii() and prev_ch.isalnum() and next_ch.isascii() and next_ch.isalnum()
            if keep_apostrophe:
                result.append(ch)
            else:
                result.append("‘" if open_single else "’")
                open_single = not open_single
        else:
            result.append(ch)
    return "".join(result)


def _normalize_non_url_text(text: str) -> str:
    return normalize_fullwidth_quotes(str(text or "").translate(PUNCT_MAP))


def normalize_chinese_punctuation(text: str) -> str:
    """Normalize Chinese punctuation while preserving raw URL syntax.

    URLs must keep ASCII ``https://`` and query-string punctuation; otherwise
    Word output can turn links into invalid strings such as ``https：//``.
    """
    value = str(text or "")
    parts: list[str] = []
    last = 0
    for match in URL_RE.finditer(value):
        parts.append(_normalize_non_url_text(value[last : match.start()]))
        parts.append(match.group(0))
        last = match.end()
    parts.append(_normalize_non_url_text(value[last:]))
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def has_half_width_quotes(text: str) -> bool:
    value = str(text or "")
    if chr(34) in value:
        return True
    for idx, ch in enumerate(value):
        if ch != chr(39):
            continue
        prev_ch = value[idx - 1] if idx > 0 else ""
        next_ch = value[idx + 1] if idx + 1 < len(value) else ""
        if not (prev_ch.isascii() and prev_ch.isalnum() and next_ch.isascii() and next_ch.isalnum()):
            return True
    return False
