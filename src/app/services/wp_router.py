from __future__ import annotations

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.adapters.errors import AdapterError
from app.core.config import get_settings
from app.core.llm_provider_factory import make_text_llm
from app.core.site_config_schema import WpIntrospectionSpec

logger = logging.getLogger(__name__)


class WpAction(BaseModel):
    """Routed action: всё, что нужно pipeline'у для одной публикации."""
    post_type: str = Field(min_length=1, max_length=64)
    post_status: Literal["publish", "draft", "pending", "private"] = "publish"
    topic: str = Field(min_length=3, max_length=500)
    taxonomy: str | None = None
    term_slug: str | None = None
    template: str | None = None
    extra_postmeta: dict[str, str] = Field(default_factory=dict)
    rationale: str = Field(default="", max_length=500)


_SYSTEM = (
    "You are routing a natural-language publishing instruction to a WordPress "
    "site. Given the site's structure (post_types, taxonomies, ACF fields, "
    "templates), decide HOW the content should be published. Output STRICT "
    "JSON — no markdown fences, no prose outside JSON."
)


def _format_post_types(intro: WpIntrospectionSpec) -> str:
    SYSTEM_TYPES = {"revision", "nav_menu_item", "acf-field", "acf-field-group", "attachment", "oembed_cache", "user_request", "wp_block", "wp_navigation"}
    lines = []
    for pt in intro.post_types:
        if pt.name in SYSTEM_TYPES:
            continue
        lines.append(f"- {pt.name} ({pt.count} записей)")
    return "\n".join(lines) or "(только дефолтный post)"


def _format_taxonomies(intro: WpIntrospectionSpec) -> str:
    SYSTEM_TAX = {"nav_menu", "link_category"}
    lines = []
    for tx in intro.taxonomies:
        if tx.name in SYSTEM_TAX:
            continue
        lines.append(f"- {tx.name} ({tx.count} термов)")
    return "\n".join(lines) or "(нет)"


def _format_categories(intro: WpIntrospectionSpec) -> str:
    if not intro.categories:
        return "(нет)"
    return "\n".join(f"- slug={c.slug!r}  name={c.name!r}  ({c.count} постов)" for c in intro.categories)


def _format_templates(intro: WpIntrospectionSpec) -> str:
    if not intro.templates_per_post_type:
        return "(шаблонов нет)"
    out = []
    for pt, tpls in intro.templates_per_post_type.items():
        out.append(f"  {pt}:")
        for tpl, cnt in tpls:
            out.append(f"    - {tpl} ({cnt} раз)")
    return "\n".join(out)


def _format_acf(intro: WpIntrospectionSpec) -> str:
    if not intro.acf_field_groups:
        return "(ACF не используется)"
    out = []
    for grp in intro.acf_field_groups:
        out.append(f"  {grp.group_title}:")
        for f in grp.fields:
            out.append(f"    - {f.field_id}  name={f.field_name!r}  label={f.label!r}  type={f.type}")
    return "\n".join(out)


def _format_sample_posts(intro: WpIntrospectionSpec) -> str:
    if not intro.sample_posts:
        return "(нет сэмплов)"
    out = []
    for sp in intro.sample_posts:
        out.append(f"  Post id={sp.post_id} post_type={sp.post_type} slug={sp.slug!r}:")
        for k, v in sp.meta[:20]:
            out.append(f"    {k}: {v[:120]}")
    return "\n".join(out)


def _build_prompt(instruction: str, intro: WpIntrospectionSpec) -> str:
    return f"""Determine the publish action for this WordPress site. Output JSON ONLY.

USER INSTRUCTION:
{instruction}

SITE INTROSPECTION:

Available post_types:
{_format_post_types(intro)}

Available taxonomies:
{_format_taxonomies(intro)}

Category terms (taxonomy='category'):
{_format_categories(intro)}

Templates used per post_type (выбирай тот что чаще встречается для выбранного post_type):
{_format_templates(intro)}

ACF field groups (для extra_postmeta маппинга _field_xxxxx):
{_format_acf(intro)}

Sample existing posts с их postmeta (паттерн как тема ожидает заполненные поля):
{_format_sample_posts(intro)}

RETURN JSON:
{{
  "post_type": "<выбери из available post_types>",
  "post_status": "<publish | draft | pending | private>",
  "topic": "<тема контента — отчисти из instruction, без 'добавь в блог' и т.п.>",
  "taxonomy": "<имя таксономии для assignment, например 'category' или 'service_category' — null если для этого post_type таксономии не используются>",
  "term_slug": "<slug term'а в taxonomy куда положить, например 'articles' — null если нет таксономии>",
  "template": "<имя _wp_page_template файла из таблицы Templates выше — null если для post_type не нужен>",
  "extra_postmeta": {{ "og_title": "{{{{title}}}}", "_og_title": "field_xxxxx", ... }},
  "rationale": "1-2 строки почему именно так разрулил"
}}

ПРАВИЛА:
- post_type ОБЯЗАТЕЛЬНО из списка available post_types выше. Не выдумывай.
- НЕ публикуй в системные типы (revision/attachment/nav_menu_item etc.) — они в список не попали.
- post_status по умолчанию 'publish' если инструкция не намекает на draft.
- topic = чистая суть, без слов «добавь», «опубликуй», «положи».
- taxonomy/term_slug:
  - Если в post_type обычно есть таксономия (post→category, services→service_category) — выбери.
  - term_slug ТОЛЬКО из существующих (см. Category terms или sample постов выбранного типа).
- template — точное имя .php файла из таблицы Templates выше для выбранного post_type.
- extra_postmeta:
  - Скопируй паттерн из sample_posts ВЫБРАННОГО post_type.
  - Где значение содержит title/description → используй плейсхолдеры {{{{title}}}}, {{{{meta_description}}}}, {{{{slug}}}}.
  - Если ключ начинается с _ и значение похоже на field_xxxxx — это ACF reference, оставь как есть.
  - НЕ копируй _yoast_*, _edit_*, _wp_old_slug, _thumbnail_id — добавит pipeline или они системные.
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


def route_instruction(instruction: str, intro: WpIntrospectionSpec) -> WpAction:
    """LLM-routes natural-language instruction → WpAction."""
    if not instruction or not instruction.strip():
        raise ValueError("instruction must be non-empty")
    settings = get_settings()
    llm = make_text_llm(settings)
    prompt = _build_prompt(instruction.strip(), intro)
    raw = llm.generate(prompt=prompt, system=_SYSTEM)
    data = _extract_json(raw)
    try:
        action = WpAction.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"router output schema invalid: {e}") from e

    allowed = {pt.name for pt in intro.post_types} - {
        "revision", "nav_menu_item", "acf-field", "acf-field-group",
        "attachment", "oembed_cache", "wp_block", "wp_navigation",
    }
    if allowed and action.post_type not in allowed:
        raise ValueError(
            f"router picked post_type={action.post_type!r} which is not in allowed set "
            f"{sorted(allowed)}"
        )

    logger.info(
        "wp_router_done post_type=%s status=%s tax=%s/%s template=%s extra_keys=%d rationale=%s",
        action.post_type, action.post_status, action.taxonomy, action.term_slug,
        action.template, len(action.extra_postmeta), action.rationale[:120],
    )
    return action
