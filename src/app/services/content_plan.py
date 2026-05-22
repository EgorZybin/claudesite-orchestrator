from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from app.adapters.errors import AdapterError
from app.core.config import get_settings
from app.core.llm_provider_factory import make_text_llm
from app.core.site_config_schema import SiteThemeConfig
from app.schemas.site_content import SiteContent

logger = logging.getLogger(__name__)


_SYSTEM = (
    "You are designing the semantic CONTENT of a multi-page business website. "
    "You output text and structured data — NOT visual layout. A separate "
    "step will design how the site visually looks."
)


def _build_prompt(
    *,
    user_prompt: str,
    target_pages: int,
    theme: SiteThemeConfig | None = None,
    industry_hint: str | None = None,
) -> str:
    industry_line = ""
    if industry_hint:
        industry_line = f"\nIndustry hint (already detected): {industry_hint}\n"
    elif theme is not None and getattr(theme, "industry", None):
        industry_line = f"\nIndustry hint (already detected): {theme.industry}\n"

    return f"""Return ONLY JSON. No markdown, no comments, no prose outside JSON.
You are designing a multi-page business website's CONTENT.

CRITICAL: You output SEMANTIC content (text, headings, lists, images, quotes,
tables, ctas) — NOT visual layout. Do NOT produce "hero", "features-section",
"footer-section" or any visual block types. A separate step designs the visual.

Schema (top-level object):
{{
  "site_meta": {{
    "brand": "...",
    "tagline": "1-sentence pitch (optional, may be null)",
    "industry": "legal|saas|food|hospitality|fashion|fitness|medical|education|agency|b2b-services|finance|retail|...",
    "language": "ru|en|..."
  }},
  "pages": [
    {{
      "slug": "latin-kebab",
      "page_type": "home|services|service|blog_index|blog_post|about|contacts",
      "title": "SEO heading for this page, in user's language",
      "seo_description": "80-320 chars, concrete, no fluff",
      "hero_title": "short headline for hero slot OR null",
      "hero_subtitle": "supporting line OR null",
      "hero_image": null,
      "content_blocks": [
        {{"kind": "heading",   "props": {{"level": 1|2|3|4, "text": "..."}}}},
        {{"kind": "paragraph", "props": {{"markdown": "Draft text with inline **bold**, *em*, [link](/slug), `code`. 1-3 sentences."}}}},
        {{"kind": "image",     "props": {{"src": "", "alt": "Описание", "caption": "..."}}}},
        {{"kind": "list",      "props": {{"ordered": false, "items": ["item 1", "item 2"]}}}},
        {{"kind": "quote",     "props": {{"text": "...", "attribution": "..."}}}},
        {{"kind": "table",     "props": {{"headers": ["A","B"], "rows": [["a1","b1"],["a2","b2"]]}}}},
        {{"kind": "cta",       "props": {{"label": "...", "href": "/slug-from-this-site", "style": "primary"}}}}
      ],
      "modules_used": ["features", "stats", "faq", "footer"],
      "nav_label": "short menu label OR null if not in nav",
      "nav_order": 1
    }}
  ],
  "modules": [
    {{"kind": "features",      "data": {{"title": "опц.", "items": [{{"title": "...", "description": "...", "icon": "⚡"}}]}}}},
    {{"kind": "stats",         "data": {{"items": [{{"value": "47%", "label": "довольных клиентов"}}]}}}},
    {{"kind": "testimonials",  "data": {{"items": [{{"quote": "...", "author": "...", "role": "..."}}]}}}},
    {{"kind": "pricing",       "data": {{"plans": [{{"name": "...", "price": "15 000 ₽", "period": "в месяц", "features": ["..."], "cta_label": "Выбрать", "cta_href": "/contacts", "highlighted": false}}]}}}},
    {{"kind": "team",          "data": {{"members": [{{"name": "...", "role": "...", "bio": "..."}}]}}}},
    {{"kind": "faq",           "data": {{"items": [{{"question": "...", "answer": "..."}}]}}}},
    {{"kind": "contact_info",  "data": {{"email": "...", "phone": "...", "address": "...", "hours": ["Пн-Пт 10:00–19:00"], "social": [{{"channel": "telegram", "href": "https://t.me/brand", "label": "@brand"}}]}}}},
    {{"kind": "footer",        "data": {{"tagline": "одно предложение про бренд", "columns": [{{"title": "Услуги", "links": [{{"label": "...", "href": "/..."}}]}}], "legal": "© 2026 Brand"}}}}
  ]
}}

HARD RULES:
- pages must contain AT LEAST {target_pages} items.
- slug: latin kebab-case, unique across pages.
- EXACTLY one page with slug="contacts" and page_type="contacts".
- EXACTLY one page with page_type="home".
- content_blocks[].kind MUST be one of: heading, paragraph, image, list, quote, table, cta.
- DO NOT invent "hero"/"features"/"footer"/etc. as content_blocks kinds. Those are
  visual layout — handled by separate step.
- IMAGES: do NOT invent URLs. Set image.src="" and hero_image=null. The pipeline
  will attach real images later.
- INTERNAL LINKS: cta_href / link href to this site's pages MUST be "/" + a slug
  that exists in this plan's pages[]. Use "/contacts" for contacts. For external
  links use full https://... URLs.
- All human-readable text in the SAME LANGUAGE as the user request.
- nav: AT MOST 6 pages have nav_label set (top-level menu); blog_post pages MUST NOT
  have nav_label (they live under blog_index). home should be first (nav_order=0),
  contacts last (high nav_order like 90).
- seo_description: 80-320 chars, concrete fact-based, no "крупная сеть"/"лидер отрасли".

CONTENT QUALITY:
- content_blocks paragraphs are DRAFTS (1-3 sentences). Use real tool/platform
  names and concrete numbers. A later step expands drafts into full long-form.
- For blog_post pages: 4-6 paragraph blocks each preceded by an H2 heading block.
  Each paragraph 1-3 sentences with at least one concrete fact/number.
- features: 3-6 items, each with short single-emoji icon, no repeats within page.
- stats: at least 3 metrics with plausible values.
- testimonials: 2-4 quotes with real-sounding author+role.
- pricing: 2-4 plans, EXACTLY one with highlighted=true.
- faq: 3-5 questions, useful answers.

PAGE TYPE GUIDANCE (semantic only — no visual block names!):
- home: brand intro (2-3 heading+paragraph alternations), 1-2 ctas. modules_used: features, stats, testimonials, faq, footer.
- services: short intro paragraphs + cta. modules_used: features, footer.
- service: 3-5 paragraph blocks about the service with H3 sub-headings, 1 cta. modules_used: features (service-specific), pricing, faq, footer.
- blog_index: 2-3 intro paragraphs, cta. modules_used: footer. NO posts_list block — populated at render time.
- blog_post: 4-6 paragraph blocks alternated with H2 headings (## subtopic), occasional image or quote. modules_used: faq, footer. NO nav_label.
- about: 4-5 paragraphs of company narrative, optional quote, optional image. modules_used: team, stats, footer.
- contacts: 1-2 intro paragraphs. modules_used: contact_info, footer.
{industry_line}
User request:
{user_prompt}
"""


