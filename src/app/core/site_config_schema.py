from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models.enums import SiteMode


class SeoTemplateLayer(BaseModel):
    """SEO-шаблоны для одного слоя (global или ``page_types.<name>``)."""

    model_config = ConfigDict(extra="ignore")

    title_template: str | None = None
    meta_description_template: str | None = None
    robots_template: str | None = None
    canonical_template: str | None = None
    og_type: str | None = None
    twitter_card: str | None = None
    schema_type: str | None = None
    h1_template: str | None = None


class HeadSeoOptions(BaseModel):
    """Флаги для разметки в ``<head>`` (custom-рендер и единый SeoResolver)."""

    model_config = ConfigDict(extra="ignore")

    breadcrumb_json_ld: bool = Field(default=True, description="Вторая JSON-LD схема BreadcrumbList")
    og_site_name: bool = Field(default=True, description="meta og:site_name из brand")


class SiteSeoConfig(BaseModel):
    """Блок ``seo:`` — иерархия слияния: ``seo_overrides`` страницы > ``page_types`` > ``global``."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    brand: str | None = None
    city: str | None = None
    default_og_image: str | None = None
    placeholders: dict[str, str] = Field(default_factory=dict)
    head: HeadSeoOptions = Field(default_factory=HeadSeoOptions)
    global_defaults: SeoTemplateLayer = Field(
        default_factory=SeoTemplateLayer,
        alias="global",
    )
    page_types: dict[str, SeoTemplateLayer] = Field(default_factory=dict)


class ImagePipelineConfig(BaseModel):
    """
    Optional hero image generation (TZ §7: OpenAI DALL·E / gpt-image, **Google Gemini Nano Banana**, SD).

    **Nano Banana** — нативная генерация картинок в Gemini API (``generateContent`` + image modalities);
    конкретные id моделей Google переименовывает; смотри актуальную доку и поле ``gemini_model``.
    """

    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    provider: str = "openai"
    max_images_per_page: int = Field(default=1, ge=0, le=10)
    prompt_template: str = (
        "Editorial hero image for article topic: {{keyword}}. "
        "Brief context: {{snippet}}. Style: {{style}}."
    )
    alt_template: str = "{{keyword}}"
    style: str = "clean editorial photography, natural light"
    openai_model: str = "dall-e-3"
    openai_size: str = "1024x1024"
    gemini_model: str = "gemini-2.5-flash-image"
    gemini_aspect_ratio: str = "1:1"
    gemini_image_size: str = "1K"
    srcset_widths: list[int] = Field(default_factory=lambda: [640, 960, 1280])
    variation_hints: list[str] | None = Field(
        default=None,
        description=(
            "Доп. ограничения композиции для 2+ картинок на страницу (универсальные формулировки). "
            "Если не задано — используются встроенные нейтральные подсказки."
        ),
    )


class PipelineConfig(BaseModel):
    """Значения по умолчанию для контент-пайплайна (цикл Smodin / Тургенев)."""

    turgenev_pass_score_max: float = Field(
        default=6.0,
        description="Score at or below this value means pass (per TZ).",
    )
    max_iterations: int = Field(default=5, ge=1, le=50)
    smodin_each_iteration: bool = False
    images: ImagePipelineConfig = Field(default_factory=ImagePipelineConfig)
    content_length: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Минимальная длина основного текста (символов) по page_type, плюс ключ 'default'. "
            "Управляет per-page раскрытием prose-блоков: content_plan отдаёт скелет, "
            "expand_prose добивает каждую страницу до целевого объёма одним LLM-вызовом."
        ),
    )
    humanizers_per_pass: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "blog_post": ["humanizer_ru", "smodin"],
            "default": ["smodin"],
        },
        description=(
            "Цепочка гуманизаторов по page_type: каждый элемент списка задаёт ОДИН проход "
            "expand_prose+humanizer на этапе CUSTOM-create. Длина списка = число проходов. "
            "Допустимые значения элементов: 'smodin' (внешний rewriter-API), 'humanizer_ru' "
            "(локальный LLM по skill-промпту), 'none' (skip humanizer, только expand_prose). "
            "Default: blog_post = [smodin, humanizer_ru] (эмпирически <10% AI), остальные = [smodin]. "
            "Минимум один проход; пустой список поднимается до ['smodin']."
        ),
    )

    def min_chars_for(self, page_type: str | None) -> int:
        """Целевая длина основного текста для page_type (0 = раскрытие отключено)."""
        if not self.content_length:
            return 0
        if page_type and page_type in self.content_length:
            return int(self.content_length[page_type])
        return int(self.content_length.get("default", 0))

    def humanizer_chain_for(self, page_type: str | None) -> list[str]:
        """Цепочка имён гуманизаторов для page_type (минимум 1 элемент)."""
        chain: list[str] = []
        raw = None
        if page_type and page_type in self.humanizers_per_pass:
            raw = self.humanizers_per_pass[page_type]
        elif "default" in self.humanizers_per_pass:
            raw = self.humanizers_per_pass["default"]
        if isinstance(raw, list):
            chain = [str(x).strip() for x in raw if isinstance(x, (str, bytes)) and str(x).strip()]
        if not chain:
            chain = ["smodin"]
        return chain


class WpPostTypeInfo(BaseModel):
    name: str
    count: int = 0


class WpTaxonomyInfo(BaseModel):
    name: str
    count: int = 0


class WpCategoryInfo(BaseModel):
    slug: str
    name: str
    count: int = 0


class WpPageInfo(BaseModel):
    slug: str
    title: str


class WpAcfField(BaseModel):
    field_id: str
    field_name: str
    label: str
    type: str = ""


class WpAcfGroup(BaseModel):
    group_id: int
    group_title: str
    fields: list[WpAcfField] = Field(default_factory=list)


class WpSamplePost(BaseModel):
    post_id: int
    title: str
    slug: str
    post_type: str = "post"
    meta: list[tuple[str, str]] = Field(default_factory=list)


class WpIntrospectionSpec(BaseModel):
    """Snapshot структуры WP-сайта — ground truth для LLM-router'а."""

    siteurl: str | None = None
    blogname: str | None = None
    theme: str | None = None
    stylesheet: str | None = None
    seo_plugin: str = "none"
    post_types: list[WpPostTypeInfo] = Field(default_factory=list)
    taxonomies: list[WpTaxonomyInfo] = Field(default_factory=list)
    categories: list[WpCategoryInfo] = Field(default_factory=list)
    top_pages: list[WpPageInfo] = Field(default_factory=list)
    templates_per_post_type: dict[str, list[tuple[str, int]]] = Field(default_factory=dict)
    acf_field_groups: list[WpAcfGroup] = Field(default_factory=list)
    sample_posts: list[WpSamplePost] = Field(default_factory=list)


