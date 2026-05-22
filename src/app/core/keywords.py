from __future__ import annotations

import hashlib
import unicodedata


def normalize_keyword(raw: str) -> str:
    """Обрезать пробелы, привести к NFC unicode и регистронезависимому виду (Unicode case fold)."""
    s = unicodedata.normalize("NFC", raw.strip())
    return s.casefold()


def keyword_sha256_hex(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def keyword_hash_from_raw(raw: str) -> tuple[str, str]:
    """Вернуть ``(normalized, sha256_hex)``."""
    n = normalize_keyword(raw)
    return n, keyword_sha256_hex(n)
