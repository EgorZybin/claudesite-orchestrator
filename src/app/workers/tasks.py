from __future__ import annotations

import html as _html
import logging
from datetime import UTC, datetime

from app.core.exceptions import OrchestratorError
from app.db.session import get_session_factory
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
_site_logger = logging.getLogger("app.workers.site_pipeline")

_DEFAULT_FORM_SUBJECT = "Новая заявка с {brand}"


@celery_app.task(name="app.ping")
def ping() -> str:
    """Проверка связки broker/worker."""
    return "pong"


def _resolve_form_destination(rt) -> tuple[str | None, str | None, list[str]]:
    """Возвращает (to_email, from_name, cc_emails). Если у сайта нет forms.notify_email — to_email=None."""
    forms_cfg = rt.file.forms if rt.file.forms else None
    notify = forms_cfg.notify_email if forms_cfg else None
    from_name = (forms_cfg.from_name if forms_cfg else None) or (rt.file.display_name or rt.slug)
    cc = list(forms_cfg.cc_emails) if (forms_cfg and forms_cfg.cc_emails) else []
    if notify and "@" in notify:
        return notify.strip(), from_name, cc
    return None, from_name, []


def _compose_form_email(
    *,
    site_slug: str,
    brand: str,
    page_slug: str | None,
    form_id: str,
    payload: dict,
    submitted_at_iso: str,
    ip: str | None,
    subject_template: str | None,
) -> tuple[str, str, str, str | None]:
    placeholders = {
        "brand": brand,
        "site_slug": site_slug,
        "form_id": form_id,
        "page_slug": page_slug or "",
    }
    tmpl = subject_template or _DEFAULT_FORM_SUBJECT
    try:
        subject = tmpl.format(**placeholders)
    except (KeyError, IndexError):
        subject = f"Новая заявка с {brand}"

    reply_to: str | None = None
    for k, v in (payload or {}).items():
        if (k or "").lower() in {"email", "e-mail", "почта"} and isinstance(v, str) and "@" in v:
            reply_to = v.strip()
            break

    lines = [f"Новая заявка с сайта {brand} ({site_slug})", ""]
    if page_slug:
        lines.append(f"Страница: /{page_slug}")
    lines.append(f"Форма: {form_id}")
    lines.append(f"Время: {submitted_at_iso}")
    if ip:
        lines.append(f"IP: {ip}")
    lines.append("")
    lines.append("Поля:")
    for k, v in (payload or {}).items():
        lines.append(f"  {k}: {v}")
    body_text = "\n".join(lines)

    rows = "".join(
        f"<tr><td style='padding:6px 12px;border:1px solid #e5e7eb;background:#f9fafb;font-weight:600;vertical-align:top'>{_html.escape(str(k))}</td>"
        f"<td style='padding:6px 12px;border:1px solid #e5e7eb'>{_html.escape(str(v))}</td></tr>"
        for k, v in (payload or {}).items()
    )
    body_html = (
        f"<div style='font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#111;max-width:560px'>"
        f"<h2 style='margin:0 0 8px;font-size:18px'>Новая заявка</h2>"
        f"<p style='margin:0 0 12px;color:#475569'>Сайт: <b>{_html.escape(brand)}</b> ({_html.escape(site_slug)})"
        f"{f' &middot; страница /{_html.escape(page_slug)}' if page_slug else ''}</p>"
        f"<table style='border-collapse:collapse;width:100%;font-size:14px'>{rows}</table>"
        f"<p style='color:#9ca3af;font-size:12px;margin-top:14px'>"
        f"Форма: {_html.escape(form_id)} &middot; {_html.escape(submitted_at_iso)}"
        f"{f' &middot; IP: {_html.escape(ip)}' if ip else ''}</p></div>"
    )
    return subject, body_text, body_html, reply_to


