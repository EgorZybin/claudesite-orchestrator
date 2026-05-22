from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from app.adapters.errors import AdapterError
from app.core.config import get_settings
from app.core.llm_provider_factory import make_text_llm

logger = logging.getLogger(__name__)


class WpContentDraft(BaseModel):
    title: str = Field(min_length=10, max_length=200)
    slug: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    meta_description: str = Field(min_length=80, max_length=320)
    body_markdown: str = Field(min_length=300)


_PROFILES: dict[str, dict[str, str]] = {
    "post": {
        "kind": "СТАТЬЯ для блога",
        "structure": "Intro (2-3 предложения с фактами) → 3-5 H2 разделов → выводы.",
        "length": "Минимум 600 слов.",
        "tone": "Деловой, факты, конкретика, ссылки на статьи закона/практику если применимо.",
    },
    "services": {
        "kind": "СТРАНИЦА УСЛУГИ",
        "structure": "Hero-абзац о сути услуги → блок Что входит (список) → Кому подходит → Как мы работаем (шаги) → Цены/Сроки если есть → CTA-выводы.",
        "length": "Минимум 400 слов.",
        "tone": "Преимущественно продающий, конкретный, без эпитетов 'лучший / уникальный'.",
    },
    "service": {
        "kind": "СТРАНИЦА УСЛУГИ",
        "structure": "Hero-абзац о сути услуги → блок Что входит (список) → Кому подходит → Как мы работаем (шаги) → CTA.",
        "length": "Минимум 400 слов.",
        "tone": "Продающий + конкретный.",
    },
    "case": {
        "kind": "КЕЙС",
        "structure": "Клиент (1 абз.) → Задача → Что сделали (с цифрами/инструментами) → Результаты (метрики) → Выводы.",
        "length": "Минимум 500 слов.",
        "tone": "Сторителлинг + цифры. От 1-го лица команды (мы).",
    },
    "cases": {
        "kind": "КЕЙС",
        "structure": "Клиент → Задача → Решение с цифрами → Результаты → Выводы.",
        "length": "Минимум 500 слов.",
        "tone": "Сторителлинг + цифры.",
    },
    "page": {
        "kind": "СТАТИЧЕСКАЯ СТРАНИЦА",
        "structure": "Intro → 2-4 содержательных раздела → CTA/контакт. БЕЗ news-стиля.",
        "length": "Минимум 350 слов.",
        "tone": "Информационный, sober, без хайпа.",
    },
    "default": {
        "kind": "КОНТЕНТ",
        "structure": "Intro → 3 раздела → выводы.",
        "length": "Минимум 400 слов.",
        "tone": "Деловой и конкретный.",
    },
}


_SYSTEM = (
    "You are a Russian-language content writer producing content for an existing "
    "WordPress site. Output STRICT JSON only — no markdown fences, no prose "
    "outside JSON. Adapt style/structure based on the content kind given."
)


def _build_prompt(topic: str, post_type: str, language: str = "ru") -> str:
    profile = _PROFILES.get(post_type, _PROFILES["default"])
    return f"""Return ONLY JSON. No markdown fences, no commentary.

{{
  "title": "SEO-заголовок 40-100 символов",
  "slug": "latin-kebab-case-from-title",
  "meta_description": "80-320 символов, конкретно, без воды",
  "body_markdown": "Полный текст в markdown. Используй ## для подзаголовков. БЕЗ ссылок на внешние сайты, БЕЗ изображений."
}}

КОНТЕНТ-ТИП: {profile['kind']}
СТРУКТУРА: {profile['structure']}
ОБЪЁМ: {profile['length']}
ТОН: {profile['tone']}

ОБЩИЕ ПРАВИЛА:
- Язык: {language}.
- title — без кликбейта/эмодзи, описывает суть.
- slug — латиница kebab-case, из title.
- meta_description — фактическая суть для SERP, не водяной маркетинг.
- НЕ начинай абзацы со слов "В современном мире", "Сегодня", "Многие".

TOPIC:
{topic}
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
            raise ValueError(f"no JSON in LLM output: head={raw[:200]!r}")
        t = t[s:]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json
            return json.loads(repair_json(t))
        except Exception as exc:
            raise ValueError(f"JSON parse failed: {exc}; head={raw[:200]!r}") from exc


def generate_content_draft(
    topic: str, *, post_type: str = "post", language: str = "ru",
) -> WpContentDraft:
    if not topic or not topic.strip():
        raise ValueError("topic must be non-empty")
    settings = get_settings()
    llm = make_text_llm(settings)
    prompt = _build_prompt(topic.strip(), post_type=post_type, language=language)
    raw = llm.generate(prompt=prompt, system=_SYSTEM)
    data = _extract_json(raw)
    try:
        draft = WpContentDraft.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"draft schema invalid: {e}") from e
    logger.info(
        "wp_content_drafted post_type=%s title=%s slug=%s body_chars=%d",
        post_type, draft.title[:60], draft.slug, len(draft.body_markdown),
    )
    return draft
