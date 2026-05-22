from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.adapters.errors import AdapterError
from app.core.config import get_settings
from app.core.llm_provider_factory import make_text_llm

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (claudesite-analyze/0.1) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)
_FETCH_TIMEOUT = 15.0
_MAX_PAGE_BYTES = 800_000
_BLOCK_TAGS = ("script", "style", "noscript", "iframe", "svg")
_PRIORITY_KEYWORDS = (
    "about", "service", "услуг", "продукт", "product", "price",
    "цен", "tariff", "тариф", "case", "portfolio", "портфол",
    "blog", "блог", "о нас", "о компании",
)


def _normalize_url(url: str) -> str:
    url = url.strip()
    p = urlparse(url)
    if not p.scheme:
        url = "https://" + url
        p = urlparse(url)
    if not p.netloc:
        raise ValueError(f"invalid URL: {url!r}")
    if p.scheme not in ("http", "https"):
        raise ValueError(f"only http/https supported, got: {p.scheme!r}")
    return url


def _fetch_html(client: httpx.Client, url: str) -> str:
    r = client.get(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept": "text/html"},
        follow_redirects=True,
    )
    r.raise_for_status()
    ct = r.headers.get("content-type", "").lower()
    if ct and "html" not in ct:
        raise ValueError(f"not HTML content-type: {ct!r}")
    return r.text[:_MAX_PAGE_BYTES]


def _parse_page(html: str, *, source_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_BLOCK_TAGS):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    meta_desc = ""
    md = soup.find("meta", attrs={"name": "description"})
    if md and md.get("content"):
        meta_desc = md["content"].strip()

    headings: list[tuple[str, str]] = []
    for h in soup.find_all(["h1", "h2"]):
        txt = h.get_text(" ", strip=True)
        if txt:
            headings.append((h.name, txt[:200]))
        if len(headings) >= 30:
            break

    nav_links: list[tuple[str, str]] = []
    nav_containers = soup.find_all("nav") or [soup.find("header") or soup]
    seen_hrefs: set[str] = set()
    for container in nav_containers:
        if container is None:
            continue
        for a in container.find_all("a", href=True):
            href = (a["href"] or "").strip()
            label = a.get_text(" ", strip=True)
            if not href or not label:
                continue
            if href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            full = urljoin(source_url, href)
            if full in seen_hrefs:
                continue
            seen_hrefs.add(full)
            nav_links.append((label[:60], full))
            if len(nav_links) >= 15:
                break
        if len(nav_links) >= 15:
            break

    body_text = soup.get_text(" ", strip=True)
    body_text = re.sub(r"\s+", " ", body_text)[:4000]

    return {
        "title": title,
        "meta_description": meta_desc,
        "headings": headings,
        "nav_links": nav_links,
        "text": body_text,
    }


def _pick_inner_pages(homepage: dict, base_url: str, *, n: int) -> list[str]:
    base_host = urlparse(base_url).netloc
    base_url_norm = base_url.rstrip("/")

    candidates: list[tuple[int, str]] = []
    for label, link in homepage["nav_links"]:
        p = urlparse(link)
        if p.netloc and p.netloc != base_host:
            continue
        if link.rstrip("/") == base_url_norm:
            continue
        signal = (label + " " + link).lower()
        priority = 1 if any(kw in signal for kw in _PRIORITY_KEYWORDS) else 0
        candidates.append((priority, link))

    candidates.sort(key=lambda x: -x[0])
    return [link for _, link in candidates[:n]]


_ANALYZE_SYSTEM = (
    "You are a brand designer doing PIXEL-LEVEL extraction from a website "
    "screenshot. You receive the page text/structure AND a screenshot of "
    "the homepage. Produce a JSON object with TWO fields:\n\n"
    "  - `prompt` — one dense paragraph in the source's language describing "
    "what to build (content + audience + tone).\n"
    "  - `design_tokens` — strict structured object. Values MUST come from "
    "ACTUAL PIXELS in the screenshot, NOT from industry stereotypes.\n\n"
    "CRITICAL: Many landing pages have DIFFERENT palettes per zone — the "
    "header may be cream, the hero may be dark navy, the body may be white. "
    "You must extract palettes ZONE-BY-ZONE. Do not collapse multi-zone "
    "designs into a single set of 'page colors' — that destroys the "
    "dramatic contrast the original designer chose.\n\n"
    "Output ONLY the JSON object — no markdown fences, no preamble, no "
    "explanation."
)


