from __future__ import annotations

import html
import io
import logging
import re
from random import Random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.errors import AdapterConfigurationError
from app.adapters.gemini_image import GeminiImageAdapter
from app.adapters.openai_image import OpenAIImageAdapter
from app.core.site_config_schema import ImagePipelineConfig
from app.core.site_runtime import SiteRuntime
from app.db.models.enums import SiteMode
from app.db.models.page import Page
from app.db.models.page_revision import PageRevision
from app.db.repos.media import MediaRepository
from app.schemas.site_content import SiteContent

logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def render_template(tpl: str, ctx: dict[str, str]) -> str:
    """Подстановка ``{{key}}`` — раньше жила в удалённом seo_resolve.py."""
    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return ctx.get(key, "")
    return _PLACEHOLDER_RE.sub(repl, tpl)


def _safe_base_name(text: str, *, max_len: int = 72) -> str:
    s = (text or "image").strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^\w\-]+", "-", s, flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    return (s[:max_len] if s else "image")


def _uploads_root(runtime: SiteRuntime) -> Path:
    if runtime.effective_mode == SiteMode.CUSTOM and runtime.file.custom and runtime.file.custom.uploads_base_path:
        return Path(runtime.file.custom.uploads_base_path).expanduser()
    if runtime.file.wordpress and runtime.file.wordpress.uploads_base_path:
        return Path(runtime.file.wordpress.uploads_base_path).expanduser()
    raise AdapterConfigurationError(
        "Configure wordpress.uploads_base_path or custom.uploads_base_path for image generation",
    )


def _public_origin(runtime: SiteRuntime) -> str:
    if runtime.effective_mode == SiteMode.CUSTOM and runtime.file.custom:
        return (runtime.file.custom.public_base_url or "").rstrip("/")
    if runtime.file.wordpress and runtime.file.wordpress.public_site_url:
        return (runtime.file.wordpress.public_site_url or "").rstrip("/")
    return ""


def public_uploads_url(runtime: SiteRuntime, rel_path: str) -> str:
    """Public URL для файла внутри uploads.

    Route ``GET /uploads/{site_slug}/{rel_path:path}`` требует slug в URL —
    значит и для CUSTOM, и для WordPress mode мы префиксуем путь slug'ом.
    """
    rel_path = rel_path.lstrip("/")
    if runtime.effective_mode == SiteMode.CUSTOM:
        return f"/uploads/{runtime.slug}/{rel_path}"
    origin = _public_origin(runtime)
    if origin:
        return f"{origin}/uploads/{runtime.slug}/{rel_path}"
    return f"/uploads/{runtime.slug}/{rel_path}"


def _make_provider(cfg: ImagePipelineConfig) -> Any:
    p = (cfg.provider or "openai").lower().strip()
    if p == "openai":
        return OpenAIImageAdapter(model=cfg.openai_model, size=cfg.openai_size)
    if p == "gemini":
        return GeminiImageAdapter(
            model=cfg.gemini_model,
            aspect_ratio=cfg.gemini_aspect_ratio,
            image_size=cfg.gemini_image_size,
        )
    raise AdapterConfigurationError(f"Unknown pipeline.images.provider: {cfg.provider!r}")


def _build_variants(img: Image.Image, widths: list[int]) -> dict[int, Image.Image]:
    w0, h0 = img.size
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    out: dict[int, Image.Image] = {}
    for tw in sorted(set(widths)):
        rw = min(int(tw), w0)
        if rw < 1:
            continue
        if rw in out:
            continue
        rh = max(1, int(h0 * rw / w0))
        out[rw] = img.resize((rw, rh), Image.Resampling.LANCZOS)
    return out


_DEFAULT_VARIATION_HINTS: tuple[str, ...] = (
    "Extreme wide / establishing: main subject small in frame; environment dominates.",
    "Tight detail or macro: one texture, object fragment, or pattern fills most of the frame.",
    "Low camera height; upward emphasis on vertical structures or tall forms.",
    "High or elevated viewpoint; flattened perspective; broad overview.",
    "Subject clearly off-center (rule of thirds); generous intentional negative space.",
    "Formal centered symmetry; balanced masses left and right.",
    "Strong diagonal rhythm; leading lines across the frame at an angle.",
    "Foreground framing: a nearer plane (sharp or soft) frames the main subject deeper in.",
    "Rim light or silhouette: dark subject edge against a brighter field.",
    "Chiaroscuro lean: mostly shadow with one controlled highlight.",
    "Sparse composition: very few elements; minimal clutter.",
    "Clear three-plane depth: readable foreground, mid-ground, background separation.",
    "Environmental scale shot: subject shown clearly within its setting.",
    "Compressed telephoto feel: stacked layers, compressed depth between planes.",
)


