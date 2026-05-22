from __future__ import annotations

import json

from app.schemas.site_content import SiteContent


_INDUSTRY_GROUPS: dict[str, tuple[str, str]] = {
    "legal":        ("conservative-professional", "Юридическая ниша. Тон строгий, институциональный. Палитра — глубокий синий / навcкий / бордо / forest-green, низкая-средняя насыщенность (S=30-60%). Neutral family — slate или zinc. Использовать top-bar в header с телефоном, часами, адресом. Hero pattern — top-bar-hero с метриками (опыт, дела, рейтинг). Никаких градиентов, никакого 'SaaS-bold'. Шрифт display — serif (Source Serif Pro, EB Garamond) или серьёзный гротеск (Manrope, Inter), без showy-размеров."),
    "law":          ("conservative-professional", "Юридическая ниша — см. legal."),
    "lawyer":       ("conservative-professional", "Юридическая ниша — см. legal."),
    "lawfirm":      ("conservative-professional", "Юридическая ниша — см. legal."),
    "medical":      ("conservative-professional", "Медицина. Палитра — спокойные синие/teal/sage-green с белым, низкая насыщенность. Top-bar обязателен (часы приёма, телефон, адрес). Подчёркивай доверие, сертификаты, опыт врачей. Не использовать ярко-красный или жёлтый."),
    "dental":       ("conservative-professional", "Стоматология — см. medical, плюс акцент на 'безболезненно/современно/комфортно'."),
    "clinic":       ("conservative-professional", "Клиника — см. medical."),
    "accounting":   ("conservative-professional", "Бухгалтерия/аудит. Палитра — deep blue/navy/charcoal. Подчёркивай точность, надёжность, лицензии. Top-bar с телефоном."),
    "notary":       ("conservative-professional", "Нотариус — см. legal, более камерно."),
    "financial":    ("conservative-professional", "Финансовый сектор. Deep navy/charcoal/forest, минимум декора. Подчёркивай регуляторный compliance."),
    "insurance":    ("conservative-professional", "Страхование — см. financial."),
    "consulting":   ("conservative-professional", "Консалтинг. Restrained palette, подчёркивай экспертизу через case-studies и метрики."),
    "saas":         ("bold-tech", "SaaS/tech. Палитра — bright accent (бирюза/индиго/фиолет/электрик), S=80-100%. Градиенты в hero разрешены. Hero — split layout (текст + product visual). Display font — geometric sans (Inter, Manrope, Geist) большого размера. Активные scroll-reveal и hover-эффекты OK. CTA — 'Start free trial' / 'Book a demo'."),
    "startup":      ("bold-tech", "Стартап — см. saas."),
    "ai":           ("bold-tech", "AI/ML продукт — см. saas, плюс futuristic accent (плюрпле/электрик/неон)."),
    "fintech":      ("bold-tech", "Современный fintech — может быть bold, но осторожнее с яркостью; индиго/teal лучше чем оранжевый."),
    "tech":         ("bold-tech", "Технологическая компания — см. saas."),
    "devtools":     ("bold-tech", "Dev-tools — monospace в hero допустим, terminal-aesthetic, dark mode опц."),
    "agency":       ("editorial-creative", "Креативное агентство. Editorial-стиль — крупная типографика, асимметричные сетки, большие изображения, тонкие гротеск + serif display. Палитра монохромная с одним acuente. Подчёркивай портфолио и cases."),
    "studio":       ("editorial-creative", "Студия — см. agency."),
    "design":       ("editorial-creative", "Дизайн-студия — design-forward, опинионатив, асимметрия, mixed type."),
    "portfolio":    ("editorial-creative", "Портфолио — image-first, минимальный текст, work showcase центральный."),
    "photography":  ("editorial-creative", "Фотография — image-first, минимальный chrome, тёмные/светлые theme на работы."),
    "restaurant":   ("warm-hospitality", "Ресторан. Тёплая палитра — терракот, охра, sage, dusty rose. Serif display (Cormorant, Playfair). Hero — фото блюда / интерьера. Подчёркивай атмосферу. Большие радиусы (12-16px)."),
    "cafe":         ("warm-hospitality", "Кафе — см. restaurant, более камерно."),
    "bakery":       ("warm-hospitality", "Пекарня — warm palette, photo-led, soft transitions."),
    "hotel":        ("warm-hospitality", "Отель. Premium-warm — sage/sand/cream, photo-rich, large hero imagery. Booking-CTA приоритет."),
    "spa":          ("warm-hospitality", "Spa/wellness — мягкая палитра, calm, серифный display, минимум movement."),
    "salon":        ("warm-hospitality", "Салон красоты — soft warm, photo-led."),
    "florist":      ("warm-hospitality", "Цветы — pastel palette, soft typography, photo-rich."),
    "wedding":      ("warm-hospitality", "Свадьба — romantic palette, serif display, image-heavy."),
    "repair":       ("functional-utility", "Ремонт. Direct, info-first. Палитра — bold primary (синий/оранжевый/красный) для CTA, остальное neutral. Большие телефонные номера в top-bar. Прайс-лист и зоны обслуживания на видном месте."),
    "plumbing":     ("functional-utility", "Сантехника — см. repair."),
    "automotive":   ("functional-utility", "Авто-сервис — см. repair, плюс акцент на бренды/марки."),
    "logistics":    ("functional-utility", "Логистика/перевозки — info-first, tracking-CTA, regional coverage."),
    "locksmith":    ("functional-utility", "Замки/двери — 24/7 phone prominent, fast-response messaging."),
    "construction": ("functional-utility", "Строительство — projects portfolio + контакты в visible CTA."),
    "luxury":       ("premium-luxury", "Premium/luxury. Spacious, considered, expensive feel. Палитра — deep neutrals + champagne/gold accent. Serif display (Cormorant Garamond, Didot-like) + thin grotesque sans. Large hero imagery, минимум motion, тон quiet."),
    "jewelry":      ("premium-luxury", "Ювелирка — см. luxury."),
    "realestate":   ("conservative-professional", "Недвижимость — depends on segment. Эконом → functional-utility, премиум → premium-luxury, mass-market → conservative-professional. Если не ясно — conservative."),
    "ecommerce":    ("functional-utility", "Интернет-магазин — product-first, prominent prices, clear nav by category. CTA — 'Купить'/'В корзину'."),
    "education":    ("conservative-professional", "Образование — trust-led, calm. Палитра — blue/teal/forest. Подчёркивай аккредитацию, преподавателей, результаты студентов."),
    "nonprofit":    ("warm-hospitality", "Некоммерческая — emotive, story-led, donate-CTA приоритет."),
    "government":   ("conservative-professional", "Гос/муниципальный сектор — predictable, accessible, ВЫСОКИЙ контраст, никакого decorative. Палитра — официальная (blue/navy)."),
}


