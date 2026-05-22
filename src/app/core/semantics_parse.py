from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SemanticsRow:
    keyword_raw: str
    line_no: int
    slug: str | None = None
    title: str | None = None
    page_type: str | None = None
    extras: dict[str, str] = field(default_factory=dict)


_KEY_ALIASES = frozenset({"keyword", "key", "query", "фраза", "ключ"})
_SLUG_ALIASES = frozenset({"slug", "url", "чпу"})
_TITLE_ALIASES = frozenset({"title", "h1", "заголовок"})
_TYPE_ALIASES = frozenset({"page_type", "type", "тип"})


def _norm_key(name: str) -> str:
    return re.sub(r"\s+", "_", name.strip().lower())


def _pick(row: dict[str, str | None], aliases: frozenset[str]) -> str | None:
    for k, v in row.items():
        if v is None:
            continue
        vs = str(v).strip()
        if not vs:
            continue
        if _norm_key(k or "") in aliases:
            return vs
    return None


def parse_semantics_bytes(data: bytes, *, filename_hint: str = "") -> list[SemanticsRow]:
    text = data.decode("utf-8-sig")
    path_hint = filename_hint.lower()
    first_line = text.lstrip()[:2048]
    is_csv = path_hint.endswith(".csv") or ("," in first_line and "\n" in text[:4096])
    if is_csv:
        return _parse_csv(text)
    return _parse_txt_lines(text)


def parse_semantics_path(path: Path) -> list[SemanticsRow]:
    data = path.read_bytes()
    return parse_semantics_bytes(data, filename_hint=path.name)


def _parse_csv(text: str) -> list[SemanticsRow]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return []

    known = _KEY_ALIASES | _SLUG_ALIASES | _TITLE_ALIASES | _TYPE_ALIASES
    out: list[SemanticsRow] = []
    for i, raw in enumerate(reader, start=2):
        kw = _pick(raw, _KEY_ALIASES)
        if kw is None:
            cells = [str(v).strip() for v in raw.values() if v is not None and str(v).strip()]
            kw = cells[0] if cells else ""
        if not kw:
            continue

        slug = _pick(raw, _SLUG_ALIASES)
        title = _pick(raw, _TITLE_ALIASES)
        ptype = _pick(raw, _TYPE_ALIASES)

        extras: dict[str, str] = {}
        for k, v in raw.items():
            nk = _norm_key(k or "")
            if nk in known:
                continue
            if v is not None and str(v).strip():
                extras[nk or (k or "")] = str(v).strip()

        out.append(
            SemanticsRow(
                keyword_raw=kw,
                line_no=i,
                slug=slug or None,
                title=title or None,
                page_type=ptype or None,
                extras=extras,
            ),
        )
    return out


def _parse_txt_lines(text: str) -> list[SemanticsRow]:
    out: list[SemanticsRow] = []
    for i, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "\t" in s:
            parts = [p.strip() for p in s.split("\t")]
            kw = parts[0]
            slug = parts[1] if len(parts) > 1 and parts[1] else None
            title = parts[2] if len(parts) > 2 and parts[2] else None
        else:
            kw, slug, title = s, None, None
        if kw:
            out.append(SemanticsRow(keyword_raw=kw, line_no=i, slug=slug, title=title))
    return out