@celery_app.task(
    bind=True,
    name="app.form.notify",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def notify_form_submission_task(self, submission_id: int) -> dict:
    from app.adapters.errors import AdapterConfigurationError, SmtpEmailError
    from app.adapters.smtp_email import SmtpEmailAdapter
    from app.core.config import get_settings
    from app.core.site_runtime import SiteRuntimeResolver
    from app.db.repos.form_submissions import FormSubmissionRepository
    from app.db.repos.sites import SiteRepository

    settings = get_settings()
    factory = get_session_factory()
    session = factory()
    try:
        with session.begin():
            repo = FormSubmissionRepository(session)
            row = repo.get_by_id(submission_id)
            if row is None:
                return {"ok": False, "error": "submission not found", "id": submission_id}
            if row.status in ("sent", "archived", "spam_honeypot"):
                return {"ok": True, "skipped": True, "status": row.status, "id": submission_id}

            site = SiteRepository(session).get_by_id(row.site_id) if hasattr(SiteRepository(session), "get_by_id") else None
            if site is None:
                from sqlalchemy import text as _sql_text
                slug = session.execute(_sql_text("SELECT slug FROM sites WHERE id=:id"), {"id": row.site_id}).scalar()
            else:
                slug = site.slug
            rt = SiteRuntimeResolver().resolve(session, slug)

            to_email, from_name, cc_emails = _resolve_form_destination(rt)
            if to_email is None:
                repo.update_status(submission_id, "no_destination")
                return {"ok": True, "status": "no_destination", "id": submission_id}

            subject_tmpl = (rt.file.forms.subject_template if rt.file.forms else None) or _DEFAULT_FORM_SUBJECT
            brand = rt.file.display_name or rt.slug
            subject, body_text, body_html, reply_to = _compose_form_email(
                site_slug=slug,
                brand=brand,
                page_slug=row.page_slug,
                form_id=row.form_id,
                payload=row.payload or {},
                submitted_at_iso=(row.submitted_at.isoformat() if row.submitted_at else ""),
                ip=row.ip,
                subject_template=subject_tmpl,
            )

            adapter = SmtpEmailAdapter(settings=settings)
            try:
                adapter.send(
                    to=to_email,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html,
                    reply_to=reply_to,
                    cc=cc_emails or None,
                    from_name=from_name,
                )
            except AdapterConfigurationError:
                repo.update_status(submission_id, "no_destination", error_text="SMTP not configured")
                return {"ok": True, "status": "no_destination", "id": submission_id}
            except SmtpEmailError as e:
                if self.request.retries >= self.max_retries:
                    repo.update_status(submission_id, "email_failed", error_text=str(e)[:1024])
                    return {"ok": False, "status": "email_failed", "id": submission_id, "error": str(e)}
                raise

            repo.update_status(submission_id, "sent")
            return {"ok": True, "status": "sent", "id": submission_id, "to": to_email}
    finally:
        session.close()


def _mark_job_running(job_id: int) -> None:
    from app.db.models.enums import JobRunStatus
    from app.db.repos.jobs import JobRunRepository

    factory = get_session_factory()
    with factory() as s:
        job = JobRunRepository(s).get_by_id(job_id)
        if job is None:
            raise OrchestratorError(f"job_run id={job_id} not found")
        job.status = JobRunStatus.RUNNING
        job.started_at = datetime.now(UTC).replace(tzinfo=None)
        s.commit()


def _mark_job_done(job_id: int, *, summary: str, page_ids: list[int] | None = None) -> None:
    from app.db.models.enums import JobRunStatus
    from app.db.repos.jobs import JobRunRepository

    factory = get_session_factory()
    with factory() as s:
        job = JobRunRepository(s).get_by_id(job_id)
        if job is None:
            return
        job.status = JobRunStatus.SUCCESS
        job.summary = summary[:2000]
        job.finished_at = datetime.now(UTC).replace(tzinfo=None)
        if page_ids:
            job.page_ids = list(page_ids)
        s.commit()


def _mark_job_failed(job_id: int, *, error: str) -> None:
    from app.db.models.enums import JobRunStatus
    from app.db.repos.jobs import JobRunRepository

    factory = get_session_factory()
    with factory() as s:
        job = JobRunRepository(s).get_by_id(job_id)
        if job is None:
            return
        job.status = JobRunStatus.FAILED
        job.summary = error[:2000]
        job.finished_at = datetime.now(UTC).replace(tzinfo=None)
        s.commit()


def _with_job_run(job_id: int, task_label: str):
    """Декоратор: оборачивает impl-функцию в mark_running/mark_done/mark_failed."""

    def wrap(fn):
        def runner(*args, **kwargs):
            _mark_job_running(job_id)
            try:
                result = fn(*args, **kwargs)
            except Exception as e:
                _mark_job_failed(job_id, error=f"{type(e).__name__}: {e}")
                raise
            if isinstance(result, dict):
                if "version_num" in result:
                    summary = f"{task_label}: v{result['version_num']} published"
                elif "page_id" in result:
                    summary = f"{task_label}: page_id={result['page_id']} ({result.get('slug', '?')})"
                else:
                    summary = f"{task_label}: ok"
            else:
                summary = f"{task_label}: ok"
            page_ids = (
                [result.get("page_id")]
                if isinstance(result, dict) and result.get("page_id")
                else None
            )
            _mark_job_done(job_id, summary=summary, page_ids=page_ids)
            return result

        return runner

    return wrap


def _generate_site_impl(
    *,
    site_slug: str,
    user_prompt: str,
    target_pages: int = 6,
    accent_hsl: str | None = None,
    neutral_family: str | None = None,
    display_font: str | None = None,
    body_font: str | None = None,
    extra_notes: str | None = None,
    skip_expand_prose: bool = False,
    design_tokens: dict | None = None,
) -> dict[str, object]:
    """End-to-end site generation. Synchronous callable for tests + worker wrapper.

    Sequence:
        1. resolve site_id by slug
        2. content_plan (LLM via /generate) → SiteContent
        3. expand_site_prose (LLM × pages_with_paragraphs)
        4. persist_site_content → INSERT pages + content_blocks + modules
        5. generate_initial_site → claude_project.build via /project/build
        6. → SiteVersion published
    """
    from app.core.exceptions import SiteConfigNotFoundError
    from app.core.site_runtime import SiteRuntimeResolver
    from app.db.repos.sites import SiteRepository
    from app.services.content_plan import llm_plan_site_content
    from app.services.image_generation import attach_images_to_site_content
    from app.services.prose_expand import expand_site_prose
    from app.services.site_build.persist import persist_site_content
    from app.services.site_build.react_builder import build_initial_site

    factory = get_session_factory()

    with factory() as s:
        site = SiteRepository(s).get_by_slug(site_slug)
        if site is None:
            raise OrchestratorError(f"site not found: slug={site_slug}")
        site_id = site.id
    _site_logger.info("site_generate_start site_id=%s slug=%s", site_id, site_slug)

    content = llm_plan_site_content(user_prompt=user_prompt, target_pages=target_pages)
    _site_logger.info(
        "content_plan_ok site_id=%s pages=%d modules=%d brand=%s",
        site_id, len(content.pages), len(content.modules), content.site_meta.brand,
    )

    if not skip_expand_prose:
        expanded_pages = expand_site_prose(pages=content.pages, brand=content.site_meta.brand)
        content = content.model_copy(update={"pages": expanded_pages})
        _site_logger.info("expand_prose_ok site_id=%s pages=%d", site_id, len(expanded_pages))

    with factory() as s:
        counts = persist_site_content(s, site_id=site_id, content=content)
        s.commit()
    _site_logger.info("persist_ok site_id=%s counts=%s", site_id, counts)

    from concurrent.futures import ThreadPoolExecutor

    content_for_cli = content.model_copy(deep=True)

    def _image_worker() -> int:
        try:
            with factory() as s:
                try:
                    runtime = SiteRuntimeResolver().resolve(s, site_slug)
                except SiteConfigNotFoundError:
                    _site_logger.info(
                        "image_attach_skip_no_config site_id=%s slug=%s",
                        site_id, site_slug,
                    )
                    return 0
            attach_images_to_site_content(
                content,
                site_id=site_id,
                runtime=runtime,
                session_factory=factory,
            )
            n = sum(1 for p in content.pages if p.hero_image)
            _site_logger.info(
                "image_attach_done site_id=%s pages_with_hero=%d", site_id, n,
            )
            return n
        except Exception:
            _site_logger.exception("image_attach_failed site_id=%s — continuing", site_id)
            return 0

    def _cli_worker() -> dict[str, object]:
        with factory() as s:
            version = build_initial_site(
                s,
                site_id=site_id,
                site_content=content_for_cli,
                accent_hsl=accent_hsl,
                neutral_family=neutral_family,
                display_font=display_font,
                body_font=body_font,
                extra_notes=extra_notes,
                design_tokens=design_tokens,
            )
            s.commit()
            manifest = version.manifest_json or {}
            asset_hashes_inner = (
                manifest.get("asset_hashes") if isinstance(manifest, dict) else {}
            ) or {}
            return {
                "version_num": version.version_num,
                "version_id": version.id,
                "asset_hashes": asset_hashes_inner,
            }

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="gen-site") as pool:
        img_future = pool.submit(_image_worker)
        cli_future = pool.submit(_cli_worker)
        cli_result = cli_future.result()
        n_with_hero = img_future.result()

    version_num = cli_result["version_num"]
    version_id = cli_result["version_id"]
    asset_hashes = cli_result["asset_hashes"]

    _site_logger.info(
        "site_generate_done site_id=%s version=%s pages_with_hero=%d",
        site_id, version_num, n_with_hero,
    )
    return {
        "site_id": site_id,
        "site_slug": site_slug,
        "version_num": version_num,
        "version_id": version_id,
        "pages_persisted": counts["pages"],
        "content_blocks_persisted": counts["content_blocks"],
        "modules_persisted": counts["modules"],
        "asset_hashes": asset_hashes,
    }