def _variation_hints_pool(cfg: ImagePipelineConfig) -> tuple[str, ...]:
    if cfg.variation_hints:
        t = tuple(h.strip() for h in cfg.variation_hints if h and str(h).strip())
        return t if t else _DEFAULT_VARIATION_HINTS
    return _DEFAULT_VARIATION_HINTS


def _compose_image_prompt(
    *,
    base: str,
    index: int,
    total: int,
    page_id: int,
    revision_id: int,
    hints: Sequence[str],
) -> str:
    if total <= 1:
        return base
    pool = tuple(hints)
    if not pool:
        pool = _DEFAULT_VARIATION_HINTS
    rng = Random(revision_id * 1_000_003 + page_id * 17 + index * 7919)
    if index == 0:
        return (
            f"{base} Hero/opening image: one clear focal subject; readable when scaled down; "
            "avoid repeating the same clichéd stock composition another illustration might use."
        )
    hint = rng.choice(pool)
    return (
        f"{base} Illustration {index + 1} of {total} for the same article — must look "
        f"VISUALLY DISTINCT from any other illustration (different framing, distance, crop, dominant element). "
        f"Composition constraint: {hint} "
        "Same overall style and lighting family as the set, but not the same picture with tiny changes. "
        "No text, letters, or watermarks in the image."
    )


