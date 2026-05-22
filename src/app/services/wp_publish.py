from __future__ import annotations

import logging
from dataclasses import dataclass

import markdown as md
from sqlalchemy.orm import Session

from app.adapters.errors import AdapterError
from app.adapters.protocols import TextHumanizer
from app.adapters.wordpress_db import WordPressDbAdapter
from app.adapters.wordpress_rest import WordPressRestClient
from app.core.site_runtime import SiteRuntime
from app.db.models.enums import PageStatus
from app.db.models.page import Page
from app.services.wp_content import WpContentDraft, generate_content_draft
from app.services.wp_router import WpAction, route_instruction

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WpPublishResult:
    wp_post_id: int
    page_id: int
    slug: str
    title: str
    post_type: str
    post_status: str
    chars_body_md: int
    humanizer_chain: tuple[str, ...]
    taxonomy: str | None
    term_slug: str | None
    template: str | None
    featured_image_id: int | None = None
    featured_image_url: str | None = None


def _build_humanizer_chain(rt: SiteRuntime, post_type: str) -> tuple[list[TextHumanizer], tuple[str, ...]]:
    chain_names = rt.file.pipeline.humanizer_chain_for(post_type)
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
            logger.warning("wp_publish_unknown_humanizer name=%s — skipping", n)
    return resolved, tuple(chain_names)


def _markdown_to_html(text: str) -> str:
    return md.markdown(text, extensions=["extra", "sane_lists"])


def _maybe_generate_featured_image(
    rt: SiteRuntime, wp_post_id: int, draft: WpContentDraft,
) -> tuple[int | None, str | None]:
    wp_cfg = rt.file.wordpress
    if not wp_cfg.images_enabled:
        return None, None
    if not (wp_cfg.rest_base_url and wp_cfg.rest_auth_user and wp_cfg.rest_auth_password):
        logger.warning("wp_publish_images_enabled но rest_auth не сконфигурирован — skipping")
        return None, None

    from app.adapters.openai_image import OpenAIImageAdapter
    from app.core.config import get_settings

    settings = get_settings()
    image_prompt = (
        f"editorial illustration, clean professional photography style, "
        f"subject: {draft.title}. natural light, no text or watermarks, "
        f"no logos, no people facing camera straight on."
    )
    img_adapter = OpenAIImageAdapter(
        model=settings.openai_image_model,
        size=settings.openai_image_size,
        settings=settings,
    )
    try:
        img_bytes = img_adapter.generate(prompt=image_prompt)
    except Exception as e:
        logger.warning("wp_publish_image_gen_failed: %s — продолжаем без картинки", e)
        return None, None

    rest = WordPressRestClient(
        base_url=wp_cfg.rest_base_url,
        auth_user=wp_cfg.rest_auth_user,
        auth_password=wp_cfg.rest_auth_password,
    )
    filename = f"{draft.slug[:80]}.png"
    try:
        result = rest.upload_media(
            content=img_bytes, filename=filename, mime_type="image/png",
            alt_text=draft.title, title=draft.title,
        )
    except Exception as e:
        logger.warning("wp_publish_image_upload_failed: %s — продолжаем без картинки", e)
        return None, None
    return result.attachment_id, result.source_url


def _render_extra_postmeta(template: dict[str, str], draft: WpContentDraft, action: WpAction) -> dict[str, str]:
    placeholders = {
        "title": draft.title,
        "meta_description": draft.meta_description,
        "slug": draft.slug,
        "post_type": action.post_type,
        "taxonomy": action.taxonomy or "",
        "term_slug": action.term_slug or "",
    }
    rendered: dict[str, str] = {}
    for k, v in (template or {}).items():
        out = v
        for ph, repl in placeholders.items():
            out = out.replace("{{" + ph + "}}", repl)
        rendered[k] = out
    return rendered