@celery_app.task(bind=True, name="app.site.generate")
def generate_site_task(
    self,
    site_slug: str,
    user_prompt: str,
    target_pages: int = 6,
    job_id: int | None = None,
    design_tokens: dict | None = None,
) -> dict[str, object]:
    if job_id is not None:
        return _with_job_run(job_id, "generate_site")(_generate_site_impl)(
            site_slug=site_slug,
            user_prompt=user_prompt,
            target_pages=target_pages,
            design_tokens=design_tokens,
        )
    return _generate_site_impl(
        site_slug=site_slug,
        user_prompt=user_prompt,
        target_pages=target_pages,
        design_tokens=design_tokens,
    )


_TEXT_FIELD_BY_KIND: dict[str, str] = {
    "paragraph": "markdown",
    "heading": "text",
    "quote": "text",
    "cta": "label",
}


def _rewrite_block_prompt(*, current_text: str, instruction: str, kind: str) -> str:
    from app.services.prose_expand import HUMANIZATION_RULES as _HR

    inline_md_note = (
        "Сохраняй inline-markdown форматирование (**bold**, *em*, `code`, "
        "[link](href)) если оно уже есть и уместно после правки."
        if kind in ("paragraph", "quote")
        else "Возвращай чистый текст без markdown-форматирования."
    )
    no_h_note = (
        "Не добавляй markdown-заголовки (## ...) — это отдельный block kind."
        if kind == "paragraph"
        else ""
    )
    short_note = (
        "Это короткий заголовок/метка (≤200 символов); не делай его параграфом."
        if kind in ("heading", "cta")
        else ""
    )
    return (
        "Ты редактируешь один фрагмент текста на сайте. Примени инструкцию "
        "и верни ТОЛЬКО новый текст без преамбулы, кавычек или markdown-обёртки.\n\n"
        f"Тип фрагмента: {kind}\n"
        f"Текущий текст:\n{current_text}\n\n"
        f"Инструкция редактора:\n{instruction}\n\n"
        "Правила:\n"
        "- Верни ТОЛЬКО новый текст без объяснений и без кавычек вокруг.\n"
        f"- {inline_md_note}\n"
        f"{('- ' + no_h_note + chr(10)) if no_h_note else ''}"
        f"{('- ' + short_note + chr(10)) if short_note else ''}"
        f"\n{_HR}\n"
        "Новый текст:"
    )