def attach_images_to_site_content(
    content: SiteContent,
    *,
    site_id: int,
    runtime: SiteRuntime,
    session_factory,
) -> SiteContent:
    """Сгенерить один hero на страницу параллельно (опт. C).

    Должна вызываться ПОСЛЕ ``persist_site_content`` (нужны ``pages.id`` для
    FK в media-записях). По каждой ``content.pages[i]`` в потоке:

    - дергает ``OpenAIImageAdapter.generate(prompt=...)``;
    - сохраняет источник как PNG, варианты как WebP+AVIF по ``cfg.srcset_widths``;
    - открывает СВОЮ session через ``session_factory``, пишет ``Media``-строки,
      UPDATE'ит ``pages.hero_image``, коммитит и закрывает session;
    - мутирует ``content.pages[i].hero_image`` чтобы ``generate_initial_site``
      получил URL в site_content.

    Параллелизм управляется ``settings.pipeline_image_max_concurrency``
    (default 3 — консервативно под gpt-image-1 ~5 RPM лимит). Каждый поток
    держит свой httpx-клиент (новый ``with httpx.Client(...)`` на вызов),
    свою SQLAlchemy session, свой Pillow Image — никаких shared mutable
    объектов между потоками. Падение страницы логируется как WARNING и
    не валит остальные.
    """
    cfg = runtime.file.pipeline.images
    if not cfg.enabled:
        return content
    try:
        root = _uploads_root(runtime)
    except AdapterConfigurationError as e:
        logger.warning("image_attach_skip_no_uploads: %s", e)
        return content

    adapter = _make_provider(cfg)
    widths = sorted(set(cfg.srcset_widths))
    now = datetime.now(UTC).replace(tzinfo=None)
    y, m = f"{now.year:04d}", f"{now.month:02d}"
    dest_dir = root / y / m
    dest_dir.mkdir(parents=True, exist_ok=True)
    brand = content.site_meta.brand

    with session_factory() as s:
        db_rows = s.scalars(select(Page).where(Page.site_id == site_id)).all()
        by_slug_id: dict[str, int] = {p.slug: p.id for p in db_rows}

    from app.core.config import get_settings as _get_settings
    settings = _get_settings()
    workers = max(1, min(settings.pipeline_image_max_concurrency, len(content.pages)))

    def _process_one(page) -> tuple[str, str | None]:
        page_db_id = by_slug_id.get(page.slug)
        if page_db_id is None:
            logger.warning("image_attach_skip_unknown_slug page=%s", page.slug)
            return (page.slug, None)

        keyword = page.hero_title or page.title or page.slug
        snippet = ""
        for blk in page.content_blocks:
            if blk.kind == "paragraph":
                md = (blk.props or {}).get("markdown") or ""
                if md.strip():
                    snippet = md[:1200].replace("\n", " ").strip()
                    break
        ctx = {
            "keyword": keyword,
            "snippet": snippet,
            "style": cfg.style,
            "title": page.title,
            "slug": page.slug,
            "brand": brand,
        }
        prompt = render_template(cfg.prompt_template, ctx)
        alt = render_template(cfg.alt_template, ctx) or keyword
        slug_base = _safe_base_name(f"{page.slug}-hero")

        try:
            raw = adapter.generate(prompt=prompt)
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
        except Exception as e:
            logger.warning("image_gen_failed page=%s err=%s", page.slug, e)
            return (page.slug, None)

        src_name = f"{slug_base}-src.png"
        try:
            img.save(dest_dir / src_name, format="PNG", optimize=True)
        except Exception as e:
            logger.warning("image_save_src_failed page=%s err=%s", page.slug, e)
            return (page.slug, None)
        src_rel = f"{y}/{m}/{src_name}"
        src_w, src_h = img.size[0], img.size[1]

        variants = _build_variants(img, widths)
        webp_rel_by_width: dict[int, str] = {}
        avif_rel_by_width: dict[int, str] = {}
        variant_sizes: dict[int, tuple[int, int]] = {}
        for w, vimg in sorted(variants.items()):
            vrgb = vimg.convert("RGB") if vimg.mode == "RGBA" else vimg

            webp_name = f"{slug_base}-{w}.webp"
            try:
                vrgb.save(dest_dir / webp_name, format="WEBP", quality=75, method=6)
            except Exception as e:
                logger.warning("image_save_webp_failed page=%s w=%s err=%s", page.slug, w, e)
                continue
            webp_rel_by_width[w] = f"{y}/{m}/{webp_name}"
            variant_sizes[w] = (vimg.size[0], vimg.size[1])

            avif_name = f"{slug_base}-{w}.avif"
            try:
                vrgb.save(dest_dir / avif_name, format="AVIF", quality=60)
            except Exception as e:
                logger.warning("avif_skipped page=%s w=%s err=%s", page.slug, w, e)
                continue
            avif_rel_by_width[w] = f"{y}/{m}/{avif_name}"

        if not webp_rel_by_width:
            return (page.slug, None)

        biggest = max(webp_rel_by_width)
        hero_url = public_uploads_url(runtime, webp_rel_by_width[biggest])

        with session_factory() as s:
            media_repo = MediaRepository(s)
            media_repo.create(
                site_id=site_id, page_id=page_db_id, storage_path=src_rel,
                mime_type="image/png", width=src_w, height=src_h,
                alt_text=alt, extra={"role": "hero_src"},
            )
            for w_key in sorted(webp_rel_by_width):
                ww, hh = variant_sizes[w_key]
                media_repo.create(
                    site_id=site_id, page_id=page_db_id,
                    storage_path=webp_rel_by_width[w_key],
                    mime_type="image/webp", width=ww, height=hh,
                    alt_text=alt, extra={"role": "hero_webp", "width": w_key},
                )
                if w_key in avif_rel_by_width:
                    media_repo.create(
                        site_id=site_id, page_id=page_db_id,
                        storage_path=avif_rel_by_width[w_key],
                        mime_type="image/avif", width=ww, height=hh,
                        alt_text=alt, extra={"role": "hero_avif", "width": w_key},
                    )
            db_page = s.get(Page, page_db_id)
            if db_page is not None:
                db_page.hero_image = hero_url
            s.commit()

        page.hero_image = hero_url

        logger.info(
            "image_attach_ok page=%s url=%s widths=%s avif_widths=%d",
            page.slug, hero_url, sorted(webp_rel_by_width),
            len(avif_rel_by_width),
        )
        return (page.slug, hero_url)

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="image-attach") as pool:
        futures = [pool.submit(_process_one, page) for page in content.pages]
        for fut in futures:
            try:
                fut.result()
            except Exception:
                logger.exception("image_attach_worker_failed")

    n_with_hero = sum(1 for p in content.pages if p.hero_image)
    logger.info(
        "image_attach_done_all site_id=%s workers=%d pages=%d with_hero=%d",
        site_id, workers, len(content.pages), n_with_hero,
    )
    return content


