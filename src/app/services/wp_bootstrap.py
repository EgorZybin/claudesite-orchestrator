from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.adapters.wordpress_rest import WordPressRestClient
from app.core.site_runtime import SiteRuntime
from app.services.wp_bootstrap_plan import (
    BlogPostPlan, CasePlan, CategoryPlan, FaqPlan, PagePlan, ServicePlan,
    SitePlan, TeamMemberPlan, plan_site,
)
from app.services.wp_publish_rest import publish_rest, RestPublishResult

logger = logging.getLogger(__name__)


@dataclass
class BootstrapProgress:
    plan: SitePlan
    site_options_set: bool = False
    blog_categories: dict[str, int] = None
    service_categories: dict[str, int] = None
    pages: dict[str, RestPublishResult] = None
    services: list[RestPublishResult] = None
    cases: list[RestPublishResult] = None
    team: list[RestPublishResult] = None
    faqs: list[RestPublishResult] = None
    blog_posts: list[RestPublishResult] = None
    errors: list[str] = None

    def __post_init__(self):
        for f in ("blog_categories", "service_categories"):
            if getattr(self, f) is None:
                setattr(self, f, {})
        for f in ("services", "cases", "team", "faqs", "blog_posts", "errors"):
            if getattr(self, f) is None:
                setattr(self, f, [])
        if self.pages is None:
            self.pages = {}


def _rest(rt: SiteRuntime) -> WordPressRestClient:
    wp_cfg = rt.file.wordpress
    return WordPressRestClient(
        base_url=wp_cfg.rest_base_url, auth_user=wp_cfg.rest_auth_user,
        auth_password=wp_cfg.rest_auth_password,
    )


def _set_site_options(rt: SiteRuntime, plan: SitePlan) -> None:
    """Set ключевые wp_options через WP REST settings endpoint."""
    rest = _rest(rt)
    payload = {
        "title": plan.brand,
        "description": plan.tagline,
        "timezone": plan.timezone,
        "language": plan.language,
        "posts_per_page": 9,
    }
    import httpx
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            f"{rt.file.wordpress.rest_base_url.rstrip('/')}/wp/v2/settings",
            json=payload, auth=(rt.file.wordpress.rest_auth_user, rt.file.wordpress.rest_auth_password),
        )
        if r.status_code >= 400:
            logger.warning("set_site_options_failed: %s %s", r.status_code, r.text[:200])
        else:
            logger.info("site_options_set brand=%s lang=%s", plan.brand, plan.language)


def _create_categories(
    rt: SiteRuntime, cats: list[CategoryPlan], tax_rest_base: str,
) -> dict[str, int]:
    """Создать категории через REST. Возвращает slug → term_id."""
    rest = _rest(rt)
    out: dict[str, int] = {}
    for c in cats:
        try:
            term = rest.create_term(
                tax_rest_base, name=c.name, slug=c.slug, description=c.description,
            )
            out[c.slug] = int(term["id"])
            logger.info("category_created tax=%s slug=%s id=%s", tax_rest_base, c.slug, term["id"])
        except Exception as e:
            logger.warning("category_create_failed slug=%s: %s", c.slug, e)
    return out


def _set_front_page(rt: SiteRuntime, *, home_post_id: int, posts_page_id: int | None) -> None:
    rest = _rest(rt)
    import httpx
    payload: dict = {"show_on_front": "page", "page_on_front": int(home_post_id)}
    if posts_page_id:
        payload["page_for_posts"] = int(posts_page_id)
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            f"{rt.file.wordpress.rest_base_url.rstrip('/')}/wp/v2/settings",
            json=payload, auth=(rt.file.wordpress.rest_auth_user, rt.file.wordpress.rest_auth_password),
        )
        if r.status_code >= 400:
            logger.warning("set_front_page_failed: %s %s", r.status_code, r.text[:200])


