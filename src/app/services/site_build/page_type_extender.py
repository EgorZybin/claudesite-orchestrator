from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.adapters.claude_project import ProjectEditResult, RemoteClaudeProjectAdapter
from app.db.models.site_version import SiteVersion
from app.services.site_build.storage import FilesystemSiteStorage

logger = logging.getLogger(__name__)


class PageTypeExtensionError(Exception):
    pass


_SYSTEM = (
    "You are an experienced web developer extending an existing static site "
    "with a NEW page_type template. Use Read to see existing templates "
    "(_layout.html, home.html, etc.) and learn the design language. Use Write "
    "to create the new template. Use Edit to update manifest.json. DO NOT modify "
    "ANY other files — only the new template + manifest.json are in scope. "
    "Don't introduce new CSS classes outside what already exists."
)


def _build_extend_prompt(
    *,
    name: str,
    description: str,
    slots_needed: list[str] | None,
    existing_page_types: list[str],
) -> str:
    slots_line = (
        f"Suggested slots: {slots_needed}"
        if slots_needed
        else "Pick slots that fit the page purpose. Common slots: hero, content_blocks, "
        "features, stats, testimonials, pricing, team, faq, contact_info."
    )
    return f"""Add a new page_type to this site.

New page_type name: `{name}`
What it's for: {description}
{slots_line}

Existing page_types in this site: {existing_page_types}

Your task:
1. Read `templates/_layout.html` to understand the base shell and global Jinja
   context (site, page, content, modules, nav, footer).
2. Read 1-2 existing page templates (e.g., `templates/home.html`,
   `templates/blog_post.html`) to learn the design patterns used: section
   classes, container structure, how modules are guarded with
   `{{% if has_module(...) %}}`.
3. Create `templates/{name}.html` that:
   - `{{% extends "_layout.html" %}}`
   - Inside `{{% block content %}}` renders the slots appropriate for this
     page_type's purpose.
   - Uses ONLY CSS classes and styles already present in existing templates +
     bundle.css. Don't introduce new class names.
   - Guards every module section with `{{% if has_module("<name>") %}}`.
   - Iterates `page.content_blocks` if the page_type expects rich body content.
4. Update `manifest.json`:
   - Add `"{name}"` to the `page_types` array.
   - Add `page_slots["{name}"]` listing exactly the slots your new template uses
     (subset of hero, content_blocks + module names like features, faq, etc.).
   - Do NOT change `asset_hashes`, `design_tokens`, or other unrelated fields.

When done, write a brief 1-2 sentence summary of what you built.

Constraints:
- ONLY edit `templates/{name}.html` and `manifest.json`. Scope is enforced — any
  other file modification will be rejected.
- Do NOT add new CSS to bundle.css (no scope for it).
- Don't break existing manifest schema (keep all other fields intact).
"""


def add_page_type(
    session: Session,
    *,
    site_id: int,
    name: str,
    description: str,
    slots_needed: list[str] | None = None,
    timeout_seconds: int = 900,
) -> dict:
    """Расширить сайт новым page_type'ом через Claude CLI.

    Returns: dict с version_num, files_changed, manifest_page_types_after.
    Raises: PageTypeExtensionError на любую проблему.
    """
    storage = FilesystemSiteStorage(session)
    try:
        seed_files = storage.read_version(site_id)
    except Exception as e:
        raise PageTypeExtensionError(f"cannot read current site_id={site_id}: {e}") from e

    if not seed_files:
        raise PageTypeExtensionError(f"site_id={site_id} has no current version")

    try:
        manifest_before = json.loads(seed_files.get("manifest.json", "{}"))
    except json.JSONDecodeError as e:
        raise PageTypeExtensionError(f"current manifest.json unparseable: {e}") from e

    existing_types = list(manifest_before.get("page_types") or [])
    if name in existing_types:
        raise PageTypeExtensionError(
            f"page_type {name!r} already exists in manifest.page_types={existing_types}"
        )

    scope = [f"templates/{name}.html", "manifest.json"]
    prompt = _build_extend_prompt(
        name=name,
        description=description,
        slots_needed=slots_needed,
        existing_page_types=existing_types,
    )

    logger.info(
        "add_page_type_start site_id=%s name=%s existing=%s",
        site_id, name, existing_types,
    )

    adapter = RemoteClaudeProjectAdapter()
    result: ProjectEditResult = adapter.edit(
        seed_files=seed_files,
        scope=scope,
        prompt=prompt,
        system=_SYSTEM,
        tools=["Edit", "Write", "Read", "Grep", "Glob"],
        timeout_seconds=timeout_seconds,
    )
    if not result.success:
        raise PageTypeExtensionError(
            f"Claude failed: {result.error} (duration={result.duration_seconds:.1f}s)"
        )

    if not result.files_changed:
        raise PageTypeExtensionError(
            "Claude returned success but no files changed. "
            f"Summary: {result.summary!r}"
        )

    new_files = dict(seed_files)
    for entry in result.files_changed:
        new_files[entry.path] = entry.content

    new_template_path = f"templates/{name}.html"
    if new_template_path not in new_files:
        raise PageTypeExtensionError(
            f"Claude didn't create {new_template_path} "
            f"(files_changed={[e.path for e in result.files_changed]})"
        )

    try:
        manifest_after = json.loads(new_files["manifest.json"])
    except json.JSONDecodeError as e:
        raise PageTypeExtensionError(f"manifest.json after edit unparseable: {e}") from e

    types_after = list(manifest_after.get("page_types") or [])
    if name not in types_after:
        raise PageTypeExtensionError(
            f"Claude didn't add {name!r} to manifest.page_types={types_after}"
        )

    page_slots_after = manifest_after.get("page_slots") or {}
    if name not in page_slots_after or not isinstance(page_slots_after[name], list):
        raise PageTypeExtensionError(
            f"Claude didn't add page_slots[{name!r}] as list "
            f"(have keys: {sorted(page_slots_after.keys())})"
        )

    from jinja2 import Environment
    from jinja2.exceptions import TemplateSyntaxError

    try:
        Environment().parse(new_files[new_template_path])
    except TemplateSyntaxError as e:
        raise PageTypeExtensionError(
            f"new template {new_template_path} has Jinja syntax error: "
            f"line {e.lineno}: {e.message}"
        ) from e

    final_comment = f"add page_type: {name}"
    written = storage.write_version(site_id, new_files, comment=final_comment)
    published = storage.switch_current(site_id, written.version_num)

    logger.info(
        "add_page_type_done site_id=%s name=%s version=%s files_changed=%d duration=%.1fs",
        site_id, name, written.version_num, len(result.files_changed), result.duration_seconds,
    )

    return {
        "version_num": written.version_num,
        "version_id": published.id,
        "page_type_added": name,
        "manifest_page_types_after": types_after,
        "manifest_page_slots_for_new_type": page_slots_after[name],
        "files_changed": [e.path for e in result.files_changed],
        "claude_summary": result.summary,
        "duration_seconds": result.duration_seconds,
    }
