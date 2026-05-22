from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.errors import AdapterError
from app.adapters.protocols import TextHumanizer
from app.adapters.wordpress_rest import WordPressRestClient, WpPostResult
from app.core.site_runtime import SiteRuntime
from app.db.models.enums import PageStatus
from app.db.models.page import Page
from app.services.theme_manifest import PostTypeDef, post_type as get_post_type
from app.services.wp_content_for_type import TypedContentDraft, generate_for_post_type

logger = logging.getLogger(__name__)


_HUMANIZE_MIN_CHARS = 600


@dataclass(frozen=True)
class RestPublishResult:
    post_id: int
    post_type: str
    slug: str
    title: str
    link: str
    status: str
    page_id: int
    featured_image_id: int | None
    humanizer_chain: tuple[str, ...]
    term_id: int | None
    term_name: str | None


def _wp_rest(rt: SiteRuntime) -> WordPressRestClient:
    wp_cfg = rt.file.wordpress
    if not (wp_cfg.rest_base_url and wp_cfg.rest_auth_user and wp_cfg.rest_auth_password):
        raise ValueError(
            "site config missing wordpress.rest_base_url / rest_auth_user / rest_auth_password"
        )
    return WordPressRestClient(
        base_url=wp_cfg.rest_base_url,
        auth_user=wp_cfg.rest_auth_user,
        auth_password=wp_cfg.rest_auth_password,
    )


def _build_humanizer_chain(rt: SiteRuntime, post_type_slug: str) -> tuple[list[TextHumanizer], tuple[str, ...]]:
    chain_names = rt.file.pipeline.humanizer_chain_for(post_type_slug)
    resolved: list[TextHumanizer] = []
    for name in chain_names:
        n = name.strip().lower()
        if n == "smodin":
            from app.adapters.smodin import SmodinAdapter
            resolved.append(SmodinAdapter())
        elif n == "humanizer_ru":
            from app.adapters.humanizer_ru import HumanizerRuAdapter
            from app.core.config import get_settings
            from app.core.llm_provider_factory import make_text_llm
            settings = get_settings()
            llm = make_text_llm(settings)
            resolved.append(HumanizerRuAdapter(llm=llm, settings=settings))
        elif n in {"none", "skip", ""}:
            continue
        else:
            logger.warning("unknown_humanizer name=%s — skipping", n)
    return resolved, tuple(chain_names)


def _humanize_html_body(html: str, chain: list[TextHumanizer]) -> str:
    """Прогоняет HTML через humanize-цепочку. Сохраняет HTML-структуру —
    humanizer работает с raw text внутри тегов; здесь мы передаём целиком и
    надеемся что markdown→html → humanize → html всё ещё валидный.
    Простейший вариант: humanize всё body как plain text.
    """
    if not html or len(html) < _HUMANIZE_MIN_CHARS or not chain:
        return html
    body = html
    for humanizer in chain:
        try:
            body = humanizer.humanize(text=body)
        except AdapterError as e:
            logger.warning("humanize_step_failed: %s — продолжаем", e)
    return body


def _maybe_generate_featured_image(
    rt: SiteRuntime, draft: TypedContentDraft,
) -> tuple[int | None, str | None]:
    wp_cfg = rt.file.wordpress
    if not wp_cfg.images_enabled:
        return None, None

    from app.adapters.openai_image import OpenAIImageAdapter
    from app.core.config import get_settings

    settings = get_settings()
    image_prompt = (
        f"editorial illustration, clean professional photography style, "
        f"subject: {draft.title}. natural light, no text or watermarks, "
        f"no logos, no people facing camera straight on."
    )
    try:
        img_bytes = OpenAIImageAdapter(
            model=settings.openai_image_model,
            size=settings.openai_image_size,
            settings=settings,
        ).generate(prompt=image_prompt)
    except Exception as e:
        logger.warning("featured_image_gen_failed: %s", e)
        return None, None

    try:
        media = _wp_rest(rt).upload_media(
            content=img_bytes,
            filename=f"{draft.slug[:80]}.png",
            mime_type="image/png",
            alt_text=draft.title,
            title=draft.title,
        )
    except Exception as e:
        logger.warning("featured_image_upload_failed: %s", e)
        return None, None
    return media.attachment_id, media.source_url


