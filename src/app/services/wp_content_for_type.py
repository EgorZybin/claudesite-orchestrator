from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.core.llm_provider_factory import make_text_llm
from app.services.theme_manifest import AcfFieldDef, PostTypeDef, post_type as get_post_type

logger = logging.getLogger(__name__)


class TypedContentDraft(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    slug: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    meta_description: str = Field(min_length=60, max_length=320)
    content_html: str = Field(default="", description="HTML для post_content. Может быть пустым для типов с rich ACF (faq, team_member).")
    acf: dict[str, Any] = Field(default_factory=dict)


_SYSTEM = (
    "You are a Russian-language content writer publishing into a structured "
    "WordPress site (claudesite-theme). You receive a post_type schema and a "
    "topic — you output a JSON draft matching that schema. Output STRICT JSON "
    "only, no markdown fences, no commentary."
)


def _format_acf_schema(fields: list[AcfFieldDef]) -> str:
    lines = []
    for f in fields:
        constraint = ""
        if f.type == "text" and f.max_length:
            constraint = f" (макс {f.max_length} симв.)"
        elif f.type == "textarea" and f.max_length:
            constraint = f" (макс {f.max_length} симв.)"
        elif f.type == "number":
            constraint = " (целое число)"
        elif f.type == "true_false":
            constraint = " (true/false)"
        elif f.type == "select" and f.choices:
            opts = " | ".join(f.choices.keys())
            constraint = f" (одно из: {opts})"
        elif f.type == "url":
            constraint = " (полный URL или относительный путь типа /contacts/)"
        elif f.type == "email":
            constraint = " (email)"

        lines.append(f"- `{f.name}` ({f.type}){constraint}: {f.description}")
    return "\n".join(lines) or "(нет ACF-полей)"


def _build_prompt(*, topic: str, pt_def: PostTypeDef, brand: str | None = None, language: str = "ru") -> str:
    schema_block = _format_acf_schema(pt_def.acf_fields)
    brand_line = f"Бренд: {brand}\n" if brand else ""

    return f"""Сгенерируй контент для {pt_def.label.upper()} в WordPress. Output JSON ONLY.

ТЕМА: {topic}

{brand_line}ТИП КОНТЕНТА: {pt_def.label} (post_type={pt_def.slug})
ОПИСАНИЕ ТИПА: {pt_def.description}
КАК РЕНДЕРИТСЯ ШАБЛОНОМ: {pt_def.template_hint}

ACF-СХЕМА (заполни ВСЕ поля если применимо к теме; необязательные оставь пустыми):
{schema_block}

ФОРМАТ ОТВЕТА:
{{
  "title": "post_title (40-100 симв.)",
  "slug": "latin-kebab-case-from-title",
  "meta_description": "80-320 симв. для SEO (Yoast)",
  "content_html": "<HTML для post_content. Используй <h2>, <p>, <ul>/<li>, <blockquote>. БЕЗ <h1> (уже есть title). БЕЗ inline-стилей. БЕЗ внешних ссылок.>",
  "acf": {{
    "<field_name>": <значение_строго_типа_из_схемы>,
    ...
  }}
}}

ПРАВИЛА:
- Язык: {language}.
- title — без кликбейта, без EMOJI, по делу.
- slug — латиница kebab-case, отражает суть title.
- meta_description — фактическая суть для SERP.
- content_html — реальный полезный контент с конкретными фактами/числами/примерами.
  Структура: intro (1 абзац) → 2-4 H2-секции → выводы.
- acf-поля — заполни КАЖДОЕ согласно описанию. Числа = integers (не строки).
  Для true_false передавай true/false (boolean). Для select — точный slug из choices.
  Для url — относительный путь (/contacts/) или полный URL.
  Для textarea с «(по строке)» — единая строка с \\n между пунктами.
- НЕ выдумывай ссылки на внешние сайты.
- НЕ начинай с «В современном мире», «Сегодня», «Многие».
"""


_FENCE_RX = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)
_FENCE_END_RX = re.compile(r"\s*```\s*$")


def _extract_json(raw: str) -> dict:
    t = raw.strip()
    if t.startswith("```"):
        t = _FENCE_RX.sub("", t)
        t = _FENCE_END_RX.sub("", t)
    if not t.startswith("{"):
        s = t.find("{")
        if s == -1:
            raise ValueError(f"no JSON: head={raw[:200]!r}")
        t = t[s:]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json
            return json.loads(repair_json(t))
        except Exception as exc:
            raise ValueError(f"JSON parse failed: {exc}; head={raw[:200]!r}") from exc


def _coerce_acf_value(value: Any, field_def: AcfFieldDef) -> Any:
    """Приводит LLM-значение к ожидаемому ACF-типу."""
    if value is None or value == "":
        return ""
    if field_def.type == "number":
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return ""
    if field_def.type == "true_false":
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"true", "1", "yes", "да"}
    return value


def generate_for_post_type(
    *,
    post_type_slug: str,
    topic: str,
    brand: str | None = None,
    language: str = "ru",
) -> TypedContentDraft:
    """Сгенерировать черновик для конкретного post_type'а из manifest'а."""
    if not topic or not topic.strip():
        raise ValueError("topic must be non-empty")

    pt_def = get_post_type(post_type_slug)
    settings = get_settings()
    llm = make_text_llm(settings)

    prompt = _build_prompt(topic=topic.strip(), pt_def=pt_def, brand=brand, language=language)
    raw = llm.generate(prompt=prompt, system=_SYSTEM)
    data = _extract_json(raw)

    acf_raw = data.get("acf", {}) if isinstance(data, dict) else {}
    if not isinstance(acf_raw, dict):
        acf_raw = {}
    acf_coerced: dict[str, Any] = {}
    by_name = {f.name: f for f in pt_def.acf_fields}
    for k, v in acf_raw.items():
        if k in by_name:
            acf_coerced[k] = _coerce_acf_value(v, by_name[k])
    data["acf"] = acf_coerced

    try:
        draft = TypedContentDraft.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"draft schema invalid: {e}") from e
    logger.info(
        "typed_content_drafted post_type=%s title=%s slug=%s acf_keys=%d",
        post_type_slug, draft.title[:60], draft.slug, len(draft.acf),
    )
    return draft