def build_picture_html(
    *,
    urls_by_width: dict[int, str],
    fallback_url: str,
    alt: str,
    width: int,
    height: int,
    sizes: str = "(max-width: 42rem) 100vw, 42rem",
) -> str:
    srcset_val = ", ".join(
        f"{html.escape(urls_by_width[w], quote=True)} {w}w" for w in sorted(urls_by_width)
    )
    return (
        "<picture>\n"
        f'  <source type="image/webp" srcset="{srcset_val}" sizes="{html.escape(sizes, quote=True)}" />\n'
        f'  <img src="{html.escape(fallback_url, quote=True)}" '
        f'alt="{html.escape(alt, quote=True)}" width="{width}" height="{height}" '
        'loading="lazy" decoding="async" />\n'
        "</picture>"
    )


def _persist_one_generated(
    img: Image.Image,
    *,
    file_slug: str,
    alt: str,
    y: str,
    m: str,
    dest_dir: Path,
    widths: list[int],
    runtime: SiteRuntime,
    page: Page,
    revision: PageRevision,
    media_repo: MediaRepository,
    idx: int,
) -> tuple[dict[int, str], dict[int, str], dict[int, str], list[int], str, dict[int, Image.Image]] | None:
    """PNG + webp + avif + media records. Возвращает (rel_webp, urls_webp, rel_avif, ids, rel_src, variants_im) или None."""
    tag = "hero" if idx == 0 else "inline"
    img = img.convert("RGBA")
    src_name = f"{file_slug}-src.png"
    img.save(dest_dir / src_name, format="PNG", optimize=True)
    rel_src = f"{y}/{m}/{src_name}"
    variants_im = _build_variants(img, widths)
    rel_keys: dict[int, str] = {}
    urls: dict[int, str] = {}
    rel_avif: dict[int, str] = {}
    ids: list[int] = [
        media_repo.create(
            site_id=runtime.site_id,
            page_id=page.id,
            storage_path=rel_src,
            mime_type="image/png",
            width=img.size[0],
            height=img.size[1],
            alt_text=alt,
            extra={"role": f"{tag}_src", "revision_id": revision.id, "i": idx},
        ).id,
    ]
    for rw, rim in sorted(variants_im.items()):
        rim_rgb = rim.convert("RGB") if rim.mode == "RGBA" else rim
        fname = f"{file_slug}-{rw}.webp"
        fp = dest_dir / fname
        rim_rgb.save(fp, format="WEBP", quality=75, method=6)
        rel = f"{y}/{m}/{fname}"
        rel_keys[rw] = rel
        urls[rw] = public_uploads_url(runtime, rel)
        ids.append(
            media_repo.create(
                site_id=runtime.site_id,
                page_id=page.id,
                storage_path=rel,
                mime_type="image/webp",
                width=rim.size[0],
                height=rim.size[1],
                alt_text=alt,
                extra={"role": f"{tag}_webp", "width": rw, "revision_id": revision.id, "i": idx},
            ).id,
        )
        try:
            avif_fname = f"{file_slug}-{rw}.avif"
            avif_fp = dest_dir / avif_fname
            rim_rgb.save(avif_fp, format="AVIF", quality=60)
            avif_rel = f"{y}/{m}/{avif_fname}"
            rel_avif[rw] = avif_rel
            ids.append(
                media_repo.create(
                    site_id=runtime.site_id,
                    page_id=page.id,
                    storage_path=avif_rel,
                    mime_type="image/avif",
                    width=rim.size[0],
                    height=rim.size[1],
                    alt_text=alt,
                    extra={"role": f"{tag}_avif", "width": rw, "revision_id": revision.id, "i": idx},
                ).id,
            )
        except Exception as e:
            logger.warning("avif_skipped width=%s err=%s", rw, e)
    if not urls:
        return None
    return rel_keys, urls, rel_avif, ids, rel_src, variants_im