def _resolve_term(
    rt: SiteRuntime, pt_def: PostTypeDef, term_slug: str | None, term_name: str | None,
) -> tuple[int | None, str | None, str | None]:
    """Resolve term для post_type'а: либо находит по slug, либо создаёт по name."""
    if not (pt_def.has_built_in_taxonomy and pt_def.default_taxonomy_rest_base):
        return None, None, None
    if not (term_slug or term_name):
        return None, None, pt_def.default_taxonomy_rest_base
    rest = _wp_rest(rt)
    tax_base = pt_def.default_taxonomy_rest_base
    try:
        if term_slug:
            term = rest.create_term(tax_base, name=term_name or term_slug, slug=term_slug)
        else:
            term = rest.create_term(tax_base, name=term_name)
        return int(term["id"]), str(term.get("name", "")), tax_base
    except Exception as e:
        logger.warning("term_resolve_failed taxonomy=%s slug=%s name=%s: %s",
                       tax_base, term_slug, term_name, e)
        return None, None, tax_base


def publish_rest(
    *,
    session: Session,
    rt: SiteRuntime,
    post_type_slug: str,
    topic: str,
    status: str = "publish",
    term_slug: str | None = None,
    term_name: str | None = None,
    brand: str | None = None,
    skip_image: bool = False,
) -> RestPublishResult:
    """End-to-end: generate → humanize → image → POST → mirror."""
    pt_def = get_post_type(post_type_slug)

    draft = generate_for_post_type(post_type_slug=post_type_slug, topic=topic, brand=brand)

    chain, chain_names = _build_humanizer_chain(rt, post_type_slug)
    if draft.content_html and len(draft.content_html) >= _HUMANIZE_MIN_CHARS:
        humanized = _humanize_html_body(draft.content_html, chain)
        draft = TypedContentDraft(
            title=draft.title, slug=draft.slug,
            meta_description=draft.meta_description,
            content_html=humanized, acf=draft.acf,
        )

    featured_id = None
    if not skip_image:
        featured_id, _ = _maybe_generate_featured_image(rt, draft)

    term_id, term_name_resolved, _ = _resolve_term(rt, pt_def, term_slug, term_name)

    rest = _wp_rest(rt)
    create_kwargs: dict[str, Any] = {
        "title": draft.title,
        "content": draft.content_html,
        "excerpt": draft.meta_description,
        "status": status,
        "slug": draft.slug,
        "author": rt.file.wordpress.default_post_author_id,
        "acf": draft.acf,
    }
    if featured_id:
        create_kwargs["featured_media"] = featured_id
    if term_id and pt_def.has_built_in_taxonomy and pt_def.default_taxonomy_rest_base:
        if pt_def.default_taxonomy_rest_base == "categories":
            create_kwargs["categories"] = [term_id]
        else:
            taxonomy_key = pt_def.default_taxonomy_rest_base.replace("-", "_")
            create_kwargs.setdefault("extra", {})[taxonomy_key] = [term_id]

    post: WpPostResult = rest.create_post(pt_def.rest_base, **create_kwargs)

    try:
        rest.update_post(pt_def.rest_base, post.post_id, fields={"meta": {
            "_yoast_wpseo_metadesc": draft.meta_description,
            "_yoast_wpseo_title": draft.title,
        }})
    except Exception as e:
        logger.warning("yoast_meta_set_failed post_id=%s: %s", post.post_id, e)

    page = Page(
        site_id=rt.site_id,
        slug=draft.slug,
        title=draft.title,
        status=PageStatus.PUBLISHED,
        page_type=post_type_slug,
        keyword_raw=topic[:1024],
        wp_post_id=post.post_id,
        seo_overrides={
            "meta_description": draft.meta_description,
            "post_type": post_type_slug,
            "rest_base": pt_def.rest_base,
            "term_id": term_id,
            "term_name": term_name_resolved,
            "link": post.link,
        },
    )
    session.add(page)
    session.flush()
    page_id = int(page.id)
    session.commit()

    logger.info(
        "wp_rest_published post_id=%s page_id=%s type=%s status=%s term=%s",
        post.post_id, page_id, post.post_type, post.status, term_name_resolved,
    )
    return RestPublishResult(
        post_id=post.post_id,
        post_type=post.post_type,
        slug=post.slug,
        title=draft.title,
        link=post.link,
        status=post.status,
        page_id=page_id,
        featured_image_id=featured_id,
        humanizer_chain=chain_names,
        term_id=term_id,
        term_name=term_name_resolved,
    )
