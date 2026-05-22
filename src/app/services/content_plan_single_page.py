from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from app.adapters.errors import AdapterError
from app.core.config import get_settings
from app.core.llm_provider_factory import make_text_llm
from app.schemas.site_content import Page, PageType

logger = logging.getLogger(__name__)


_SYSTEM = (
    "You are designing the semantic CONTENT of ONE page for an existing "
    "multi-page website. You output text/structured data — NOT visual layout. "
    "A separate template (already built) will render it."
)


_BASE_PAGE_TYPES: tuple[str, ...] = (
    "home",
    "services",
    "service",
    "blog_index",
    "blog_post",
    "about",
    "contacts",
)


def _build_prompt(
    *,
    brand: str,
    industry: str,
    language: str,
    page_type: str,
    slug: str,
    keyword: str,
    title_hint: str | None,
    existing_slugs: list[str],
) -> str:
    title_line = f"Title hint: {title_hint}\n" if title_hint else ""
    existing = ", ".join(existing_slugs) or "(none yet)"

    page_type_guide = {
        "blog_post": (
            "blog_post: 4-6 paragraph blocks ALTERNATED with H2 heading blocks (each "
            "heading names a sub-topic). Each paragraph 1-3 SHORT sentences with at "
            "least one concrete fact/number/tool name. A later expand step turns these "
            "drafts into full long-form. Optional one image or quote block. modules_used: "
            '["faq", "footer"].'
        ),
        "service": (
            "service: short hero subtitle + 3-5 paragraph blocks with H3 sub-headings "
            "explaining what is included, how it works, what value the customer gets. "
            "1 cta at the end. modules_used: "
            '["features", "pricing", "faq", "footer"].'
        ),
        "about": (
            "about: 4-5 paragraph blocks of company narrative (history, mission, "
            "approach). Optional one quote. modules_used: "
            '["team", "stats", "footer"].'
        ),
        "services": (
            "services overview: brief intro 2-3 paragraphs + cta. modules_used: "
            '["features", "footer"].'
        ),
        "contacts": (
            "contacts: 1-2 intro paragraphs. modules_used: "
            '["contact_info", "footer"].'
        ),
        "blog_index": (
            "blog_index: 2-3 intro paragraphs + cta. modules_used: ['footer']. "
            "Cards for individual posts are populated at render time."
        ),
        "home": (
            "home: brand intro 2-3 heading+paragraph alternations, 1-2 ctas. "
            'modules_used: ["features", "stats", "testimonials", "faq", "footer"].'
        ),
    }.get(page_type, "Use sensible content structure for the page type.")

    return f"""Return ONLY JSON. No markdown, no comments, no prose outside JSON.

You are designing ONE page for an existing multi-page website.

Site context (already established, don't change):
- Brand: {brand}
- Industry: {industry}
- Language: {language}
- Existing page slugs (don't collide): {existing}

This page:
- Slug: {slug}
- Page type: {page_type}
- Keyword / topic: {keyword}
{title_line}

Schema (one Page object):
{{
  "slug": "{slug}",
  "page_type": "{page_type}",
  "title": "SEO heading (in {language})",
  "seo_description": "80-200 chars, concrete, no fluff",
  "hero_title": "short headline OR null",
  "hero_subtitle": "supporting line OR null",
  "hero_image": null,
  "content_blocks": [
    {{"kind": "heading", "props": {{"level": 2, "text": "..."}}}},
    {{"kind": "paragraph", "props": {{"markdown": "Draft 1-3 sentences with **inline**, *em*, [link](/existing-slug), `code`."}}}},
    {{"kind": "image",     "props": {{"src": "", "alt": "...", "caption": "..."}}}},
    {{"kind": "list",      "props": {{"ordered": false, "items": ["..."]}}}},
    {{"kind": "quote",     "props": {{"text": "...", "attribution": "..."}}}},
    {{"kind": "table",     "props": {{"headers": ["..."], "rows": [["..."]]}}}},
    {{"kind": "cta",       "props": {{"label": "...", "href": "/contacts", "style": "primary"}}}}
  ],
  "modules_used": ["faq", "footer"],
  "nav_label": null,
  "nav_order": null
}}

HARD RULES:
- slug = exactly "{slug}" (don't change).
- page_type = exactly "{page_type}".
- content_blocks[].kind only: heading, paragraph, image, list, quote, table, cta.
- DO NOT invent visual block types (no "hero", "features", "cta-section", etc.).
- IMAGES: src="" (pipeline attaches later).
- INTERNAL LINKS: cta_href / link href to existing pages MUST be "/" + one of:
  {existing} + "/contacts".
- All text in language: {language}.
- For blog_post: NO nav_label (blog_post pages live under blog_index).
- seo_description: 80-200 chars, concrete.

PAGE TYPE GUIDANCE:
- {page_type_guide}

CONTENT QUALITY:
- Drafts only — 1-3 sentences per paragraph. expand_prose step extends them.
- Concrete numbers, real tool/platform names. No "крупная сеть" / "лидер отрасли".
- Tone: professional, fits {industry} industry.
"""


def _extract_json(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    if not t.startswith("{"):
        start = t.find("{")
        if start == -1:
            raise ValueError(f"no JSON object found; head={text[:200]!r}")
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i in range(start, len(t)):
            c = t[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        t = t[start:end] if end != -1 else t[start:]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        from json_repair import repair_json

        return json.loads(repair_json(t))


def llm_plan_single_page_content(
    *,
    brand: str,
    industry: str,
    language: str,
    page_type: str,
    slug: str,
    keyword: str,
    title_hint: str | None = None,
    existing_slugs: list[str] | None = None,
) -> Page:
    """Сгенерить ОДНУ Page для существующего сайта.

    Raises:
        ValueError: невалидный page_type, конфликт slug'а, malformed JSON,
            или Page-схема не сошлась.
        AdapterError: LLM-провайдер недоступен.
    """
    if not page_type or not page_type.strip().islower() or not page_type.replace("_", "").isalnum():
        raise ValueError(
            f"invalid page_type format={page_type!r}; expect lowercase letters/digits/underscore"
        )

    existing = list(existing_slugs or [])
    if slug in existing:
        raise ValueError(f"slug {slug!r} already exists on this site")

    settings = get_settings()
    llm = make_text_llm(settings)
    prompt = _build_prompt(
        brand=brand,
        industry=industry,
        language=language,
        page_type=page_type,
        slug=slug,
        keyword=keyword,
        title_hint=title_hint,
        existing_slugs=existing,
    )

    try:
        raw = llm.generate(prompt=prompt, system=_SYSTEM)
    except AdapterError:
        raise

    try:
        data = _extract_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"single_page: JSON parse failed: {e}; head={raw[:300]!r}") from e

    data["slug"] = slug
    data["page_type"] = page_type

    try:
        page = Page.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"single_page: Page validation failed: {e}") from e

    logger.info(
        "single_page_ok slug=%s page_type=%s blocks=%d modules_used=%s",
        page.slug, page.page_type, len(page.content_blocks), page.modules_used,
    )
    return page