_ANALYZE_PROMPT_TEMPLATE = """Analyze this website (text below + screenshot
attached) and emit a single JSON object with exactly this shape. Values
MUST come from ACTUAL PIXELS in the screenshot — not from generic
"how legal sites usually look" stereotypes.

{{
  "prompt": "<dense single paragraph, 350-600 words, in the source language>",
  "design_tokens": {{
    "palette_hsl": {{
      "_comment": "PAGE-LEVEL palette — the COMMON colors used across most of the body. Look at the long stretch of the page (not just the hero).",
      "background":         "<H S% L%>",
      "foreground":         "<H S% L%>",
      "card":               "<H S% L%>",
      "card_foreground":    "<H S% L%>",
      "primary":            "<H S% L%>",
      "primary_foreground": "<H S% L%>",
      "secondary":          "<H S% L%>",
      "secondary_foreground":"<H S% L%>",
      "accent":             "<H S% L%>",
      "accent_foreground":  "<H S% L%>",
      "muted":              "<H S% L%>",
      "muted_foreground":   "<H S% L%>",
      "border":             "<H S% L%>",
      "ring":               "<H S% L%>"
    }},
    "hero_palette_hsl": {{
      "_comment": "HERO-SECTION palette — if the hero uses a DRAMATICALLY different background (dark navy hero on a cream page, or a full-bleed photo overlay, etc), extract THOSE pixel values here. If hero uses the same palette as page, copy `background`/`foreground`/`accent` values from `palette_hsl` above.",
      "background":         "<H S% L%>",
      "foreground":         "<H S% L%>",
      "accent":             "<H S% L%>"
    }},
    "header_palette_hsl": {{
      "_comment": "TOP NAVIGATION palette — frequently lighter/cream when the hero is dark. Extract the bg of the topmost ~80px strip of the screenshot.",
      "background":         "<H S% L%>",
      "foreground":         "<H S% L%>"
    }},
    "fonts": {{
      "display": "<Google-Fonts family, e.g. 'Cormorant Garamond' — based on letterforms in the actual screenshot>",
      "body":    "<Google-Fonts family>",
      "mark":    "<Google-Fonts family for UI marks / buttons / badges>"
    }},
    "hero_pattern":   "<split-text-image | centered-bold | full-bleed-bg | top-bar-trust | minimal-text-only | photo-overlay | side-aside-card | dark-hero-light-page>",
    "section_rhythm": "<alternating-bg | inverse-bands | heavy-dividers | monotone>",
    "card_style":     "<solid | outlined | elevated | glass>",
    "motion_style":   "<subtle | slide-up | scale-in | bold>",
    "logo_style":     "<wordmark | icon-only | monogram | illustrative>",
    "radius":         "<0 | 0.25rem | 0.5rem | 1rem | 9999px>",
    "tone_tag":       "<conservative-professional | bold-tech | warm-hospitality | premium-luxury | editorial-creative | minimal-saas | playful-consumer | brutalist | other>"
  }}
}}

PIXEL-LEVEL EXTRACTION RULES (read these CAREFULLY before answering):

1. **Multi-zone palettes are common.** Many high-end sites use a DIFFERENT
   background per zone: cream header + dark-navy hero + white body + dark
   footer is one common pattern. DO NOT collapse all of these into a single
   `background`. The hero zone often has the MOST distinctive color treatment
   in the entire site — capture it in `hero_palette_hsl`, separate from
   `palette_hsl.background`.

2. **Look at actual pixels.** Pick up a virtual eyedropper to the EXACT
   colors you see — don't substitute "what a legal site should look like".
   If the hero is `#0b1f3a` (deep navy with hint of warmth), that's
   `215 70% 14%`-ish, NOT `210 50% 10%` generic blue.

3. **Find the accent.** The accent is the COLOR-OF-EMPHASIS — usually one
   sharp non-neutral hue used for buttons, link underlines, decorative
   strokes. On warm-luxury sites it's often gold/champagne (`#c9a96e`,
   `35 40% 60%`), not amber/orange. Don't reach for `35 90% 50%` if the
   actual accent has lower saturation.

4. **Fonts**: identify the actual families. Serif italic on the hero =
   probably Cormorant Garamond / Playfair Display / EB Garamond. Geometric
   sans = Geist / Söhne / Manrope. Don't default to Roboto / Open Sans /
   Arial just because you're unsure — pick the closest Google Fonts match
   to what you SEE.

5. **hero_pattern**: pick the OBSERVED layout, not the industry default.
   If you see dark-bg hero with light text + a contrast band below, that's
   `dark-hero-light-page`. If you see a centered massive serif on a flat
   page, that's `centered-bold`. If you see split text-left + image-right,
   that's `split-text-image`.

The `prompt` paragraph must include:
- WHAT (industry/niche) + format (lead-gen / catalog / blog-driven / portfolio)
- WHO (target audience, geo + segment)
- BRAND (name, tagline, USP)
- PAGES (5-8 pages this site should have, one sentence each)
- KEY MODULES (features/stats/testimonials/pricing/faq/team/contact_info — list what the source clearly uses)
- SPECIFIC CONTENT (3-7 concrete services/products/features in source's terminology)

NO markdown fences (no ```json…```), no commentary, no leading "Here is the JSON". Just the raw JSON object as the entire response.

=== SOURCE WEBSITE ===
URL: {url}
Title: {title}
Meta description: {meta_desc}

Headings (h1/h2):
{headings}

Navigation:
{nav}

Body text from {n_pages} page(s):
{body_text}
""".strip()