def _industry_guidance(industry: str | None) -> str:
    """Подобрать индустриальную ноту для brief.md.

    Если индустрия в словаре — отдаёт явный совет; иначе — generic fallback,
    который просит Claude выбрать группу из tone matrix в design.md.
    """
    if not industry:
        return (
            "_Industry not specified — read `design.md` Industry tone matrix and pick "
            "the closest group based on brand name and tagline. When in doubt, default "
            "to Conservative-professional._"
        )
    key = industry.strip().lower()
    entry = _INDUSTRY_GROUPS.get(key)
    if entry is None:
        return (
            f"_Industry `{industry}` not in the lookup table — read `design.md` "
            f"Industry tone matrix and pick the closest group based on brand mood. "
            f"Default to Conservative-professional if unclear._"
        )
    group, note = entry
    return f"**Group:** `{group}`\n\n{note}"


def _build_mandatory_tokens_section(tokens: dict | None) -> str:
    """Render the design_tokens from analyze-url as a MANDATORY block in
    the brief. Empty string when no tokens — Claude picks its own.

    Format: ready-to-copy CSS variable block + font list + categorical
    layout hints, all under a "MUST USE EXACTLY" header.
    """
    if not isinstance(tokens, dict) or not tokens:
        return ""

    palette = tokens.get("palette_hsl") or {}
    fonts = tokens.get("fonts") or {}

    lines: list[str] = [
        "",
        "## ⚠ MANDATORY design tokens — picked from a reference site's screenshot",
        "",
        "These values are NOT suggestions — they are LOCKED. Use them",
        "EXACTLY in `src/theme.css` (palette + fonts) and apply the",
        "categorical hints below (hero_pattern, section_rhythm, card_style,",
        "etc) when composing layouts. Picking your own palette/fonts here",
        "would defeat the whole purpose of the reference-driven build.",
        "",
        "**These tokens OVERRIDE `contracts/design.md` and `contracts/frontend-design.md`",
        "when they conflict.** The skill says 'NEVER use Inter/Roboto'; if the tokens",
        "below say `body: \"Roboto\"`, you use Roboto — fidelity to the reference site",
        "matters more than aesthetic generality here. The user explicitly chose this",
        "by running `analyze-url` to extract real values from a source they like.",
        "",
        "### `:root` CSS variables to set (HSL components, no #hex)",
        "",
        "```css",
        ":root {",
    ]
    var_order = [
        "background", "foreground", "card", "card_foreground",
        "primary", "primary_foreground",
        "secondary", "secondary_foreground",
        "accent", "accent_foreground",
        "muted", "muted_foreground",
        "border", "ring",
    ]
    for var_name in var_order:
        value = palette.get(var_name)
        if value:
            css_name = var_name.replace("_", "-")
            lines.append(f"  --{css_name}: {value};")
    radius = tokens.get("radius")
    if radius:
        lines.append(f"  --radius: {radius};")

    display_font = fonts.get("display")
    body_font = fonts.get("body")
    mark_font = fonts.get("mark")
    if display_font:
        lines.append(
            f"  --font-display: \"{display_font}\", system-ui, sans-serif;"
        )
    if body_font:
        lines.append(
            f"  --font-body: \"{body_font}\", system-ui, sans-serif;"
        )
    if mark_font:
        lines.append(
            f"  --font-mark: \"{mark_font}\", system-ui, sans-serif;"
        )
    lines.append("}")
    lines.append("```")
    lines.append("")

    hero_pal = tokens.get("hero_palette_hsl") or {}
    header_pal = tokens.get("header_palette_hsl") or {}
    if hero_pal or header_pal:
        lines.append("### Zone-specific palette overrides (CRITICAL — multi-zone fidelity):")
        lines.append("")
        lines.append("The source design uses DIFFERENT backgrounds per zone (e.g. cream")
        lines.append("header / dark-navy hero / cream body). To preserve this dramatic")
        lines.append("contrast, in `src/theme.css` add these additional CSS variables")
        lines.append("AND use them in your hero / header section components rather than")
        lines.append("the page-level `--background`/`--foreground`.")
        lines.append("")
        lines.append("```css")
        lines.append(":root {")
        if hero_pal.get("background"):
            lines.append(f"  --hero-bg: {hero_pal['background']};")
        if hero_pal.get("foreground"):
            lines.append(f"  --hero-fg: {hero_pal['foreground']};")
        if hero_pal.get("accent"):
            lines.append(f"  --hero-accent: {hero_pal['accent']};")
        if header_pal.get("background"):
            lines.append(f"  --header-bg: {header_pal['background']};")
        if header_pal.get("foreground"):
            lines.append(f"  --header-fg: {header_pal['foreground']};")
        lines.append("}")
        lines.append("```")
        lines.append("")
        lines.append("Use these in your Hero section: `<section style={{ backgroundColor: `hsl(var(--hero-bg))`, color: `hsl(var(--hero-fg))` }}>` or via Tailwind arbitrary values: `bg-[hsl(var(--hero-bg))] text-[hsl(var(--hero-fg))]`.")
        lines.append("")

    if any([display_font, body_font, mark_font]):
        lines.append("### Google Fonts to load in `Layout.tsx` `<head>`:")
        lines.append("")
        family_parts = []
        for fam in filter(None, [display_font, body_font, mark_font]):
            family_parts.append(f"family={fam.replace(' ', '+')}")
        if family_parts:
            url = "https://fonts.googleapis.com/css2?" + "&".join(family_parts) + "&display=swap"
            lines.append(f"`{url}`")
        lines.append("")

    categorical_keys = [
        ("hero_pattern", "Hero composition"),
        ("section_rhythm", "Section rhythm"),
        ("card_style", "Card style"),
        ("motion_style", "Motion style"),
        ("logo_style", "Logo style"),
        ("tone_tag", "Overall tone"),
    ]
    cat_lines = []
    for key, label in categorical_keys:
        val = tokens.get(key)
        if val:
            cat_lines.append(f"- **{label}:** `{val}`")
    if cat_lines:
        lines.append("### Layout & tone (apply these per `design.md` patterns):")
        lines.append("")
        lines.extend(cat_lines)
        lines.append("")

    return "\n".join(lines)


