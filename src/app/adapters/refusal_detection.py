from __future__ import annotations

import re

_SOFT_PATTERNS = [
    r"\bI\s+(?:cannot|can'?t|won'?t|will\s+not|am\s+not\s+able\s+to|do\s+not\s+(?:feel\s+comfortable|wish\s+to))\b",
    r"\bI'?m\s+(?:sorry|unable|not\s+able|afraid|not\s+going\s+to)\b",
    r"\bя\s+не\s+(?:буду|могу|стану|хочу|готов|собираюсь)\b",
    r"\b(?:извин(?:ите|яюсь)|к\s+сожалению),?\s+(?:но\s+)?я\b",
]
_HARD_PATTERNS = [
    r"\bAs\s+an?\s+AI\b",
    r"\bкак\s+(?:ИИ|искусственный\s+интеллект)\b",
    r"\bкак\s+языковая\s+модель\b",
]

_LEN_THRESHOLD = 600
_SCAN_WINDOW = 300

_SOFT = [re.compile(p, re.IGNORECASE) for p in _SOFT_PATTERNS]
_HARD = [re.compile(p, re.IGNORECASE) for p in _HARD_PATTERNS]


def detect_refusal(text: str) -> str | None:
    """Вернуть совпавший фрагмент отказа, если ``text`` похож на отказ LLM, иначе None."""
    if not text:
        return None
    head = text[:_SCAN_WINDOW]
    for pat in _HARD:
        m = pat.search(head)
        if m:
            return m.group(0)
    if len(text) >= _LEN_THRESHOLD:
        return None
    for pat in _SOFT:
        m = pat.search(head)
        if m:
            return m.group(0)
    return None
