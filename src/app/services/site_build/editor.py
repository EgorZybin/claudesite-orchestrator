from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.adapters.claude_project import ProjectEditResult, RemoteClaudeProjectAdapter
from app.core.config import get_settings
from app.services.site_build.storage import FilesystemSiteStorage

logger = logging.getLogger(__name__)


class DesignEditError(Exception):
    pass


_DEFAULT_SCOPE = [
    "src/**/*.tsx",
    "src/**/*.ts",
    "src/**/*.css",
]

_DIR_SHORTCUTS: dict[str, str] = {
    "src": "src/**/*",
    "components": "src/components/**/*",
    "pages": "src/pages/**/*",
    "sections": "src/components/sections/**/*",
    "ui": "src/components/ui/**/*",
    "lib": "src/lib/**/*",
    "styles": "src/**/*.css",
    "tsx": "src/**/*.tsx",
}

_HIDDEN_PREFIXES = ("dist/", "node_modules/", ".git/")


def _expand_scope(scope: list[str]) -> list[str]:
    """Развернуть directory-shortcuts в glob-паттерны."""
    expanded: list[str] = []
    for item in scope:
        item = (item or "").strip()
        if not item:
            continue
        if item in _DIR_SHORTCUTS:
            expanded.append(_DIR_SHORTCUTS[item])
        elif "/" in item or "*" in item or "." in item:
            expanded.append(item)
        else:
            expanded.append(f"{item}/**/*")
    return expanded


_EDIT_SYSTEM = (
    "You are an experienced web developer making a SMALL targeted edit to an "
    "existing React + Vite + Tailwind + shadcn site. Use Read to inspect the "
    "TSX components and the theme.css, then Edit to make the minimum change "
    "needed.\n\n"
    "Rules:\n"
    "  - DO NOT rewrite files you don't need to change.\n"
    "  - DO NOT modify package.json, vite.config.ts, tailwind.config.ts, "
    "tsconfig.json, postcss.config.js, index.html, src/main.tsx, "
    "src/entry-server.tsx, src/types.ts — those are immutable infrastructure.\n"
    "  - DO NOT modify src/components/ui/* (shadcn primitives are immutable).\n"
    "  - DO NOT add new npm dependencies.\n"
    "  - DO NOT touch dist/ — that's build output; orchestrator rebuilds it.\n"
    "  - Stay within the allowed scope. Out-of-scope changes are rejected.\n"
    "  - Don't break TypeScript or Tailwind validity. After the edit the "
    "    orchestrator runs `vite build` — your edits must compile."
)


def _build_edit_prompt(instruction: str, scope: list[str]) -> str:
    scope_lines = "\n".join(f"  - `{p}`" for p in scope)
    return (
        f"User request: {instruction}\n\n"
        f"You may modify files matching these patterns (scope):\n{scope_lines}\n\n"
        "Make the minimum changes needed. Don't refactor unrelated parts. "
        "When done, write a brief 1-2 sentence summary of what you changed."
    )


def _strip_build_artifacts(files: dict[str, str]) -> dict[str, str]:
    """Drop dist/, node_modules/, .git/ from a read_version dict."""
    return {
        k: v for k, v in files.items()
        if not any(k.startswith(prefix) for prefix in _HIDDEN_PREFIXES)
    }