class WordPressSiteSection(BaseModel):
    """WP-цель: credentials + кэшированная introspection структуры сайта."""

    database_url: str | None = Field(
        default=None,
        description="SQLAlchemy URL of the WordPress MySQL database for this site.",
    )
    table_prefix: str = Field(default="wp_", pattern=r"^[A-Za-z0-9_]+$", min_length=2)
    uploads_base_path: str | None = Field(
        default=None,
        description="Filesystem base for wp-content/uploads (attachment registration).",
    )
    public_site_url: str | None = None
    default_post_author_id: int = Field(default=1, ge=1)
    theme_slug: str | None = None
    wp_cli_base: str | None = None
    introspection: WpIntrospectionSpec | None = Field(
        default=None,
        description=(
            "Snapshot структуры WP-сайта от init-wp / refresh-wp. LLM-router "
            "использует это как ground truth для выбора post_type / taxonomy / "
            "template / ACF-полей на каждую публикацию. Если null — pipeline "
            "запросит интроспекцию у БД в realtime (медленнее)."
        ),
    )
    rest_base_url: str | None = Field(
        default=None,
        description=(
            "Base URL для WP REST API (обычно public_site_url + /wp-json). "
            "Используется для загрузки media-attachments через /wp/v2/media."
        ),
    )
    rest_auth_user: str | None = Field(
        default=None,
        description="WP user (login) для Basic Auth к REST API.",
    )
    rest_auth_password: str | None = Field(
        default=None,
        description="WP Application Password (НЕ обычный пароль пользователя!).",
    )
    images_enabled: bool = Field(
        default=False,
        description=(
            "Включить генерацию featured image при publish: openai_image → "
            "REST /wp/v2/media → _thumbnail_id. Требует rest_auth_*. "
            "Каждый publish = +1 image API call (~10-30s + $0.03)."
        ),
    )