def _truncate_paragraph_drafts(page_dump: dict, max_chars: int = 200) -> None:
    """Обрезать paragraph.markdown в дампе страницы для размера brief'а.

    Claude видит примеры, чтобы понять SHAPE контента. Полный текст ему не нужен,
    он его не использует для генерации — только для понимания типа данных.
    """
    for b in page_dump.get("content_blocks", []):
        if (b.get("kind") == "paragraph") and isinstance(b.get("props"), dict):
            md = b["props"].get("markdown", "")
            if isinstance(md, str) and len(md) > max_chars:
                b["props"]["markdown"] = md[:max_chars].rstrip() + "..."


def build_brief(
    site_content: SiteContent,
    *,
    accent_hsl: str | None = None,
    neutral_family: str | None = None,
    display_font: str | None = None,
    body_font: str | None = None,
    extra_notes: str | None = None,
    design_tokens: dict | None = None,
) -> str:
    """Markdown brief для Claude CLI.

    Args:
        site_content: SiteContent из content_plan + expand_prose.
        accent_hsl: опц. HSL-строка типа "210 100% 50%". Если None — Claude
            подбирает сам по индустрии.
        neutral_family: опц. slate|zinc|stone|gray|neutral.
        display_font / body_font: опц. конкретные семейства; иначе Claude выбирает.
        extra_notes: опц. — дополнительные требования к сайту.
        design_tokens: опц. структурированный объект из ``analyze_url``
            с точными HSL-значениями палитры, font-family'ями, hero_pattern и т.п.
            Если задан — добавляется как MANDATORY-секция в brief; Claude
            ОБЯЗАН использовать эти значения в ``src/theme.css`` и композиции.
    """
    m = site_content.site_meta
    page_types = sorted({p.page_type for p in site_content.pages})
    pages_breakdown = {pt: sum(1 for p in site_content.pages if p.page_type == pt) for pt in page_types}
    modules_kinds = [mod.kind for mod in site_content.modules]

    sample_page = next((p for p in site_content.pages if p.page_type == "home"), site_content.pages[0])
    sample_dump = sample_page.model_dump()
    _truncate_paragraph_drafts(sample_dump, max_chars=200)
    sample_json = json.dumps(sample_dump, ensure_ascii=False, indent=2)

    sample_modules = {mod.kind: mod.data for mod in site_content.modules[:3]}
    modules_json_full = json.dumps(sample_modules, ensure_ascii=False, indent=2)
    modules_json = modules_json_full[:1800] + ("..." if len(modules_json_full) > 1800 else "")

    theme_lines: list[str] = []
    if accent_hsl:
        theme_lines.append(f"- **Accent color (HSL):** `{accent_hsl}`")
    if neutral_family:
        theme_lines.append(f"- **Neutral family:** `{neutral_family}` (slate-like neutral foundation)")
    if display_font:
        theme_lines.append(f"- **Display font:** `{display_font}`")
    if body_font:
        theme_lines.append(f"- **Body font:** `{body_font}`")
    theme_block = "\n".join(theme_lines) if theme_lines else (
        "_None specified — choose design tokens that match the industry and tone of the brand._"
    )

    extras_section = ""
    if extra_notes and extra_notes.strip():
        extras_section = f"\n\n## Additional notes\n\n{extra_notes.strip()}\n"

    mandatory_tokens_section = _build_mandatory_tokens_section(design_tokens)

    industry_guidance = _industry_guidance(m.industry)

    return f"""# Site build brief

## Brand

- **Brand:** {m.brand}
- **Industry:** {m.industry}
- **Language:** {m.language}
- **Tagline:** {m.tagline or "(none — invent suitable one for fallback)"}
{mandatory_tokens_section}
## Industry guidance

{industry_guidance}

Read `design.md` "Industry tone matrix" for the full mapping. The note above is
this site's specific anchor — apply it to header treatment, hero pattern, palette
saturation, and typography choices.

## Theme hints

{theme_block}

## Pages and templates

The site has {len(site_content.pages)} pages total, by page_type:

{json.dumps(pages_breakdown, ensure_ascii=False, indent=2)}

You MUST produce one `templates/<page_type>.html` file for each unique page_type
listed above. ALL of these must exist: {page_types}.

## Modules the site uses

The orchestrator injects these site-level modules at render time:

{modules_kinds}

In `_layout.html` and page templates, guard each module section with
`{{% if has_module("<name>") %}}`. Modules data has its own shape — see the
sample below + `contract.md` for the full module render contract.

## Sample page (one of {len(site_content.pages)})

This is `/{sample_page.slug}` (`page_type={sample_page.page_type!r}`, paragraph
markdown truncated to ~200 chars for brevity — actual content will be longer):

```json
{sample_json}
```

## Sample modules data

```json
{modules_json}
```

## Your task

1. Read `contract.md` for the EXACT slot/render contract — required globals
   (`site`, `page`, `content`, `modules`, `nav`), `content_blocks` block-render
   contract, module render contracts. **You must follow it exactly.**
2. Read `design.md` for the design system — HSL palette via custom properties,
   spacing scale (4/8/12/16/24/32/48/64/96/128), type scale, native
   interactivity primitives (`<details>`, `<dialog>`).
3. Pick design tokens (accent HSL, neutral family, fonts, radius) appropriate
   for industry `"{m.industry}"` and language `"{m.language}"`. Document them
   in `manifest.json.design_tokens`.
4. Build the templates:
   - `templates/_layout.html` — the shell: `<html>`, `<head>`, `<body>`, with
     `{{% block content %}}{{% endblock %}}` for page content. Include
     `_partials/nav.html` and `_partials/footer.html`. Wire stylesheet and
     script links using `{{{{ assets }}}}/styles/bundle.<hash>.css` and
     `{{{{ assets }}}}/scripts/bundle.<hash>.js` — the hash matches what you
     declare in `manifest.asset_hashes`.
   - `templates/_partials/nav.html`, `templates/_partials/footer.html`
   - One `templates/<page_type>.html` for each page_type listed above.
     Each extends `_layout.html` via `{{% extends "_layout.html" %}}`.
5. Write `styles/bundle.<8hex>.css` — entire stylesheet. The 8hex hash is the
   first 8 chars of sha256 of the file's text content (any hash works as long
   as it matches what you put in `manifest.asset_hashes.css`).
6. Write `scripts/bundle.<8hex>.js` — vanilla JS for interactivity (mobile nav
   toggle, accordion polish, form validation). KEEP UNDER 5KB. Empty file with
   just a comment is fine if templates don't need JS.
7. Write `manifest.json` with the EXACT shape from `contract.md` (see "manifest.json
   schema"). Critically:
   - `page_types`: array of unique page_types you produced templates for.
   - `page_slots["<type>"]`: list of slots used in that template (subset of
     `["hero", "content_blocks"]` + any module names you reference with
     `{{% if has_module(...) %}}`).
   - `asset_hashes.css` and `.js`: 8-char SHA256 prefixes matching your actual
     file contents (the gateway will validate this!).
   - `design_tokens`: the values you picked.

When you're done, write a brief 2-3 sentence summary of what you built. {extras_section}

## Constraints (do not break these)

- NO Tailwind, React, Vue, or any framework. Vanilla CSS + minimal vanilla JS only.
- NO external CDN imports (no `<script src="https://...`, no `@import url(https://...`).
- All colors must use HSL via CSS custom properties on `:root`. No hex codes outside
  comments.
- All sizes must come from the spacing scale (multiples of 4) and type scale (12–60).
- Sandboxed Jinja runtime — your templates must NOT use Python attribute tricks like
  `{{{{ ''.__class__... }}}}` or import-like constructs.
- `bundle.js` ≤ 5 KB uncompressed.
- Don't write files outside the current workspace.
"""