def attach_hero_image(
    session: Session,
    runtime: SiteRuntime,
    page: Page,
    revision: PageRevision,
    body_markdown: str,
) -> dict[str, Any] | None:
    """Файлы + media; первая картинка — hero, остальные — markdown-блок."""
    cfg = runtime.file.pipeline.images
    if not cfg.enabled or cfg.max_images_per_page <= 0:
        return None

    try:
        root = _uploads_root(runtime)
    except AdapterConfigurationError as e:
        logger.warning("hero_image_skip_no_uploads: %s", e)
        return None

    n = min(int(cfg.max_images_per_page), 10)
    snippet = (body_markdown or "")[:1200].strip().replace("\n", " ")
    ctx = {
        "keyword": page.keyword_raw or "",
        "snippet": snippet,
        "style": cfg.style,
        "title": page.title or "",
        "slug": page.slug,
    }
    base_prompt = render_template(cfg.prompt_template, ctx)
    alt0 = render_template(cfg.alt_template, ctx)
    hint_pool = _variation_hints_pool(cfg)

    adapter = _make_provider(cfg)
    media_repo = MediaRepository(session)
    widths = sorted(set(cfg.srcset_widths))
    now = datetime.now(UTC).replace(tzinfo=None)
    y, m = f"{now.year:04d}", f"{now.month:02d}"
    slug_base = _safe_base_name(page.keyword_raw or page.slug)
    dest_dir = root / y / m
    dest_dir.mkdir(parents=True, exist_ok=True)

    all_ids: list[int] = []
    hero_rel: dict[int, str] | None = None
    hero_rel_avif: dict[int, str] = {}
    picture: str | None = None
    md_extra: list[str] = []

    for i in range(n):
        prompt = _compose_image_prompt(
            base=base_prompt,
            index=i,
            total=n,
            page_id=page.id,
            revision_id=revision.id,
            hints=hint_pool,
        )
        alt = alt0 if i == 0 else f"{alt0} — {i + 1}"
        file_slug = slug_base if i == 0 else f"{slug_base}-i{i + 1}"
        out = _persist_one_generated(
            Image.open(io.BytesIO(adapter.generate(prompt=prompt))),
            file_slug=file_slug,
            alt=alt,
            y=y,
            m=m,
            dest_dir=dest_dir,
            widths=widths,
            runtime=runtime,
            page=page,
            revision=revision,
            media_repo=media_repo,
            idx=i,
        )
        if out is None:
            logger.warning("hero_image_no_variants page_id=%s i=%s", page.id, i)
            return None
        rel_keys, urls, rel_avif_keys, ids, rel_src, vmap = out
        all_ids.extend(ids)
        if i == 0:
            hero_rel = rel_keys
            hero_rel_avif = rel_avif_keys
            mw = max(urls)
            picture = build_picture_html(
                urls_by_width=urls,
                fallback_url=public_uploads_url(runtime, rel_src),
                alt=alt0,
                width=vmap[mw].size[0],
                height=vmap[mw].size[1],
            )
        else:
            mw = max(rel_keys)
            src_u = public_uploads_url(runtime, rel_keys[mw])
            w_sz, h_sz = vmap[mw].size
            md_extra.append(
                '<figure class="article-figure">\n'
                f'  <img src="{html.escape(src_u, quote=True)}" alt="{html.escape(alt, quote=True)}" '
                f'width="{w_sz}" height="{h_sz}" loading="lazy" decoding="async" />\n'
                "</figure>"
            )

    if picture is None or hero_rel is None:
        return None
    hero_block: dict[str, Any] = {
        "picture_html": picture,
        "alt": alt0,
        "media_ids": all_ids,
        "provider": cfg.provider,
        "variants": hero_rel,
    }
    if hero_rel_avif:
        hero_block["variants_avif"] = hero_rel_avif
    patch: dict[str, Any] = {"hero_image": hero_block}
    if md_extra:
        patch["body_markdown"] = (body_markdown or "").rstrip() + (
            "\n\n---\n\n## Иллюстрации\n\n"
            + "\n\n".join(md_extra)
            + "\n"
        )
    return patch