class CustomSiteSection(BaseModel):
    """Сайт в custom-режиме — динамический рендер из БД оркестратора."""

    public_base_url: str | None = Field(
        default=None,
        description=(
            "Канонический origin для SEO (canonical, шаблоны {{public_base_url}}). "
            "Не используется для src/srcset hero-картинок: в custom они всегда /uploads/..."
        ),
    )
    uploads_base_path: str | None = None
    default_template: str = "article"


class SiteThemeConfig(BaseModel):
    """Визуальная тема: палитра, шрифты, layout-настройки рендерера."""

    accent: str | None = Field(
        default=None,
        description="Брендовый цвет (HEX), используется для CTA, бейджей, hover-стейтов",
    )
    accent_foreground: str | None = Field(
        default=None,
        description="Цвет текста на брендовом фоне (по умолчанию #ffffff)",
    )
    background: str | None = None
    foreground: str | None = None
    nav_background: str | None = None
    card_background: str | None = None
    muted: str | None = None
    border: str | None = None
    radius: str | None = None
    max_width: str | None = None
    display_font: str | None = Field(
        default=None,
        description="Шрифт заголовков (имя Google Font, e.g. 'Manrope', 'Space Grotesk')",
    )
    body_font: str | None = Field(
        default=None,
        description="Шрифт текста (имя Google Font, по умолчанию Inter)",
    )
    density_scale: float | None = Field(
        default=None,
        ge=0.5,
        le=2.0,
        description="Множитель внутренних отступов и gap'ов (0.7 = плотно, 1.0 = по умолчанию, 1.3 = просторно)",
    )
    shadow_strength: float | None = Field(
        default=None,
        ge=0,
        le=3.0,
        description="Множитель плотности теней карточек (0 = плоский стиль, 1.0 = умолчание, 2.0 = выраженные тени)",
    )
    card_style: Literal["solid", "outlined", "elevated", "glass"] | None = Field(
        default=None,
        description=(
            "Базовое оформление карточек (features, link_grid, pricing, faq, ...). "
            "solid = белая карточка с border + тонкая тень (default); "
            "outlined = прозрачный фон, чёткий border, no shadow (editorial / legal); "
            "elevated = плотная тень, без border (premium / SaaS); "
            "glass = полупрозрачный фон с тонким border (modern / iOS)."
        ),
    )
    nav_style: Literal["pill", "flat", "minimal"] | None = Field(
        default=None,
        description=(
            "Стиль верхней навигации. "
            "pill = sticky плавающая «таблетка» с blur (default, SaaS/lifestyle); "
            "flat = full-width, прямые края, solid background (корпоративный); "
            "minimal = прозрачный фон, без border (editorial)."
        ),
    )
    font_subsets: list[Literal["cyrillic", "cyrillic-ext", "latin", "latin-ext", "greek"]] | None = Field(
        default=None,
        description=(
            "Какие subsets веб-шрифтов инлайнить. По умолчанию ['cyrillic','latin'] "
            "(оптимизировано под русские сайты). Добавь 'latin-ext' если есть "
            "редкие символы типа ₽, ä, ñ и хочешь чтобы они рендерились в Inter, "
            "а не системным fallback'ом."
        ),
    )
    motif_pattern: Literal["none", "dots", "waves", "grid", "hexagons", "stripes", "topo"] | None = Field(
        default=None,
        description=(
            "Декоративный паттерн на фоне hero-блока. Цвет берётся из accent. "
            "none = чистый градиент (legal/finance/minimal); "
            "dots = сетка точек (SaaS/B2B/marketplaces); "
            "waves = волны внизу (food/lifestyle/wellness); "
            "grid = инженерная сетка (engineering/DevOps/SaaS); "
            "hexagons = соты (biotech/fintech/инновации); "
            "stripes = диагональные полосы (sport/fitness/fashion); "
            "topo = топографические линии (outdoor/eco/travel)."
        ),
    )
    hero_layout: Literal["side", "background", "centered"] | None = Field(
        default=None,
        description=(
            "Раскладка hero-блока. "
            "side (default) = текст слева, картинка справа; "
            "background = картинка во весь блок, текст поверх затемнения (cafe/lifestyle/hotel); "
            "centered = текст по центру без картинки (minimal/editorial/legal)."
        ),
    )
    section_divider: Literal["none", "diagonal", "curved", "dotted", "zigzag"] | None = Field(
        default=None,
        description=(
            "Декоративный SVG-разделитель между смежными секциями страницы. Цвет — accent, "
            "низкая opacity. "
            "none (default) = без разделителей (минимализм, legal/finance); "
            "diagonal = тонкая диагональная штриховка (modern/SaaS/agency); "
            "curved = пологая волна (editorial/wellness/food); "
            "dotted = ряд точек (B2B/professional services); "
            "zigzag = зигзаг (fitness/youth/bold brands)."
        ),
    )
    reveal_animation: Literal["subtle", "slide_up", "slide_left", "scale_in"] | None = Field(
        default=None,
        description=(
            "Анимация появления секций при скролле (motion identity). "
            "subtle = только fade (luxury/legal/finance — спокойно); "
            "slide_up (default) = fade + slide up 20px (нейтральный — large multi-purpose); "
            "slide_left = fade + slide-from-left 30px (modern/magazine/editorial); "
            "scale_in = fade + лёгкий scale-up из 0.97 (agency/portfolio/creative). "
            "prefers-reduced-motion всегда отключает анимацию."
        ),
    )
    section_rhythm: Literal["none", "striped"] | None = Field(
        default=None,
        description=(
            "Ритм фонов соседних секций для зрительной разбивки длинной страницы. "
            "none (default) — все секции на едином bg-color (мinimalism, modern); "
            "striped — чётные .block-section получают translucent accent-tinted bg (~4%), "
            "motif/dividers просвечивают сквозь. Использовать для editorial/B2B/agency сайтов "
            "с длинной homepage; не использовать вместе с яркими motif (waves/topo)."
        ),
    )
    hover_intensity: Literal["minimal", "lift", "bold", "glow"] | None = Field(
        default=None,
        description=(
            "Интенсивность hover/focus-эффектов на интерактивных карточках и ссылках. "
            "minimal — только color-shift (legal/luxury/medical — без motion); "
            "lift (default) — translateY(-3px) + усиление тени (B2B/SaaS/generic — текущее); "
            "bold — translateY(-5px) + scale(1.015) (agency/portfolio/fitness — энергично); "
            "glow — accent-ring без motion (editorial/wellness — luminous, спокойный)."
        ),
    )


