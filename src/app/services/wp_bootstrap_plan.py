from __future__ import annotations

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.core.llm_provider_factory import make_text_llm

logger = logging.getLogger(__name__)


class CategoryPlan(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    slug: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str = Field(default="", max_length=300)


class PagePlan(BaseModel):
    role: Literal["home", "about", "services_overview", "cases_overview", "team_overview", "contacts", "privacy"]
    title: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    instruction: str = Field(min_length=20, max_length=500)


class ServicePlan(BaseModel):
    topic: str = Field(min_length=5, max_length=200)


class CasePlan(BaseModel):
    topic: str = Field(min_length=5, max_length=200)
    industry: str = Field(min_length=2, max_length=60)


class TeamMemberPlan(BaseModel):
    topic: str = Field(min_length=5, max_length=200, description="Имя + краткая роль для LLM-generator'а")


class FaqPlan(BaseModel):
    question: str = Field(min_length=5, max_length=200)
    show_on: Literal["front_page", "services_overview", "contacts"] = "front_page"


class BlogPostPlan(BaseModel):
    topic: str = Field(min_length=5, max_length=200)
    category_slug: str = Field(min_length=2, max_length=60)


class SitePlan(BaseModel):
    """Полный план сайта на этап bootstrap."""
    brand: str = Field(min_length=1, max_length=120)
    tagline: str = Field(min_length=5, max_length=200)
    language: str = "ru"
    primary_color_hex: str = Field(default="#0284c7", pattern=r"^#[0-9a-fA-F]{6}$")
    industry_label: str
    timezone: str = Field(default="Europe/Moscow")

    blog_categories: list[CategoryPlan] = Field(min_length=3, max_length=8)
    service_categories: list[CategoryPlan] = Field(default_factory=list, max_length=6)

    pages: list[PagePlan] = Field(min_length=4, max_length=8)
    services: list[ServicePlan] = Field(min_length=3, max_length=8)
    cases: list[CasePlan] = Field(default_factory=list, max_length=6)
    team: list[TeamMemberPlan] = Field(default_factory=list, max_length=6)
    faqs: list[FaqPlan] = Field(default_factory=list, max_length=10)
    blog_posts: list[BlogPostPlan] = Field(min_length=5, max_length=25)


_SYSTEM = (
    "You are planning the structure of a new WordPress website for a specific "
    "business. You receive a brand name + industry description and output a "
    "JSON plan with all artefacts to create: categories, pages, services, "
    "cases, team, FAQs, and blog post topics. Output STRICT JSON only."
)


def _build_prompt(*, instruction: str, language: str = "ru") -> str:
    return f"""Ты собираешь план нового WordPress-сайта. Output JSON ONLY.

ЗАДАЧА: на основе описания ниже сгенерируй полный план сайта:
- brand (название бизнеса)
- tagline (слоган)
- 4-6 категорий блога (slug + name + description)
- 3-5 категорий услуг (опционально)
- 5-6 страниц (Home, About, Services overview, Cases overview, Team, Contacts, Privacy — выбери релевантные)
- 4-6 услуг (топиков для генерации)
- 3-5 кейсов (если применимо к индустрии)
- 3-5 сотрудников команды (если применимо)
- 5-8 FAQ-вопросов
- 10-15 тем блог-статей (с привязкой к категории)

ФОРМАТ ОТВЕТА:
{{
  "brand": "Название бренда",
  "tagline": "1 предложение слогана",
  "language": "ru",
  "primary_color_hex": "#0284c7",
  "industry_label": "B2B SaaS / Юр. услуги / Клиника / ...",
  "timezone": "Europe/Moscow",
  "blog_categories": [
    {{"name": "...", "slug": "latin-kebab", "description": "1 строка"}},
    ...
  ],
  "service_categories": [
    {{"name": "...", "slug": "latin-kebab", "description": ""}},
    ...
  ],
  "pages": [
    {{"role": "home", "title": "Главная", "slug": "home",
      "instruction": "Что должно быть на главной странице — 1-2 абзаца контекста для генератора"}},
    {{"role": "about", "title": "О компании", "slug": "about", "instruction": "..."}},
    ...
  ],
  "services": [
    {{"topic": "название услуги + ключевое преимущество"}},
    ...
  ],
  "cases": [
    {{"topic": "тема кейса с цифрой в результате", "industry": "B2B SaaS"}},
    ...
  ],
  "team": [
    {{"topic": "Имя Фамилия — должность"}},
    ...
  ],
  "faqs": [
    {{"question": "Вопрос?", "show_on": "front_page"}},
    ...
  ],
  "blog_posts": [
    {{"topic": "тема статьи", "category_slug": "slug-из-blog_categories"}},
    ...
  ]
}}

ПРАВИЛА:
- Язык: {language}.
- slug — латиница kebab-case.
- category_slug в blog_posts ОБЯЗАТЕЛЬНО совпадает с одним из blog_categories[].slug.
- show_on в faqs — только из набора (front_page | services_overview | contacts).
- role в pages — только из (home | about | services_overview | cases_overview | team_overview | contacts | privacy).
- Должен быть РОВНО ОДИН page с role=home.
- Темы услуг и кейсов — конкретные, не общие («контекстная реклама в Яндекс Директ», не «реклама»).
- Если для индустрии team / cases / service_categories неактуальны (например бизнес-блог без команды) — оставь пустые массивы.
- Темы блог-постов — равномерно распределены по blog_categories (минимум 2 поста на категорию).

ОПИСАНИЕ БИЗНЕСА:
{instruction}
"""


_FENCE_RX = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)


def _extract_json(raw: str) -> dict:
    t = raw.strip()
    if t.startswith("```"):
        t = _FENCE_RX.sub("", t)
        t = re.sub(r"\s*```\s*$", "", t)
    if not t.startswith("{"):
        s = t.find("{")
        if s == -1:
            raise ValueError(f"no JSON in plan: head={raw[:200]!r}")
        t = t[s:]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json
            return json.loads(repair_json(t))
        except Exception as exc:
            raise ValueError(f"plan JSON parse failed: {exc}") from exc


def plan_site(instruction: str, *, language: str = "ru") -> SitePlan:
    """Один LLM-вызов: instruction → полный SitePlan."""
    if not instruction or not instruction.strip():
        raise ValueError("instruction must be non-empty")

    settings = get_settings()
    llm = make_text_llm(settings)
    prompt = _build_prompt(instruction=instruction.strip(), language=language)
    raw = llm.generate(prompt=prompt, system=_SYSTEM)
    data = _extract_json(raw)

    try:
        plan = SitePlan.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"site plan schema invalid: {e}") from e

    logger.info(
        "site_planned brand=%s industry=%s pages=%d services=%d cases=%d team=%d faqs=%d posts=%d",
        plan.brand, plan.industry_label, len(plan.pages), len(plan.services),
        len(plan.cases), len(plan.team), len(plan.faqs), len(plan.blog_posts),
    )
    return plan