def _strip_rewrite_envelope(raw: str) -> str:
    import re

    t = (raw or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    if len(t) >= 2 and t[0] in ('"', "«", "“") and t[-1] in ('"', "»", "”"):
        t = t[1:-1].strip()
    return t


def _rewrite_block_impl(
    *,
    site_slug: str,
    page_slug: str,
    block_id: int,
    instruction: str,
) -> dict[str, object]:
    from sqlalchemy import select

    from app.adapters.errors import AdapterError
    from app.core.config import get_settings
    from app.core.llm_provider_factory import make_text_llm
    from app.db.models.page import Page
    from app.db.models.site import Site
    from app.db.models.site_content_block import SiteContentBlock

    factory = get_session_factory()
    with factory() as s:
        site = s.scalar(select(Site).where(Site.slug == site_slug))
        if site is None:
            raise OrchestratorError(f"site not found: {site_slug}")
        page = s.scalar(select(Page).where(Page.site_id == site.id, Page.slug == page_slug))
        if page is None:
            raise OrchestratorError(f"page not found: /{page_slug}")
        block = s.get(SiteContentBlock, block_id)
        if block is None or block.page_id != page.id:
            raise OrchestratorError(f"block not found on page: id={block_id}")
        field = _TEXT_FIELD_BY_KIND.get(block.kind)
        if field is None:
            raise OrchestratorError(f"rewrite not supported for kind={block.kind!r}")
        current = (block.props or {}).get(field) or ""
        if not isinstance(current, str) or not current.strip():
            raise OrchestratorError(f"block.props.{field} empty")
        kind_for_prompt = block.kind
        site_id_for_log = site.id
        page_id_for_log = page.id

    settings = get_settings()
    llm = make_text_llm(settings)
    try:
        raw = llm.generate(
            prompt=_rewrite_block_prompt(
                current_text=current,
                instruction=instruction,
                kind=kind_for_prompt,
            ),
            system="You are an editor rewriting one text fragment.",
        )
    except AdapterError as e:
        raise OrchestratorError(f"LLM error: {e}") from e

    new_text = _strip_rewrite_envelope(raw)
    if not new_text:
        raise OrchestratorError("LLM returned empty text")

    with factory() as s:
        block = s.get(SiteContentBlock, block_id)
        if block is None:
            raise OrchestratorError(f"block disappeared mid-edit: id={block_id}")
        new_props = dict(block.props or {})
        new_props[field] = new_text
        block.props = new_props
        s.commit()

    _site_logger.info(
        "rewrite_block_ok site_id=%s page_id=%s block=%s kind=%s old=%d new=%d",
        site_id_for_log, page_id_for_log, block_id, kind_for_prompt, len(current), len(new_text),
    )
    return {
        "ok": True,
        "block_id": block_id,
        "kind": kind_for_prompt,
        "field": field,
        "old_text": current,
        "new_text": new_text,
        "delta_chars": len(new_text) - len(current),
    }


@celery_app.task(bind=True, name="app.site.rewrite_block")
def rewrite_block_task(
    self,
    site_slug: str,
    page_slug: str,
    block_id: int,
    instruction: str,
) -> dict[str, object]:
    return _rewrite_block_impl(
        site_slug=site_slug,
        page_slug=page_slug,
        block_id=block_id,
        instruction=instruction,
    )


def _design_edit_impl(
    *,
    site_slug: str,
    instruction: str,
    scope: list[str] | None = None,
    timeout_seconds: int = 900,
) -> dict[str, object]:
    from app.db.repos.sites import SiteRepository
    from app.services.site_build.editor import design_edit

    factory = get_session_factory()
    with factory() as s:
        site = SiteRepository(s).get_by_slug(site_slug)
        if site is None:
            raise OrchestratorError(f"site not found: {site_slug}")
        site_id = site.id

    with factory() as s:
        result = design_edit(
            s,
            site_id=site_id,
            instruction=instruction,
            scope=scope,
            timeout_seconds=timeout_seconds,
        )
        s.commit()

    _site_logger.info(
        "design_edit_ok site_id=%s version=%s files_changed=%d",
        site_id, result.get("version_num"), len(result.get("files_changed") or []),
    )
    return {"site_id": site_id, "site_slug": site_slug, **result}


@celery_app.task(bind=True, name="app.site.design_edit")
def design_edit_task(
    self,
    job_id: int,
    site_slug: str,
    instruction: str,
    scope: list[str] | None = None,
    timeout_seconds: int = 900,
) -> dict[str, object]:
    return _with_job_run(job_id, "design_edit")(_design_edit_impl)(
        site_slug=site_slug,
        instruction=instruction,
        scope=scope,
        timeout_seconds=timeout_seconds,
    )


def _add_page_impl(
    *,
    site_slug: str,
    slug: str,
    page_type: str,
    keyword: str,
    title_hint: str | None = None,
    industry: str | None = None,
    skip_expand_prose: bool = False,
) -> dict[str, object]:
    """Добавить ОДНУ страницу к существующему сайту.

    template page_type должен быть в manifest.page_types — иначе caller должен
    сначала позвать /page-types extend.
    """
    import hashlib

    from sqlalchemy import select

    from app.db.models.enums import PageStatus
    from app.db.models.page import Page as PageModel
    from app.db.models.site import Site
    from app.db.repos.site_content_blocks import SiteContentBlockRepository
    from app.db.repos.site_versions import SiteVersionRepository
    from app.services.content_plan_single_page import llm_plan_single_page_content
    from app.services.prose_expand import expand_page_prose

    factory = get_session_factory()

    with factory() as s:
        site = s.scalar(select(Site).where(Site.slug == site_slug))
        if site is None:
            raise OrchestratorError(f"site not found: {site_slug}")
        site_id = site.id
        brand = site.display_name or site_slug
        existing = list(
            s.scalars(select(PageModel.slug).where(PageModel.site_id == site_id)).all()
        )
        if slug in existing:
            raise OrchestratorError(f"page slug {slug!r} already exists on site {site_slug}")

        v_repo = SiteVersionRepository(s)
        current = v_repo.get_current(site_id)
        if current is None:
            raise OrchestratorError(
                f"site {site_slug} has no published version; cannot add pages"
            )
        manifest = current.manifest_json or {}
        manifest_types = list(manifest.get("page_types") or [])
        if page_type not in manifest_types:
            raise OrchestratorError(
                f"page_type={page_type!r} not in manifest.page_types={manifest_types}; "
                "extend templates via /admin/sites/<slug>/page-types first"
            )

    page = llm_plan_single_page_content(
        brand=brand,
        industry=industry or "general",
        language="ru",
        page_type=page_type,
        slug=slug,
        keyword=keyword,
        title_hint=title_hint,
        existing_slugs=existing,
    )
    if not skip_expand_prose:
        page = expand_page_prose(page, brand=brand, keyword=keyword)

    with factory() as s:
        keyword_hash = hashlib.sha256(f"{slug}|{keyword}".encode("utf-8")).hexdigest()
        row = PageModel(
            site_id=site_id,
            slug=page.slug,
            title=page.title,
            status=PageStatus.PUBLISHED,
            page_type=page.page_type,
            keyword_raw=keyword,
            keyword_hash=keyword_hash,
            seo_overrides={"description": page.seo_description},
            nav_label=page.nav_label,
            sort_order=page.nav_order if page.nav_order is not None else 100,
            modules_used=list(page.modules_used or []),
            hero_image=page.hero_image,
            hero_title=page.hero_title,
            hero_subtitle=page.hero_subtitle,
        )
        s.add(row)
        s.flush()
        page_id = row.id

        cb_repo = SiteContentBlockRepository(s)
        blocks_data = [{"kind": b.kind, "props": b.props} for b in page.content_blocks]
        cb_repo.replace_for_page(page_id, blocks_data)
        s.commit()

    _site_logger.info(
        "add_page_ok site_id=%s slug=%s page_type=%s blocks=%d",
        site_id, slug, page_type, len(page.content_blocks),
    )
    return {
        "ok": True,
        "site_id": site_id,
        "page_id": page_id,
        "slug": slug,
        "page_type": page_type,
        "content_blocks": len(page.content_blocks),
        "url": f"/public/{site_slug}/{slug}",
    }


@celery_app.task(bind=True, name="app.site.add_page")
def add_page_task(
    self,
    job_id: int,
    site_slug: str,
    slug: str,
    page_type: str,
    keyword: str,
    title_hint: str | None = None,
    industry: str | None = None,
    skip_expand_prose: bool = False,
) -> dict[str, object]:
    return _with_job_run(job_id, "add_page")(_add_page_impl)(
        site_slug=site_slug,
        slug=slug,
        page_type=page_type,
        keyword=keyword,
        title_hint=title_hint,
        industry=industry,
        skip_expand_prose=skip_expand_prose,
    )


def _add_page_type_impl(
    *,
    site_slug: str,
    name: str,
    description: str,
    slots_needed: list[str] | None = None,
    timeout_seconds: int = 900,
) -> dict[str, object]:
    from app.db.repos.sites import SiteRepository
    from app.services.site_build.page_type_extender import add_page_type

    factory = get_session_factory()
    with factory() as s:
        site = SiteRepository(s).get_by_slug(site_slug)
        if site is None:
            raise OrchestratorError(f"site not found: {site_slug}")
        site_id = site.id

    with factory() as s:
        result = add_page_type(
            s,
            site_id=site_id,
            name=name,
            description=description,
            slots_needed=slots_needed,
            timeout_seconds=timeout_seconds,
        )
        s.commit()

    _site_logger.info(
        "add_page_type_ok site_id=%s name=%s version=%s",
        site_id, name, result.get("version_num"),
    )
    return {"site_id": site_id, "site_slug": site_slug, **result}


@celery_app.task(bind=True, name="app.site.add_page_type")
def add_page_type_task(
    self,
    job_id: int,
    site_slug: str,
    name: str,
    description: str,
    slots_needed: list[str] | None = None,
    timeout_seconds: int = 900,
) -> dict[str, object]:
    return _with_job_run(job_id, "add_page_type")(_add_page_type_impl)(
        site_slug=site_slug,
        name=name,
        description=description,
        slots_needed=slots_needed,
        timeout_seconds=timeout_seconds,
    )