def _extract_json(text: str) -> dict:
    """Извлечь JSON-объект из ответа LLM, переживая markdown-обёртки и обрезанный хвост."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    if not t.startswith("{"):
        start = t.find("{")
        if start != -1:
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


def llm_plan_site_content(
    *,
    user_prompt: str,
    target_pages: int = 6,
    theme: SiteThemeConfig | None = None,
    industry_hint: str | None = None,
) -> SiteContent:
    """LLM-вызов → semantic site content (заменяет llm_plan_r1_document).

    Args:
        user_prompt: запрос пользователя ("сделай сайт ресторану в Москве").
        target_pages: минимальное число страниц (плановщику разрешено больше).
        theme: опциональный уже-выбранный SiteThemeConfig — даёт industry hint.
        industry_hint: явная подсказка по индустрии (приоритет над theme.industry).

    Returns:
        SiteContent, прошедший pydantic-валидацию.

    Raises:
        ValueError: невалидный JSON-ответ или схема не сошлась.
        AdapterError: LLM-провайдер недоступен.
    """
    settings = get_settings()
    llm = make_text_llm(settings)
    prompt = _build_prompt(
        user_prompt=user_prompt,
        target_pages=max(3, int(target_pages)),
        theme=theme,
        industry_hint=industry_hint,
    )

    try:
        raw = llm.generate(prompt=prompt, system=_SYSTEM)
    except AdapterError:
        raise

    try:
        data = _extract_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"content_plan: JSON parse failed: {e}; head={raw[:300]!r}") from e

    if not isinstance(data, dict):
        raise ValueError(f"content_plan: top-level is not object: {type(data).__name__}")

    try:
        site_content = SiteContent.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"content_plan: SiteContent validation failed: {e}") from e

    pages = site_content.pages
    page_types = [p.page_type for p in pages]
    if page_types.count("home") != 1:
        raise ValueError(f"content_plan: expected exactly 1 home, got {page_types.count('home')}")
    if page_types.count("contacts") != 1:
        raise ValueError(f"content_plan: expected exactly 1 contacts, got {page_types.count('contacts')}")
    slugs = [p.slug for p in pages]
    if len(set(slugs)) != len(slugs):
        raise ValueError(f"content_plan: duplicate slugs: {slugs}")

    logger.info(
        "content_plan_ok pages=%d modules=%d brand=%s industry=%s",
        len(pages),
        len(site_content.modules),
        site_content.site_meta.brand,
        site_content.site_meta.industry,
    )
    return site_content
