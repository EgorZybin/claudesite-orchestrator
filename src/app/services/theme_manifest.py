from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AcfFieldDef:
    name: str
    type: str
    label: str
    required: bool = False
    instructions: str = ""
    max_length: int | None = None
    choices: dict[str, str] | None = None
    description: str = ""


@dataclass(frozen=True)
class PostTypeDef:
    slug: str
    rest_base: str
    label: str
    has_built_in_taxonomy: bool
    default_taxonomy_rest_base: str | None
    description: str
    acf_fields: list[AcfFieldDef] = field(default_factory=list)
    template_hint: str = ""


POST_TYPES: dict[str, PostTypeDef] = {
    "post": PostTypeDef(
        slug="post",
        rest_base="posts",
        label="Блог-статья",
        has_built_in_taxonomy=True,
        default_taxonomy_rest_base="categories",
        description=(
            "Статья в блог — Markdown-style body в post_content. "
            "Подходит для информационных материалов, гайдов, новостей."
        ),
        template_hint=(
            "Hero с категорией-чипом + featured image. Тема рендерит content через prose. "
            "Aside-блок «Главное» под статьёй если есть key_takeaways."
        ),
        acf_fields=[
            AcfFieldDef(
                name="subtitle", type="text", label="Подзаголовок",
                max_length=200,
                description="Опц. подзаголовок 1 строкой под H1. Дополняет title, не повторяет.",
            ),
            AcfFieldDef(
                name="reading_time_minutes", type="number", label="Время чтения (мин)",
                description="Целое 1-30. Показывается в шапке статьи.",
            ),
            AcfFieldDef(
                name="key_takeaways_raw", type="textarea", label="Главное (по строке)",
                max_length=2000,
                description=(
                    "3-5 главных тезисов статьи, по одному на строку (\\n-separated). "
                    "Каждый — 1 предложение. Рендерятся как aside-блок «Главное» "
                    "после контента."
                ),
            ),
        ],
    ),

    "page": PostTypeDef(
        slug="page",
        rest_base="pages",
        label="Страница",
        has_built_in_taxonomy=False,
        default_taxonomy_rest_base=None,
        description=(
            "Статическая страница (Главная, О нас, Контакты, Privacy и т.п.). "
            "Контент в post_content + опциональный hero-блок через ACF."
        ),
        template_hint=(
            "Hero-блок сверху (если hero_show=true) + post_content. "
            "Контент должен быть содержательный — 2-5 H2-секций, реальные факты."
        ),
        acf_fields=[
            AcfFieldDef(
                name="hero_show", type="true_false", label="Показать hero",
                description="true для landing-страниц (Home, О нас), false для документов (Privacy).",
            ),
            AcfFieldDef(
                name="hero_title", type="text", label="Hero-заголовок",
                max_length=200,
                description="Если задан, используется вместо post_title в hero. Может быть длиннее.",
            ),
            AcfFieldDef(
                name="hero_subtitle", type="textarea", label="Hero-подзаголовок",
                max_length=400,
                description="1-2 предложения под заголовком hero.",
            ),
            AcfFieldDef(
                name="hero_cta_label", type="text", label="CTA-кнопка: текст",
                max_length=60,
                description="«Записаться», «Получить расчёт» и т.п.",
            ),
            AcfFieldDef(
                name="hero_cta_url", type="url", label="CTA-кнопка: URL",
                description="Обычно /contacts/ или /services/.",
            ),
        ],
    ),

    "service": PostTypeDef(
        slug="service",
        rest_base="services",
        label="Услуга",
        has_built_in_taxonomy=True,
        default_taxonomy_rest_base="service-categories",
        description=(
            "Страница услуги/предложения. Имеет цену, длительность, список фич, "
            "целевую аудиторию, CTA. Рендерится с rich-hero и features-grid."
        ),
        template_hint=(
            "Hero split (text+image), features-grid, audience-callout, основной "
            "контент, FAQ привязанные к услуге, CTA-banner внизу."
        ),
        acf_fields=[
            AcfFieldDef(
                name="tagline", type="text", label="Tagline",
                max_length=200,
                description="Одна короткая фраза под title. Конкретика, не общие слова.",
            ),
            AcfFieldDef(
                name="price_from", type="text", label="Цена от",
                max_length=60,
                description="«от 60 000 ₽», «от 250 ₽ за лид», «по запросу». Пусто = не показывать.",
            ),
            AcfFieldDef(
                name="duration_text", type="text", label="Срок",
                max_length=60,
                description="«2-4 недели», «Запуск 7-10 дней», «1-3 месяца».",
            ),
            AcfFieldDef(
                name="key_features_raw", type="textarea", label="Что входит (по строке)",
                max_length=2000,
                description=(
                    "4-6 пунктов «что входит в услугу», по одному на строку (\\n). "
                    "Глаголы действия: «Аудит ниши», «Настройка кампаний», «Ежемесячные отчёты»."
                ),
            ),
            AcfFieldDef(
                name="audience_text", type="textarea", label="Кому подходит",
                max_length=1000,
                description="1-2 абзаца про целевую аудиторию услуги. Конкретика: размер бизнеса, отрасль.",
            ),
            AcfFieldDef(
                name="cta_label", type="text", label="CTA: текст",
                max_length=60,
                description="«Получить расчёт», «Записаться», «Заказать аудит».",
            ),
            AcfFieldDef(
                name="cta_url", type="url", label="CTA: URL",
                description="Обычно /contacts/.",
            ),
        ],
    ),

    "case_study": PostTypeDef(
        slug="case_study",
        rest_base="cases",
        label="Кейс",
        has_built_in_taxonomy=True,
        default_taxonomy_rest_base="case-industries",
        description=(
            "История клиента: задача, что сделали, какие результаты. "
            "Цифры обязательны — без metrics кейс не имеет смысла."
        ),
        template_hint=(
            "Dark hero с client/industry/period + metrics-grid (overlap-card на "
            "белом) + Задача → Решение → Подробности."
        ),
        acf_fields=[
            AcfFieldDef(
                name="client_name", type="text", label="Клиент",
                max_length=120,
                description="Название компании или «Анонимный клиент» если NDA.",
            ),
            AcfFieldDef(
                name="client_industry", type="text", label="Индустрия",
                max_length=60,
                description="«B2B SaaS», «E-commerce», «Юр. услуги», «Финтех».",
            ),
            AcfFieldDef(
                name="challenge", type="textarea", label="Задача",
                max_length=1500,
                description="2-4 предложения о ситуации клиента до проекта. КОНКРЕТНО: метрики, контекст.",
            ),
            AcfFieldDef(
                name="solution", type="textarea", label="Решение",
                max_length=2500,
                description="3-5 предложений о шагах работы. Действия команды + инструменты.",
            ),
            AcfFieldDef(
                name="result_summary", type="text", label="Главный результат (одна фраза)",
                max_length=200,
                description="Короткий пэйоф для карточек. «Cost per lead снижен с 4200 ₽ до 1380 ₽ за 3 месяца».",
            ),
            AcfFieldDef(
                name="metrics_raw", type="textarea", label="KPI (по строке: значение | подпись)",
                max_length=1000,
                description=(
                    "3-5 ключевых метрик. Формат: «−67% | стоимость лида\\n+240% | конверсия LP\\n"
                    "3 мес | срок реализации». ЦИФРЫ обязательны, не общие слова."
                ),
            ),
            AcfFieldDef(
                name="project_period", type="text", label="Период",
                max_length=100,
                description="«Окт 2025 — Янв 2026» или «3 месяца».",
            ),
        ],
    ),

    "team_member": PostTypeDef(
        slug="team_member",
        rest_base="team",
        label="Сотрудник",
        has_built_in_taxonomy=False,
        default_taxonomy_rest_base=None,
        description=(
            "Карточка сотрудника команды. Должность, био, экспертиза, контакты."
        ),
        template_hint=(
            "1+2 grid: photo + контакты слева, имя + position + bio + expertise-tags справа."
        ),
        acf_fields=[
            AcfFieldDef(
                name="position", type="text", label="Должность",
                max_length=120,
                description="«Управляющий партнёр», «Head of Performance», «Senior юрист».",
            ),
            AcfFieldDef(
                name="bio_short", type="textarea", label="Короткое био",
                max_length=400,
                description="1-2 предложения для карточки. Опыт + специализация.",
            ),
            AcfFieldDef(
                name="email", type="email", label="Email",
                description="Опц. рабочий email.",
            ),
            AcfFieldDef(
                name="phone", type="text", label="Телефон",
                max_length=40,
                description="С кодом страны.",
            ),
            AcfFieldDef(
                name="expertise_raw", type="textarea", label="Области экспертизы (по строке)",
                max_length=1000,
                description="3-6 коротких тегов экспертизы. «Семейное право», «Performance маркетинг», «B2B продажи».",
            ),
            AcfFieldDef(
                name="years_experience", type="number", label="Опыт (лет)",
                description="Целое число лет работы в индустрии.",
            ),
            AcfFieldDef(
                name="profile_url", type="url", label="LinkedIn / профиль",
                description="Опц. ссылка на внешний профиль.",
            ),
        ],
    ),

    "faq": PostTypeDef(
        slug="faq",
        rest_base="faqs",
        label="FAQ",
        has_built_in_taxonomy=False,
        default_taxonomy_rest_base=None,
        description=(
            "Вопрос-ответ. Title = вопрос, post_content = развёрнутый ответ. "
            "short_answer + show_on_page управляют автоматическим размещением."
        ),
        template_hint=(
            "Рендерится в accordion-блоке на главной (show_on_page=front_page) "
            "или на привязанной услуге (show_on_page=specific_post)."
        ),
        acf_fields=[
            AcfFieldDef(
                name="show_on_page", type="select", label="Где показывать",
                choices={
                    "none": "Не показывать автоматически",
                    "front_page": "Главная",
                    "services_overview": "Все услуги",
                    "contacts": "Контакты",
                    "specific_post": "Конкретный пост (см. specific_post_id)",
                },
                description="Какая страница должна автоматически тянуть этот FAQ в accordion.",
            ),
            AcfFieldDef(
                name="specific_post_id", type="number", label="ID привязанного поста",
                description="Только если show_on_page=specific_post. ID услуги/страницы.",
            ),
            AcfFieldDef(
                name="short_answer", type="textarea", label="Короткий ответ",
                max_length=600,
                description="1-3 предложения для accordion. Полный ответ в post_content.",
            ),
        ],
    ),
}


def list_post_type_slugs() -> list[str]:
    return list(POST_TYPES.keys())


def post_type(slug: str) -> PostTypeDef:
    if slug not in POST_TYPES:
        raise KeyError(f"unknown post_type: {slug}")
    return POST_TYPES[slug]


def acf_field_names(post_type_slug: str) -> list[str]:
    return [f.name for f in post_type(post_type_slug).acf_fields]