class SiteFormsConfig(BaseModel):
    """Куда слать уведомления о заявках формы для этого сайта."""

    notify_email: str | None = Field(
        default=None,
        description="Email получателя заявок (владелец сайта).",
    )
    from_name: str | None = Field(
        default=None,
        description="Имя в From-заголовке (e.g. 'Заявки Тёплая Кухня'). Если не задано — используется brand сайта.",
    )
    subject_template: str | None = Field(
        default=None,
        description="Кастомный subject. Placeholders: {brand}, {site_slug}, {form_id}, {page_slug}.",
    )
    cc_emails: list[str] = Field(
        default_factory=list,
        description="Дополнительные адреса для CC (например, второй менеджер).",
    )


class SiteFileConfig(BaseModel):
    """Файловый конфиг одного сайта (``config.yaml``)."""

    mode: SiteMode
    display_name: str | None = None
    wordpress: WordPressSiteSection | None = None
    custom: CustomSiteSection | None = None
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    seo: SiteSeoConfig | None = None
    theme: SiteThemeConfig | None = None
    forms: SiteFormsConfig = Field(default_factory=SiteFormsConfig)

    @model_validator(mode="after")
    def mode_matches_sections(self) -> SiteFileConfig:
        if self.mode == SiteMode.WORDPRESS and self.wordpress is None:
            raise ValueError("when mode is wordpress, a non-empty `wordpress:` section is required")
        if self.mode == SiteMode.CUSTOM and self.custom is None:
            raise ValueError("when mode is custom, a non-empty `custom:` section is required")
        return self