_ANALYZE_TEXT_ONLY_NOTE = (
    "\n\nIMPORTANT: screenshot was unavailable. For `design_tokens`, use "
    "industry conventions + visible text style as best-guess and set "
    "`tone_tag` accordingly — DO NOT leave palette/font fields blank."
)


def _format_for_llm(homepage: dict, inner: list[dict], source_url: str) -> str:
    headings_lines = "\n".join(
        f"  {tag.upper()}: {txt}" for tag, txt in homepage["headings"]
    ) or "  (none)"
    nav_lines = "\n".join(
        f"  {lab} → {url}" for lab, url in homepage["nav_links"]
    ) or "  (none)"

    parts = [f"--- HOMEPAGE ({source_url}) ---\n{homepage['text']}"]
    for ip in inner:
        label = ip.get("title") or ip.get("source", "(inner)")
        parts.append(f"--- {label} ({ip['source']}) ---\n{ip['text']}")
    body_text = "\n\n".join(parts)[:14_000]

    return _ANALYZE_PROMPT_TEMPLATE.format(
        url=source_url,
        title=homepage["title"] or "(no title tag)",
        meta_desc=homepage["meta_description"] or "(none)",
        headings=headings_lines,
        nav=nav_lines,
        n_pages=1 + len(inner),
        body_text=body_text,
    )