def publish_action(
    *,
    session: Session,
    rt: SiteRuntime,
    action: WpAction,
) -> WpPublishResult:
    """Выполнить routed action: generate → humanize → INSERT WP → mirror."""
    if rt.file.wordpress is None or not rt.file.wordpress.database_url:
        raise ValueError("site is not in wp-mode or wordpress.database_url is missing")

    wp = WordPressDbAdapter(
        database_url=rt.file.wordpress.database_url,
        table_prefix=rt.file.wordpress.table_prefix,
    )

    draft = generate_content_draft(action.topic, post_type=action.post_type, language="ru")

    chain, chain_names = _build_humanizer_chain(rt, action.post_type)
    body = draft.body_markdown
    for step_idx, humanizer in enumerate(chain):
        try:
            body = humanizer.humanize(text=body)
        except AdapterError:
            logger.exception(
                "wp_publish_humanizer_failed step=%d name=%s",
                step_idx, chain_names[step_idx] if step_idx < len(chain_names) else "?",
            )
            raise

    content_html = _markdown_to_html(body)

    tt_ids: list[int] = []
    if action.taxonomy and action.term_slug:
        tt_id = wp.lookup_term_taxonomy(action.taxonomy, action.term_slug)
        if tt_id is None:
            logger.warning(
                "wp_publish_term_not_found taxonomy=%s slug=%s — публикуем без assignment",
                action.taxonomy, action.term_slug,
            )
        else:
            tt_ids.append(tt_id)

    wp_post_id = wp.insert_post(
        title=draft.title,
        slug=draft.slug,
        content_html=content_html,
        excerpt=draft.meta_description,
        post_status=action.post_status,
        post_type=action.post_type,
        author_id=rt.file.wordpress.default_post_author_id,
    )

    wp.upsert_postmeta(wp_post_id, "_yoast_wpseo_metadesc", draft.meta_description)
    wp.upsert_postmeta(wp_post_id, "_yoast_wpseo_title", draft.title)
    if action.template:
        wp.upsert_postmeta(wp_post_id, "_wp_page_template", action.template)

    rendered_meta = _render_extra_postmeta(action.extra_postmeta, draft, action)
    for k, v in rendered_meta.items():
        wp.upsert_postmeta(wp_post_id, k, v)

    if tt_ids:
        wp.assign_categories(wp_post_id, tt_ids)

    img_id, img_url = _maybe_generate_featured_image(rt, wp_post_id, draft)
    if img_id is not None:
        wp.upsert_postmeta(wp_post_id, "_thumbnail_id", str(img_id))
        logger.info("wp_publish_thumbnail_set wp_post_id=%s att_id=%s", wp_post_id, img_id)

    page = Page(
        site_id=rt.site_id,
        slug=draft.slug,
        title=draft.title,
        status=PageStatus.PUBLISHED,
        page_type=action.post_type,
        keyword_raw=action.topic[:1024],
        wp_post_id=wp_post_id,
        seo_overrides={
            "meta_description": draft.meta_description,
            "taxonomy": action.taxonomy,
            "term_slug": action.term_slug,
            "template": action.template,
            "router_rationale": action.rationale,
        },
    )
    session.add(page)
    session.flush()
    page_id = int(page.id)
    session.commit()

    logger.info(
        "wp_published page_id=%s wp_post_id=%s post_type=%s tax=%s/%s template=%s status=%s",
        page_id, wp_post_id, action.post_type, action.taxonomy, action.term_slug,
        action.template, action.post_status,
    )
    return WpPublishResult(
        wp_post_id=wp_post_id,
        page_id=page_id,
        slug=draft.slug,
        title=draft.title,
        post_type=action.post_type,
        post_status=action.post_status,
        chars_body_md=len(body),
        humanizer_chain=chain_names,
        taxonomy=action.taxonomy,
        term_slug=action.term_slug,
        template=action.template,
        featured_image_id=img_id,
        featured_image_url=img_url,
    )


def publish_from_instruction(
    *,
    session: Session,
    rt: SiteRuntime,
    instruction: str,
) -> WpPublishResult:
    """Natural-language entrypoint: router решает action → publish."""
    if rt.file.wordpress is None or rt.file.wordpress.introspection is None:
        raise ValueError(
            "site has no cached introspection — запусти `claudesite site init-wp` "
            "или `refresh-wp` чтобы заполнить wordpress.introspection в config.yaml"
        )
    action = route_instruction(instruction, rt.file.wordpress.introspection)
    return publish_action(session=session, rt=rt, action=action)