def design_edit(
    session: Session,
    *,
    site_id: int,
    instruction: str,
    scope: list[str] | None = None,
    timeout_seconds: int = 900,
    comment: str | None = None,
) -> dict:
    """Выполнить дизайн-правку: Claude меняет TSX/CSS, vite перепиливает, новая версия публикуется.

    Returns:
        ``{version_num, version_id, files_changed, claude_summary, duration_seconds}``.
    Raises:
        DesignEditError: Claude fail, scope violation, vite build fail.
    """
    settings = get_settings()
    storage = FilesystemSiteStorage(session)

    try:
        raw_files = storage.read_version(site_id)
    except Exception as e:
        raise DesignEditError(f"cannot read current version site_id={site_id}: {e}") from e
    if not raw_files:
        raise DesignEditError(f"site_id={site_id} has no current version files")

    seed_files = _strip_build_artifacts(raw_files)

    effective_scope = _expand_scope(scope) if scope else list(_DEFAULT_SCOPE)
    logger.info(
        "design_edit_start site_id=%s instruction=%r scope=%s seeds=%d",
        site_id, instruction[:80], effective_scope, len(seed_files),
    )

    adapter = RemoteClaudeProjectAdapter()
    result: ProjectEditResult = adapter.edit(
        seed_files=seed_files,
        scope=effective_scope,
        prompt=_build_edit_prompt(instruction, effective_scope),
        system=_EDIT_SYSTEM,
        tools=["Edit", "Write", "Read", "Grep", "Glob"],
        timeout_seconds=timeout_seconds,
    )
    if not result.success:
        raise DesignEditError(
            f"Claude edit failed: {result.error} (duration={result.duration_seconds:.1f}s)",
        )
    if not result.files_changed:
        raise DesignEditError(
            "Claude returned success=True but files_changed=[] — "
            f"instruction may be too abstract. Summary: {result.summary!r}",
        )

    merged = dict(seed_files)
    illegal_writes: list[str] = []
    for entry in result.files_changed:
        if any(entry.path.startswith(p) for p in _HIDDEN_PREFIXES):
            illegal_writes.append(entry.path)
            continue
        merged[entry.path] = entry.content
    if illegal_writes:
        raise DesignEditError(
            f"Claude tried to write build artifacts: {illegal_writes}. "
            "These paths are off-limits; rerun with a more focused instruction.",
        )

    final_comment = comment or f"edit: {instruction[:160]}"
    written = storage.write_version(
        site_id,
        merged,
        comment=final_comment,
        manifest={},
    )
    site_dir = str(written.version_dir.resolve())
    logger.info(
        "design_edit_persisted site_id=%s version=%d files=%d site_dir=%s",
        site_id, written.version_num, len(merged), site_dir,
    )

    try:
        try:
            with httpx.Client(
                timeout=settings.react_renderer_build_timeout_seconds,
            ) as client:
                resp = client.post(
                    f"{settings.react_renderer_url}/build",
                    json={"site_dir": site_dir},
                )
                resp.raise_for_status()
                body = resp.json()
        except httpx.HTTPError as e:
            raise DesignEditError(f"renderer /build HTTP failure: {e}") from e
        if not body.get("ok"):
            log_tail = (body.get("log") or "")[-2000:]
            raise DesignEditError(
                f"vite build failed (stage={body.get('stage')}): {log_tail}",
            )
    except Exception:
        try:
            if written.version_dir.exists():
                shutil.rmtree(written.version_dir)
                logger.warning(
                    "design_edit_rollback_fs site_id=%s version=%d dir=%s",
                    site_id, written.version_num, written.version_dir,
                )
        except OSError as cleanup_err:
            logger.error(
                "design_edit_rollback_failed site_id=%s err=%s",
                site_id, cleanup_err,
            )
        raise

    asset_hashes: dict[str, str] = {}
    manifest_path = written.version_dir / "dist/client/.vite/manifest.json"
    if manifest_path.is_file():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            entry = data.get("index.html") or next(iter(data.values()), {})
            css_file = next(iter(entry.get("css") or []), None)
            js_file = entry.get("file")
            if css_file:
                asset_hashes["css"] = Path(css_file).stem
            if js_file:
                asset_hashes["js"] = Path(js_file).stem
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                "design_edit_manifest_parse_failed site_id=%s err=%s",
                site_id, e,
            )

    written.db_row.manifest_json = {
        "asset_hashes": asset_hashes,
        "stack": "react",
        "edit_comment": final_comment[:200],
    }
    session.flush()

    published = storage.switch_current(site_id, written.version_num)
    logger.info(
        "design_edit_done site_id=%s version=%d files_changed=%d duration=%.1fs",
        site_id, written.version_num, len(result.files_changed),
        result.duration_seconds,
    )
    return {
        "version_num": written.version_num,
        "version_id": published.id,
        "files_changed": [e.path for e in result.files_changed],
        "claude_summary": result.summary,
        "duration_seconds": result.duration_seconds,
    }
