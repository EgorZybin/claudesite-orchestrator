from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.site_content import ContentBlock


class BlocksReplace(BaseModel):
    """Полная замена `site_content_blocks` страницы.

    Все существующие блоки удаляются, новый список вставляется в порядке списка.
    Каждый блок валидируется через `ContentBlock` discriminated union.
    """

    blocks: list[ContentBlock] = Field(min_length=0)


class ModuleUpsert(BaseModel):
    """Upsert одного site_module (по паре site_id+kind).

    `data` — JSON по схеме конкретного kind (валидируется в роуте через
    `SiteModule` discriminated union с правильным `kind` подставленным из URL).
    """

    data: dict[str, Any]


class PageMetadataPatch(BaseModel):
    """Точечные правки полей страницы (всё optional)."""

    title: str | None = Field(default=None, max_length=200)
    seo_description: str | None = Field(default=None, min_length=80, max_length=200)
    hero_title: str | None = None
    hero_subtitle: str | None = None
    hero_image: str | None = None
    nav_label: str | None = Field(default=None, max_length=120)
    nav_order: int | None = None
    sort_order: int | None = Field(default=None, ge=0)
    modules_used: list[str] | None = None


class BlockRewrite(BaseModel):
    """LLM-правка одного текстового блока через `/admin/.../blocks/{id}/rewrite`.

    `instruction` — на естественном языке: "сделай короче", "переформулируй
    вежливее", "добавь упоминание скидки" итд.
    """

    instruction: str = Field(min_length=3, max_length=1000)


class DesignEdit(BaseModel):
    """Claude-CLI правка визуала сайта через `/admin/.../design-edit`.

    Claude edit'ит файлы (CSS/JS/templates) в workspace на EU gateway,
    diff проверяется по scope, новая версия публикуется.

    `scope` — glob-паттерны файлов, которые разрешено менять (default — всё editable
    кроме manifest.json, который перегенерится оркестратором).
    """

    instruction: str = Field(min_length=3, max_length=2000)
    scope: list[str] | None = None
    timeout_seconds: int | None = Field(default=None, ge=30, le=1800)


class PageAdd(BaseModel):
    """Добавление одной страницы существующему сайту (template уже есть).

    `slug` — latin-kebab, должен быть уникален среди существующих pages.
    `page_type` — должен быть в `manifest.page_types` (иначе нужен Phase 14 extend).
    """

    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=2, max_length=100)
    page_type: str = Field(min_length=2, max_length=32)
    keyword: str = Field(min_length=3, max_length=200)
    title_hint: str | None = Field(default=None, max_length=200)
    industry: str | None = Field(default=None, max_length=40)
    skip_expand_prose: bool = False


class PageTypeExtend(BaseModel):
    """Добавление нового page_type'а: Claude CLI генерит новый template + дописывает manifest.

    `name` — имя page_type'а (lowercase, kebab или snake). Должно быть уникально
    среди существующих manifest.page_types.
    `description` — что это за страница (даётся Claude'у как контекст).
    `slots_needed` — опц. подсказка какие slots template'у нужны
    (hero, content_blocks, features, pricing, faq, ...). Если None — Claude
    выбирает по описанию и существующим templates.
    """

    name: str = Field(
        pattern=r"^[a-z][a-z0-9_]*$",
        min_length=2,
        max_length=32,
    )
    description: str = Field(min_length=10, max_length=500)
    slots_needed: list[str] | None = None
    timeout_seconds: int | None = Field(default=None, ge=30, le=1800)


class SiteCreate(BaseModel):
    """Создание нового сайта-record (без контента). Pipeline-генерация запускается
    отдельным вызовом `/admin/sites/{slug}/generate`.
    """

    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=2, max_length=128)
    display_name: str | None = Field(default=None, max_length=255)


class SiteGenerate(BaseModel):
    """Запуск full-pipeline генерации сайта: content_plan + expand_prose + persist +
    Claude CLI design. Async — возвращает `job_id`, опрос через `/jobs/{id}`.
    """

    user_prompt: str = Field(min_length=20, max_length=5000)
    target_pages: int = Field(default=6, ge=3, le=15)
    design_tokens: dict | None = Field(
        default=None,
        description=(
            "Optional structured palette/fonts/layout tokens extracted by "
            "`claudesite site analyze-url` from a reference site's screenshot. "
            "When provided, get injected into brief.md as MANDATORY constraints "
            "(exact HSL values, font families) — Claude must use them in "
            "src/theme.css rather than pick its own."
        ),
    )


class DomainAdd(BaseModel):
    """Привязка домена к сайту. Только запись в БД — Apache vhost + Let's Encrypt
    сертификат разворачивается отдельно через `scripts/provision-domain.sh`.
    """

    host: str = Field(min_length=4, max_length=255)
    is_primary: bool = False
    is_active: bool = True