def _strip_fences(s: str) -> str:
    t = (s or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def _parse_vision_json(raw: str) -> dict:
    """Parse the vision-LLM response. Expected to be a JSON object with
    `prompt` (str) and `design_tokens` (object). Falls back to json_repair
    on borderline-malformed output."""
    import json
    t = _strip_fences(raw)
    if not t.startswith("{"):
        start = t.find("{")
        if start >= 0:
            t = t[start:]
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        from json_repair import repair_json
        data = json.loads(repair_json(t))
    if not isinstance(data, dict):
        raise ValueError(f"vision returned non-object JSON: {type(data).__name__}")
    return data


def analyze_url(
    url: str,
    *,
    inner_pages: int = 2,
    skip_screenshot: bool = False,
) -> dict:
    """Превратить ссылку в подробный prompt для site-generation.

    Делает: fetch главной + до N nav-ссылок (текст) + screenshot главной
    через Playwright Chromium → отправляет всё в vision-LLM (OpenAI
    chat/completions через ``OPENAI_BASE_URL``) с моделью
    ``llm_openai_vision_model``. На выходе — один плотный абзац с content
    + design сигналами.

    Если скриншот не удался — graceful fallback на text-only LLM
    (тот же ``make_text_llm`` что и в content_plan); brief получится менее
    точным по дизайну, но всё ещё useful.

    Args:
        url: ссылка (http(s):// добавится если нет).
        inner_pages: сколько nav-ссылок дочитать после главной (0-5).
        skip_screenshot: явно отключить vision-pass (для отладки или когда
            Playwright недоступен).

    Returns:
        {
            "prompt":          str,         # dense paragraph for user_prompt
            "design_tokens":   dict | None, # palette_hsl/fonts/hero_pattern/...
                                            # populated when screenshot+vision
                                            # succeeded; None on fallback path
            "source_url":      str,
            "pages_analyzed":  [str],       # URLs фактически загруженных html
            "screenshot_used": bool,        # True если vision-pass отработал
            "target_pages":    int,         # default 6
        }

    Raises:
        ValueError: некорректный URL или не-HTML ответ.
        httpx.HTTPError: ошибка фетча HTML.
        AdapterError: LLM-провайдер недоступен.
    """
    url = _normalize_url(url)
    inner_pages = max(0, min(int(inner_pages), 5))

    with httpx.Client(timeout=_FETCH_TIMEOUT) as client:
        html = _fetch_html(client, url)
        home = _parse_page(html, source_url=url)
        home["source"] = url

        inner_data: list[dict] = []
        if inner_pages > 0:
            picked = _pick_inner_pages(home, url, n=inner_pages)
            for inner_url in picked:
                try:
                    inner_html = _fetch_html(client, inner_url)
                    inner_p = _parse_page(inner_html, source_url=inner_url)
                    inner_p["source"] = inner_url
                    inner_data.append(inner_p)
                except (httpx.HTTPError, ValueError) as e:
                    logger.info("analyze_url_skip_inner url=%s err=%s", inner_url, e)

    screenshot_png: bytes | None = None
    if not skip_screenshot:
        try:
            from app.services.screenshot import take_screenshot, ScreenshotError
            try:
                screenshot_png = take_screenshot(url)
            except ScreenshotError as e:
                logger.warning("analyze_url_screenshot_failed url=%s err=%s", url, e)
        except ImportError as e:
            logger.warning("playwright_unavailable: %s — falling back to text-only", e)

    user_msg = _format_for_llm(home, inner_data, url)
    settings = get_settings()

    if screenshot_png is not None:
        from app.adapters.openai_vision import OpenAIVisionAdapter
        vision = OpenAIVisionAdapter(settings)
        raw = vision.generate_from_image(
            prompt=user_msg,
            system=_ANALYZE_SYSTEM,
            image_bytes=screenshot_png,
            mime_type="image/png",
        )
        screenshot_used = True
    else:
        llm = make_text_llm(settings)
        raw = llm.generate(
            prompt=user_msg + _ANALYZE_TEXT_ONLY_NOTE,
            system=_ANALYZE_SYSTEM,
        )
        screenshot_used = False

    # Parse JSON output (prompt + design_tokens). On malformed JSON fall
    # back to treating the whole response as the prompt and skipping tokens.
    prompt_text: str = ""
    design_tokens: dict | None = None
    try:
        parsed = _parse_vision_json(raw)
        prompt_text = (parsed.get("prompt") or "").strip()
        tokens = parsed.get("design_tokens")
        if isinstance(tokens, dict) and tokens:
            design_tokens = tokens
        if not prompt_text:
            # Vision skipped the prompt field — degenerate but recoverable.
            prompt_text = _strip_fences(raw)
            logger.warning("analyze_url_no_prompt_field source=%s", url)
    except (ValueError, ImportError) as e:
        logger.warning(
            "analyze_url_json_parse_failed source=%s err=%s — treating raw as prompt",
            url, e,
        )
        prompt_text = _strip_fences(raw)

    pages_analyzed = [url] + [p["source"] for p in inner_data]

    return {
        "prompt": prompt_text,
        "design_tokens": design_tokens,
        "source_url": url,
        "pages_analyzed": pages_analyzed,
        "screenshot_used": screenshot_used,
        "target_pages": 6,
    }
