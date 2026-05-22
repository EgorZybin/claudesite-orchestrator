from __future__ import annotations

import logging

from app.adapters.wordpress_db import WordPressDbAdapter
from app.core.site_config_schema import (
    WpAcfField, WpAcfGroup, WpCategoryInfo, WpIntrospectionSpec, WpPageInfo,
    WpPostTypeInfo, WpSamplePost, WpTaxonomyInfo,
)

logger = logging.getLogger(__name__)


def collect_introspection(wp: WordPressDbAdapter) -> WpIntrospectionSpec:
    """Сводный snapshot структуры сайта (Pydantic-валидированный)."""
    post_types_raw = wp.list_post_types()
    post_types = [WpPostTypeInfo(name=n, count=c) for n, c in post_types_raw]

    SYSTEM = {"revision", "nav_menu_item", "acf-field", "acf-field-group", "attachment",
              "oembed_cache", "user_request", "wp_block", "wp_navigation"}
    templates_per_pt: dict[str, list[tuple[str, int]]] = {}
    for pt_name, _ in post_types_raw:
        if pt_name in SYSTEM:
            continue
        tpls = wp.list_templates_for_post_type(pt_name, limit=10)
        if tpls:
            templates_per_pt[pt_name] = tpls

    cats = wp.list_categories(limit=50)
    pages = wp.list_top_pages(limit=30)

    acf_groups_raw = wp.list_acf_field_groups()
    acf_groups = [
        WpAcfGroup(
            group_id=g["group_id"],
            group_title=g["group_title"],
            fields=[
                WpAcfField(
                    field_id=f["field_id"],
                    field_name=f["field_name"],
                    label=f["label"],
                    type=f["type"],
                )
                for f in g["fields"]
            ],
        )
        for g in acf_groups_raw
    ]

    samples: list[WpSamplePost] = []
    user_facing = [n for n, _ in post_types_raw if n not in SYSTEM][:4]
    for pt_name in user_facing:
        sp_raw = wp.sample_postmeta_for_recent(pt_name, limit=2)
        for sp in sp_raw:
            samples.append(WpSamplePost(
                post_id=sp["post_id"], title=sp["title"], slug=sp["slug"],
                post_type=pt_name, meta=sp["meta"],
            ))

    intro = WpIntrospectionSpec(
        siteurl=wp.get_option("siteurl"),
        blogname=wp.get_option("blogname"),
        theme=wp.get_option("template"),
        stylesheet=wp.get_option("stylesheet"),
        seo_plugin=wp.detect_seo_plugin(),
        post_types=post_types,
        taxonomies=[WpTaxonomyInfo(name=n, count=c) for n, c in wp.list_taxonomies()],
        categories=[WpCategoryInfo(slug=c.slug, name=c.name, count=c.count) for c in cats],
        top_pages=[WpPageInfo(slug=p.slug, title=p.title) for p in pages],
        templates_per_post_type=templates_per_pt,
        acf_field_groups=acf_groups,
        sample_posts=samples,
    )
    logger.info(
        "wp_introspect_collected siteurl=%s theme=%s seo=%s post_types=%d acf_groups=%d samples=%d",
        intro.siteurl, intro.theme, intro.seo_plugin, len(intro.post_types),
        len(intro.acf_field_groups), len(intro.sample_posts),
    )
    return intro
