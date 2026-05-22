from __future__ import annotations

import json

import typer

from app.core.exceptions import OrchestratorError
from app.core.logging import configure_logging
from app.core.site_runtime import SiteRuntime, SiteRuntimeResolver
from app.db.models.enums import SiteMode
from app.db.repos.sites import SiteRepository
from app.db.session import get_session_factory

site_app = typer.Typer(help="Per-site config.yaml + database")


def _fail(exc: OrchestratorError) -> None:
    typer.secho(str(exc), err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1) from exc


def _resolve(slug: str) -> SiteRuntime:
    resolver = SiteRuntimeResolver()
    factory = get_session_factory()
    with factory() as session:
        try:
            return resolver.resolve(session, slug)
        except OrchestratorError as e:
            _fail(e)


@site_app.command("validate")
def site_validate(
    slug: str = typer.Option(..., "--site", "-s", help="Site slug"),
) -> None:
    """Загрузить YAML и сверить с записью в БД; при ошибке выйти с ненулевым кодом."""
    configure_logging()
    rt = _resolve(slug)

    typer.echo(
        json.dumps(
            {
                "ok": True,
                "slug": rt.slug,
                "site_id": rt.site_id,
                "effective_mode": rt.effective_mode.value,
                "db_mode": rt.db_mode.value,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


@site_app.command("show")
def site_show(
    slug: str = typer.Option(..., "--site", "-s", help="Site slug"),
) -> None:
    """Вывести провалидированный config.yaml как JSON (для отладки)."""
    configure_logging()
    rt = _resolve(slug)

    typer.echo(
        json.dumps(
            rt.file.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
        )
    )


@site_app.command("config-path")
def site_config_path(
    slug: str = typer.Option(..., "--site", "-s", help="Site slug"),
) -> None:
    """Вывести абсолютный путь к config.yaml для этого slug."""
    path = SiteRuntimeResolver().config_path(slug)
    typer.echo(str(path))


_BOOTSTRAP_CONFIG_TEMPLATE_CUSTOM = """mode: custom
display_name: {display_name_quoted}

custom:
  public_base_url: {public_base_url}
  uploads_base_path: {uploads_base_path}
  default_template: article

theme:
  accent: "#0f172a"
  display_font: Manrope
  body_font: Inter

seo:
  brand: {display_name_quoted}
  global:
    title_template: "{{{{keyword}}}} | {{{{brand}}}}"
    canonical_template: "{{{{page_url}}}}"
    schema_type: Article

pipeline:
  turgenev_pass_score_max: 6
  max_iterations: 4
  smodin_each_iteration: false
  images:
    enabled: false
    provider: openai
    openai_model: gpt-image-1
    openai_size: "1024x1024"
    max_images_per_page: 1
    style: clean editorial photography, natural light, no text or watermarks
"""

_BOOTSTRAP_CONFIG_TEMPLATE_WORDPRESS = """mode: wordpress
display_name: {display_name_quoted}

wordpress:
  database_url: mysql+pymysql://wpuser:wppass@wp-mysql:3306/wordpress
  table_prefix: wp_
  public_site_url: {public_site_url}
  default_post_author_id: 1

seo:
  brand: {display_name_quoted}

pipeline:
  max_iterations: 4
  humanizers_per_pass:
    blog_post: [humanizer_ru, smodin]
    default: [smodin]
  images:
    enabled: false
"""

_INIT_WP_TEMPLATE = """mode: wordpress
display_name: "{display_name}"

wordpress:
  database_url: {database_url}
  table_prefix: {table_prefix}
  public_site_url: {public_site_url}
  default_post_author_id: 1
  introspection:
{introspection_yaml}

seo:
  brand: "{display_name}"

pipeline:
  max_iterations: 3
  humanizers_per_pass:
    blog_post: [humanizer_ru, smodin]
    default: [smodin]
  images:
    enabled: false
"""


def _introspection_to_yaml_block(intro, indent: int = 4) -> str:
    import yaml as _yaml

    raw = intro.model_dump()
    dumped = _yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, default_flow_style=False)
    pad = " " * indent
    return "\n".join(pad + line for line in dumped.rstrip().splitlines())


@site_app.command("bootstrap")
def site_bootstrap(
    slug: str = typer.Option(..., "--slug", "-s", help="Site slug (a-z 0-9 -)"),
    display_name: str = typer.Option(..., "--display-name", "-n", help="Human-readable site name"),
    mode: str = typer.Option("custom", "--mode", "-m", help="custom | wordpress"),
    domain: str | None = typer.Option(
        None,
        "--domain",
        "-d",
        help="Производственный host (например, food-demo.lead-hunter.ru). При указании "
             "public_base_url по умолчанию ставится в https://<domain>. Регистрация "
             "Apache vhost + Let's Encrypt — отдельным шагом через scripts/provision-domain.sh.",
    ),
    public_base_url: str | None = typer.Option(
        None,
        "--public-base-url",
        help="External base URL for SEO (canonical etc). Если не указан и есть --domain → "
             "https://<domain>. Без --domain становится обязательным.",
    ),
    uploads_root: str = typer.Option(
        "/var/www",
        "--uploads-root",
        help="Parent directory under which <root>/<slug>/uploads will be created",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing config.yaml if present"),
) -> None:
    """Создать новый сайт за один шаг: каталог sites/<slug>, uploads dir, DB row.

    После выполнения сайт виден из API; uploads сервятся через FastAPI route
    /uploads/<slug>/<path>. Apache config трогать не нужно.

    Для прод-режима (один slug = свой домен) укажи --domain; конфиг будет
    подготовлен под https://<domain>, а в "next" будет напечатана команда
    scripts/provision-domain.sh для регистрации Apache vhost + TLS.
    """
    import re
    from pathlib import Path

    from app.core.config import get_settings

    configure_logging()

    if not re.match(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$", slug):
        typer.secho("slug must be lowercase a-z, 0-9, '-' (3-64 chars)", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)
    mode_norm = mode.strip().lower()
    if mode_norm not in {"custom", "wordpress"}:
        typer.secho("mode must be 'custom' or 'wordpress'", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)
    mode_enum = SiteMode.CUSTOM if mode_norm == "custom" else SiteMode.WORDPRESS

    if domain is not None:
        domain = domain.strip().lower()
        if not re.match(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}$", domain):
            typer.secho(f"invalid --domain format: {domain}", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=2)

    if public_base_url is None:
        if domain:
            public_base_url = f"https://{domain}"
        else:
            typer.secho(
                "Either --domain or --public-base-url is required.\n"
                "  --domain DOMAIN              prod site with its own host (https://<domain>)\n"
                "  --public-base-url URL        explicit external base URL otherwise",
                err=True, fg=typer.colors.RED,
            )
            raise typer.Exit(code=2)

    settings = get_settings()
    sites_root = Path(settings.sites_config_root or "sites").expanduser().resolve()
    site_dir = sites_root / slug
    config_path = site_dir / "config.yaml"
    uploads_dir = (Path(uploads_root).expanduser() / slug / "uploads").resolve()

    if config_path.exists() and not force:
        typer.secho(f"config already exists: {config_path} (use --force to overwrite)", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    site_dir.mkdir(parents=True, exist_ok=True)
    if mode_norm == "custom":
        uploads_dir.mkdir(parents=True, exist_ok=True)
        config_text = _BOOTSTRAP_CONFIG_TEMPLATE_CUSTOM.format(
            display_name_quoted=display_name,
            public_base_url=public_base_url.rstrip("/"),
            uploads_base_path=str(uploads_dir),
        )
    else:
        config_text = _BOOTSTRAP_CONFIG_TEMPLATE_WORDPRESS.format(
            display_name_quoted=display_name,
            public_site_url=public_base_url.rstrip("/"),
        )
    config_path.write_text(config_text, encoding="utf-8")

    factory = get_session_factory()
    session = factory()
    db_action = "skipped (already exists)"
    try:
        with session.begin():
            repo = SiteRepository(session)
            if repo.get_by_slug(slug) is None:
                repo.create(slug=slug, display_name=display_name, mode=mode_enum)
                db_action = "created"
    finally:
        session.close()

    try:
        SiteRuntimeResolver().resolve(get_session_factory()(), slug)
        validate_status = "ok"
    except OrchestratorError as exc:
        validate_status = f"failed: {exc}"

    next_steps: list[str] = []
    if mode_norm == "wordpress":
        next_steps.append(f"Edit {config_path} — fill in wordpress.database_url + table_prefix.")
        next_steps.append(f"Connect WP DB: claudesite site init-wp --slug {slug} --display-name {display_name!r} --wp-db-url ...")
        next_steps.append(f"Test: claudesite site validate --site {slug}")
        next_steps.append(
            f"Publish: claudesite site do --site {slug} --instruction 'добавь в блог статью про ...'"
        )
    else:
        generate_hint = (
            f"Generate site via "
            f'POST /admin/sites/{slug}/generate  body: {{"user_prompt":"...","target_pages":6}}'
        )
        if domain:
            next_steps.append(f"Point DNS A-record: {domain}  ->  this server IP")
            next_steps.append(
                f"Provision Apache vhost + Let's Encrypt cert + register site_domain:"
                f"  sudo ./scripts/provision-domain.sh {domain} {slug}"
            )
            next_steps.append(generate_hint)
            next_steps.append(f"View when ready at https://{domain}/  (and /<page-slug>)")
        else:
            next_steps.append(generate_hint)
            next_steps.append(
                f"View when ready at {public_base_url.rstrip('/')}/public/{slug}/"
                f"  (and /public/{slug}/<page-slug>)"
            )

    typer.echo(
        json.dumps(
            {
                "slug": slug,
                "display_name": display_name,
                "mode": mode_norm,
                "config_path": str(config_path),
                "uploads_dir": str(uploads_dir) if mode_norm == "custom" else None,
                "db_row": db_action,
                "validate": validate_status,
                "public_base_url": public_base_url.rstrip("/"),
                "domain": domain,
                "next": next_steps,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


@site_app.command("analyze-url")
def site_analyze_url(
    url: str = typer.Argument(..., help="URL сайта-источника (http(s):// добавится)"),
    inner_pages: int = typer.Option(
        2,
        "--inner-pages",
        "-i",
        min=0,
        max=5,
        help="Сколько nav-ссылок дочитать после главной (0..5). Default 2.",
    ),
    no_screenshot: bool = typer.Option(
        False,
        "--no-screenshot",
        help="Отключить vision-pass (Playwright + chat/completions с image). "
             "Brief получится менее точным по дизайну, но быстрее и дешевле. "
             "Использовать когда headless chromium недоступен или сайт его блокирует.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Выдать JSON с метаданными вместо чистого prompt'а.",
    ),
) -> None:
    """Превратить ссылку на сайт в подробный user_prompt для генерации.

    Фетчит главную (опц. + 2 внутренние страницы), извлекает структуру/тон/
    nav через httpx + bs4. По умолчанию ещё делает screenshot главной через
    Playwright Chromium и отправляет картинку + текст в vision-LLM —
    получается brief, в котором палитра/шрифты/layout сняты с реального
    дизайна, а не из догадок. Полученный prompt можно как есть подставить
    в body.user_prompt для POST /admin/sites/<slug>/generate.
    """
    import httpx as _httpx

    from app.adapters.errors import AdapterError
    from app.services.url_analyze import analyze_url

    configure_logging()

    try:
        result = analyze_url(
            url,
            inner_pages=inner_pages,
            skip_screenshot=no_screenshot,
        )
    except ValueError as e:
        typer.secho(f"invalid input: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2) from e
    except _httpx.HTTPError as e:
        typer.secho(f"fetch failed: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e
    except AdapterError as e:
        typer.secho(f"LLM error: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e

    if as_json:
        typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        typer.echo(result["prompt"])


@site_app.command("init-wp")
def site_init_wp(
    slug: str = typer.Option(..., "--slug", "-s", help="Site slug (a-z 0-9 -)"),
    display_name: str = typer.Option(..., "--display-name", "-n", help="Человеческое имя"),
    wp_db_url: str = typer.Option(
        ...,
        "--wp-db-url",
        help="SQLAlchemy URL: mysql+pymysql://user:pass@host:3306/db",
    ),
    table_prefix: str = typer.Option("wp_", "--table-prefix", help="Префикс таблиц WP"),
    force: bool = typer.Option(False, "--force", help="Перезаписать существующий config.yaml"),
) -> None:
    """Подключиться к WP, собрать introspection, записать config.yaml + создать site row."""
    import re
    from pathlib import Path

    from app.adapters.wordpress_db import WordPressDbAdapter
    from app.core.config import get_settings
    from app.services.wp_introspect import collect_introspection

    configure_logging()

    if not re.match(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$", slug):
        typer.secho("slug must be lowercase a-z 0-9 '-' (3-64 chars)", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    settings = get_settings()
    sites_root = Path(settings.sites_config_root or "sites").expanduser().resolve()
    site_dir = sites_root / slug
    config_path = site_dir / "config.yaml"
    if config_path.exists() and not force:
        typer.secho(f"config exists: {config_path} (use --force)", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    typer.echo("connecting to WP DB ...")
    wp = WordPressDbAdapter(database_url=wp_db_url, table_prefix=table_prefix)
    try:
        wp.ping()
    except Exception as e:
        typer.secho(f"WP DB connect failed: {type(e).__name__}: {e}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1) from e
    typer.echo("connected ✓  introspecting ...")

    intro = collect_introspection(wp)
    yaml_block = _introspection_to_yaml_block(intro, indent=4)
    config_text = _INIT_WP_TEMPLATE.format(
        display_name=display_name,
        database_url=wp_db_url,
        table_prefix=table_prefix,
        public_site_url=intro.siteurl or "",
        introspection_yaml=yaml_block,
    )

    site_dir.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_text, encoding="utf-8")
    typer.echo(f"wrote {config_path}")

    factory = get_session_factory()
    session = factory()
    db_action = "skipped (exists)"
    try:
        with session.begin():
            repo = SiteRepository(session)
            if repo.get_by_slug(slug) is None:
                repo.create(slug=slug, display_name=display_name, mode=SiteMode.WORDPRESS)
                db_action = "created"
    finally:
        session.close()

    try:
        SiteRuntimeResolver().resolve(get_session_factory()(), slug)
        validate = "ok"
    except OrchestratorError as exc:
        validate = f"failed: {exc}"

    typer.echo(
        json.dumps(
            {
                "slug": slug,
                "config_path": str(config_path),
                "db_row": db_action,
                "validate": validate,
                "detected": {
                    "siteurl": intro.siteurl,
                    "theme": intro.theme,
                    "seo_plugin": intro.seo_plugin,
                    "post_types": [pt.name for pt in intro.post_types[:6]],
                    "user_facing_templates": {
                        pt: [t for t, _ in tpls]
                        for pt, tpls in intro.templates_per_post_type.items()
                    },
                    "categories": len(intro.categories),
                    "acf_groups": len(intro.acf_field_groups),
                },
                "next": [
                    f"Test natural: claudesite site do --site {slug} --instruction 'добавь в блог статью про тест'",
                    f"Test explicit: claudesite site publish --site {slug} --topic 'тест' --post-type post --post-status draft",
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


@site_app.command("refresh-wp")
def site_refresh_wp(
    slug: str = typer.Option(..., "--site", "-s", help="Site slug"),
) -> None:
    """Re-run WP-introspection и перезаписать wordpress.introspection в config.yaml."""
    import yaml as _yaml
    from pathlib import Path

    from app.adapters.wordpress_db import WordPressDbAdapter
    from app.core.config import get_settings
    from app.services.wp_introspect import collect_introspection

    configure_logging()
    settings = get_settings()
    config_path = (
        Path(settings.sites_config_root or "sites").expanduser().resolve() / slug / "config.yaml"
    )
    if not config_path.is_file():
        typer.secho(f"config not found: {config_path}", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    raw = _yaml.safe_load(config_path.read_text(encoding="utf-8"))
    wp_section = (raw or {}).get("wordpress") or {}
    db_url = wp_section.get("database_url")
    table_prefix = wp_section.get("table_prefix", "wp_")
    if not db_url:
        typer.secho("wordpress.database_url missing in config", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=2)

    wp = WordPressDbAdapter(database_url=db_url, table_prefix=table_prefix)
    wp.ping()
    intro = collect_introspection(wp)
    wp_section["introspection"] = intro.model_dump()
    raw["wordpress"] = wp_section
    config_path.write_text(
        _yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    typer.echo(
        json.dumps(
            {
                "slug": slug,
                "refreshed": True,
                "siteurl": intro.siteurl,
                "post_types": [pt.name for pt in intro.post_types[:6]],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


@site_app.command("init-wp-full")
def site_init_wp_full(
    slug: str = typer.Option(
        ...,
        "--site",
        "-s",
        help="Site slug (claudesite-theme должна быть активна)",
    ),
    instruction: str = typer.Option(
        ...,
        "--instruction",
        "-i",
        help="Описание бизнеса: индустрия + бренд + чем занимается",
    ),
    skip_blog_posts: bool = typer.Option(False, "--skip-blog", help="Пропустить блог-посты"),
    skip_images: bool = typer.Option(False, "--skip-images", help="Пропустить featured images"),
) -> None:
    """Полный bootstrap WP-сайта по одному описанию (страницы, услуги, блог, ...)."""
    configure_logging()

    from app.core.site_runtime import SiteRuntimeResolver
    from app.services.wp_bootstrap import bootstrap_site

    factory = get_session_factory()
    with factory() as session:
        try:
            rt = SiteRuntimeResolver().resolve(session, slug)
        except OrchestratorError as e:
            _fail(e)
        try:
            progress = bootstrap_site(
                session=session,
                rt=rt,
                instruction=instruction,
                skip_blog_posts=skip_blog_posts,
                skip_images=skip_images,
            )
        except Exception as e:
            typer.secho(f"bootstrap failed: {type(e).__name__}: {e}", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from e

    typer.echo(
        json.dumps(
            {
                "brand": progress.plan.brand,
                "tagline": progress.plan.tagline,
                "industry": progress.plan.industry_label,
                "site_options_set": progress.site_options_set,
                "blog_categories": len(progress.blog_categories),
                "service_categories": len(progress.service_categories),
                "pages_created": len(progress.pages),
                "services_created": len(progress.services),
                "cases_created": len(progress.cases),
                "team_created": len(progress.team),
                "faqs_created": len(progress.faqs),
                "blog_posts_created": len(progress.blog_posts),
                "errors": progress.errors,
                "home_url": rt.file.wordpress.public_site_url if rt.file.wordpress else None,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


@site_app.command("do")
def site_do(
    slug: str = typer.Option(..., "--site", "-s", help="Site slug (wordpress mode)"),
    instruction: str = typer.Option(
        ...,
        "--instruction",
        "-i",
        help="Natural-language: 'добавь в блог статью про b2b' и т.п.",
    ),
) -> None:
    """Natural-language publish: router → publish (только mode: wordpress)."""
    configure_logging()

    from app.core.site_runtime import SiteRuntimeResolver
    from app.db.models.enums import SiteMode
    from app.services.wp_publish import publish_from_instruction

    factory = get_session_factory()
    with factory() as session:
        try:
            rt = SiteRuntimeResolver().resolve(session, slug)
        except OrchestratorError as e:
            _fail(e)
        if rt.effective_mode != SiteMode.WORDPRESS:
            typer.secho(
                f"site {slug!r} mode is {rt.effective_mode.value!r}, expected 'wordpress'",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=2)
        try:
            result = publish_from_instruction(session=session, rt=rt, instruction=instruction)
        except Exception as e:
            typer.secho(f"do failed: {type(e).__name__}: {e}", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from e

    typer.echo(
        json.dumps(
            {
                "page_id": result.page_id,
                "slug": result.slug,
                "title": result.title,
                "wp_post_id": result.wp_post_id,
                "post_type": result.post_type,
                "post_status": result.post_status,
                "taxonomy": result.taxonomy,
                "term_slug": result.term_slug,
                "template": result.template,
                "chars_body_md": result.chars_body_md,
                "humanizer_chain": list(result.humanizer_chain),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


@site_app.command("publish")
def site_publish(
    slug: str = typer.Option(..., "--site", "-s", help="Site slug (wordpress mode)"),
    topic: str = typer.Option(..., "--topic", "-t", help="Тема контента"),
    post_type: str = typer.Option("post", "--post-type", help="WP post_type"),
    post_status: str = typer.Option("publish", "--post-status", help="publish | draft | pending | private"),
    taxonomy: str | None = typer.Option(None, "--taxonomy", help="taxonomy для assignment"),
    term: str | None = typer.Option(None, "--term", help="slug term'а в taxonomy"),
    template: str | None = typer.Option(None, "--template", help="_wp_page_template файл"),
) -> None:
    """Explicit-mode publish (только mode: wordpress)."""
    configure_logging()

    from app.core.site_runtime import SiteRuntimeResolver
    from app.db.models.enums import SiteMode
    from app.services.wp_publish import publish_action
    from app.services.wp_router import WpAction

    action = WpAction(
        post_type=post_type,
        post_status=post_status,  # type: ignore[arg-type]
        topic=topic,
        taxonomy=taxonomy,
        term_slug=term,
        template=template,
        extra_postmeta={},
        rationale="cli explicit",
    )
    factory = get_session_factory()
    with factory() as session:
        try:
            rt = SiteRuntimeResolver().resolve(session, slug)
        except OrchestratorError as e:
            _fail(e)
        if rt.effective_mode != SiteMode.WORDPRESS:
            typer.secho(
                f"site {slug!r} mode is {rt.effective_mode.value!r}, expected 'wordpress'",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=2)
        try:
            result = publish_action(session=session, rt=rt, action=action)
        except Exception as e:
            typer.secho(f"publish failed: {type(e).__name__}: {e}", err=True, fg=typer.colors.RED)
            raise typer.Exit(code=1) from e

    typer.echo(
        json.dumps(
            {
                "page_id": result.page_id,
                "slug": result.slug,
                "title": result.title,
                "wp_post_id": result.wp_post_id,
                "post_type": result.post_type,
                "taxonomy": result.taxonomy,
                "term_slug": result.term_slug,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