def bootstrap_site(
    *, session: Session, rt: SiteRuntime, instruction: str,
    skip_blog_posts: bool = False, skip_images: bool = False,
) -> BootstrapProgress:
    """Полный bootstrap: LLM-plan → создание всех артефактов через REST."""
    plan = plan_site(instruction, language="ru")
    progress = BootstrapProgress(plan=plan)

    try:
        _set_site_options(rt, plan)
        progress.site_options_set = True
    except Exception as e:
        progress.errors.append(f"site_options: {e}")

    progress.blog_categories = _create_categories(rt, plan.blog_categories, "categories")
    progress.service_categories = _create_categories(rt, plan.service_categories, "service-categories")

    brand = plan.brand

    home_post_id: int | None = None
    posts_page_id: int | None = None
    for p in plan.pages:
        try:
            res = publish_rest(
                session=session, rt=rt, post_type_slug="page",
                topic=f"{p.title}: {p.instruction}",
                status="publish", brand=brand, skip_image=skip_images,
            )
            progress.pages[p.role] = res
            if p.role == "home":
                home_post_id = res.post_id
        except Exception as e:
            logger.exception("page_failed role=%s", p.role)
            progress.errors.append(f"page[{p.role}]: {e}")

    if home_post_id:
        _set_front_page(rt, home_post_id=home_post_id, posts_page_id=posts_page_id)

    for s in plan.services:
        try:
            res = publish_rest(
                session=session, rt=rt, post_type_slug="service",
                topic=s.topic, status="publish", brand=brand, skip_image=skip_images,
            )
            progress.services.append(res)
        except Exception as e:
            logger.exception("service_failed topic=%s", s.topic[:60])
            progress.errors.append(f"service[{s.topic[:40]}]: {e}")

    for c in plan.cases:
        try:
            res = publish_rest(
                session=session, rt=rt, post_type_slug="case_study",
                topic=f"{c.topic} (индустрия: {c.industry})",
                status="publish", brand=brand, skip_image=skip_images,
            )
            progress.cases.append(res)
        except Exception as e:
            logger.exception("case_failed")
            progress.errors.append(f"case[{c.topic[:40]}]: {e}")

    for tm in plan.team:
        try:
            res = publish_rest(
                session=session, rt=rt, post_type_slug="team_member",
                topic=tm.topic, status="publish", brand=brand, skip_image=skip_images,
            )
            progress.team.append(res)
        except Exception as e:
            logger.exception("team_failed")
            progress.errors.append(f"team[{tm.topic[:40]}]: {e}")

    for f in plan.faqs:
        try:
            res = publish_rest(
                session=session, rt=rt, post_type_slug="faq",
                topic=f.question, status="publish", brand=brand, skip_image=True,
            )
            try:
                _rest(rt).update_post("faqs", res.post_id, fields={"acf": {"show_on_page": f.show_on}})
            except Exception as e2:
                logger.warning("faq_show_on_update_failed: %s", e2)
            progress.faqs.append(res)
        except Exception as e:
            logger.exception("faq_failed")
            progress.errors.append(f"faq[{f.question[:40]}]: {e}")

    if not skip_blog_posts:
        for bp in plan.blog_posts:
            try:
                res = publish_rest(
                    session=session, rt=rt, post_type_slug="post",
                    topic=bp.topic,
                    status="publish", brand=brand,
                    term_slug=bp.category_slug,
                    skip_image=skip_images,
                )
                progress.blog_posts.append(res)
            except Exception as e:
                logger.exception("blog_post_failed")
                progress.errors.append(f"post[{bp.topic[:40]}]: {e}")

    logger.info(
        "bootstrap_done brand=%s pages=%d services=%d cases=%d team=%d faqs=%d posts=%d errors=%d",
        brand, len(progress.pages), len(progress.services), len(progress.cases),
        len(progress.team), len(progress.faqs), len(progress.blog_posts), len(progress.errors),
    )
    return progress
