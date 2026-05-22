from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.adapters.errors import AdapterError
from app.core.config import get_settings
from app.core.llm_provider_factory import make_text_llm
from app.schemas.site_content import ContentBlock, Page

logger = logging.getLogger(__name__)


HUMANIZATION_RULES = (
    "Стилистические правила (обязательны, проверяются на анти-AI):\n"
    "- Длинное тире (—) запрещено. Используй только короткое (-) или перестраивай предложение.\n"
    "- Не более 2 запятых в одном предложении.\n"
    "- Маркированных и нумерованных списков суммарно не более 2 на всю статью.\n"
    "- Геометрия рандомная: длина абзацев варьируется (1–6 предложений), длина предложений тоже разная. Не делай симметричные ритмы.\n"
    "- Тон экспертный, от лица компании. Конкретика: цифры, реальные сервисы и инструменты с настоящими названиями (Яндекс Директ, VK Ads, myTarget, 1С, СБИС и т.п.), а не «крупная сеть» или «известная платформа».\n"
    "- Запрещено: lorem-плейсхолдеры, незачищенные шаблоны, дословные повторы ключевой фразы, абстрактные «лидеры рынка», симметричные оппозиции в духе «X vs Y», избыточные кавычки, шаблонные сравнительные формулировки.\n"
    "- Минимум воды: каждый абзац несёт факт, цифру, совет или конкретный пример. Без вводных штампов.\n"
)


_TARGET_CHARS_BY_PAGE_TYPE: dict[str, int] = {
    "blog_post": 3500,
    "service": 1500,
    "about": 1500,
    "services": 700,
    "blog_index": 600,
    "home": 1200,
    "contacts": 400,
}


def _target_chars(page_type: str) -> int:
    return _TARGET_CHARS_BY_PAGE_TYPE.get(page_type, 1000)


def _build_prompt(
    *,
    blocks: list[dict[str, Any]],
    brand: str,
    keyword: str,
    page_type: str,
    title: str,
    target_chars: int,
) -> str:
    upper_bound = int(target_chars * 1.3)
    blocks_json = json.dumps(blocks, ensure_ascii=False, indent=2)
    return f"""Ты пишешь основной текст страницы сайта '{brand}'.
Ключевая фраза: {keyword}
Тип страницы: {page_type}
Заголовок: {title}

Страница состоит из типизированных блоков (JSON). Каждый блок имеет
shape `{{"kind": "<kind>", "props": {{...}}}}`. Тебе нужно раскрыть
КАЖДЫЙ блок с `kind="paragraph"` — превратить черновой `props.markdown`
в полноценный экспертный текст:

```json
{blocks_json}
```

Правила:
- Суммарный объём текста во всех paragraph-блоках страницы около {target_chars}
  символов (диапазон {target_chars}-{upper_bound}; НЕ превышай {upper_bound}).
  Если получается длиннее — сокращай за счёт повторов и воды, не за счёт фактов.
- Каждый paragraph раскрывает СВОЙ контекст: смысл черновика сохраняется,
  расширяется до полноценного абзаца с конкретикой (числа, реальные платформы,
  пошаговые объяснения, примеры). Без воды, без штампов «Стоит отметить»,
  «Таким образом», «В современных реалиях».
- Inline-markdown: используй **bold**, *em*, [link](href), `code` где уместно.
  НЕ используй markdown-заголовки (##) внутри paragraph — заголовки уже есть
  как отдельные блоки kind="heading".
- Блоки других kinds (heading, image, list, quote, table, cta) верни СТРОГО
  1-в-1 без изменений.
- НЕ добавляй, не удаляй, не переставляй блоки: тот же список, тот же
  порядок, те же kinds.
- Каждый блок: {{"kind": "<kind>", "props": {{...}}}}.
- Верни СТРОГО валидный JSON-массив всех блоков, без преамбулы и без
  markdown-обёртки (никаких ```json ...```).

{HUMANIZATION_RULES}"""


def _extract_json_array(text: str) -> list:
    """Извлечь JSON-массив из ответа LLM, переживая markdown-обёртки."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    if not t.startswith("["):
        start = t.find("[")
        if start == -1:
            raise ValueError(f"no JSON array in output, head={text[:200]!r}")
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
            elif c == "[":
                depth += 1
            elif c == "]":
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


_CONTENT_BLOCKS_ADAPTER = TypeAdapter(list[ContentBlock])


def expand_page_prose(
    page: Page,
    *,
    brand: str,
    keyword: str,
) -> Page:
    """Раскрыть paragraph-черновики страницы в полноценный текст.

    Args:
        page: страница из content_plan (со схематичными drafт-paragraph'ами).
        brand: имя бренда (для тона).
        keyword: ключевая фраза/тема страницы (для контекста и SEO).

    Returns:
        Новый объект Page с расширенными content_blocks. Если на странице
        нет ни одного paragraph-блока — возвращает оригинал без LLM-вызова.

    Raises:
        ValueError: невалидный JSON-ответ, или LLM поменял структуру блоков
            (другой order/length/kinds), или pydantic-валидация выходных
            блоков провалилась.
        AdapterError: LLM-провайдер недоступен.
    """
    blocks_in = page.content_blocks
    if not blocks_in:
        logger.info("expand_skip page=%s no content_blocks", page.slug)
        return page

    has_paragraph = any(b.kind == "paragraph" for b in blocks_in)
    if not has_paragraph:
        logger.info("expand_skip page=%s no paragraph blocks", page.slug)
        return page

    target = _target_chars(page.page_type)
    blocks_dump = [b.model_dump() for b in blocks_in]

    settings = get_settings()
    llm = make_text_llm(settings)
    prompt = _build_prompt(
        blocks=blocks_dump,
        brand=brand,
        keyword=keyword,
        page_type=page.page_type,
        title=page.title,
        target_chars=target,
    )

    raw = llm.generate(
        prompt=prompt,
        system="You are expanding draft paragraphs into expert long-form copy.",
    )

    try:
        out = _extract_json_array(raw)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"expand_page_prose: JSON parse failed for /{page.slug}: {e}; head={raw[:200]!r}") from e

    if not isinstance(out, list):
        raise ValueError(f"expand_page_prose: top-level is not array: {type(out).__name__}")

    if len(out) != len(blocks_in):
        raise ValueError(
            f"expand_page_prose: block count changed {len(blocks_in)}→{len(out)} on /{page.slug}"
        )
    for i, (orig, new) in enumerate(zip(blocks_in, out)):
        new_kind = (new or {}).get("kind")
        if new_kind != orig.kind:
            raise ValueError(
                f"expand_page_prose: block[{i}] kind changed {orig.kind!r}→{new_kind!r} on /{page.slug}"
            )

    try:
        validated = _CONTENT_BLOCKS_ADAPTER.validate_python(out)
    except ValidationError as e:
        raise ValueError(f"expand_page_prose: pydantic validation failed for /{page.slug}: {e}") from e

    expanded_chars = sum(
        len(b.props.get("markdown", ""))
        for b in validated
        if b.kind == "paragraph"
    )
    draft_chars = sum(
        len(b.props.get("markdown", ""))
        for b in blocks_in
        if b.kind == "paragraph"
    )
    logger.info(
        "expand_page_prose page=%s page_type=%s draft=%d expanded=%d target=%d",
        page.slug, page.page_type, draft_chars, expanded_chars, target,
    )

    validated = _maybe_humanize_paragraphs(validated, page_slug=page.slug)

    return page.model_copy(update={"content_blocks": validated})


def _maybe_humanize_paragraphs(blocks: list, *, page_slug: str) -> list:
    """Прогнать каждый paragraph через Smodin.humanize() при enabled.

    Soft-skip на ошибки Smodin — оставляем LLM-вариант. Очень короткие
    (≤200 chars) и очень длинные (>3500 chars — Smodin free лимит) пропускаем.
    """
    settings = get_settings()
    if settings.pipeline_disable_smodin:
        return blocks
    if not (settings.smodin_api_key and settings.smodin_humanize_url):
        logger.info("smodin_skip_no_config page=%s", page_slug)
        return blocks

    from app.adapters.errors import AdapterError
    from app.adapters.smodin import SmodinAdapter

    adapter = SmodinAdapter(settings=settings)
    humanized = 0
    skipped = 0
    for b in blocks:
        if b.kind != "paragraph":
            continue
        md = b.props.get("markdown", "")
        if not isinstance(md, str) or not (200 < len(md) < 3500):
            skipped += 1
            continue
        try:
            new_md = adapter.humanize(text=md)
        except AdapterError as e:
            logger.warning("smodin_soft_skip page=%s err=%s", page_slug, e)
            skipped += 1
            continue
        if new_md and new_md.strip():
            b.props["markdown"] = new_md
            humanized += 1
    logger.info(
        "smodin_pass page=%s humanized=%d skipped=%d",
        page_slug, humanized, skipped,
    )
    return blocks


def expand_site_prose(
    *,
    pages: list[Page],
    brand: str,
) -> list[Page]:
    """Прогнать expand_page_prose по всем страницам сайта ПАРАЛЛЕЛЬНО.

    Каждая страница = один LLM-вызов на EU-gateway, чисто I/O-bound — катит
    ThreadPool. ``pipeline_expand_prose_max_concurrency`` из Settings рулит
    числом одновременных вызовов (default 4, EU-gateway держит 8).

    Порядок страниц на выходе сохранён (input order). Ошибка на одной
    странице роняет всю операцию — поведение совместимо с прежним последова-
    тельным вариантом (fail-loud).
    """
    from concurrent.futures import ThreadPoolExecutor

    if not pages:
        return []

    settings = get_settings()
    workers = max(1, min(settings.pipeline_expand_prose_max_concurrency, len(pages)))

    def _one(p: Page) -> Page:
        return expand_page_prose(p, brand=brand, keyword=p.title or p.slug)

    out: list[Page] = [None] * len(pages)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="expand-prose") as pool:
        futures = [pool.submit(_one, p) for p in pages]
        for i, fut in enumerate(futures):
            out[i] = fut.result()
    logger.info(
        "expand_site_prose_done pages=%d workers=%d",
        len(pages), workers,
    )
    return out
