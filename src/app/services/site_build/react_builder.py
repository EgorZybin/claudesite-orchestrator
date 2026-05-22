from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.adapters.claude_project import ProjectBuildResult, RemoteClaudeProjectAdapter
from app.core.config import get_settings
from app.db.models.site_version import SiteVersion
from app.schemas.site_content import SiteContent
from app.services.site_build.brief_builder import build_brief
from app.services.site_build.storage import FilesystemSiteStorage

logger = logging.getLogger(__name__)

_PKG_DIR = Path(__file__).parent
_SEED_DIR = (_PKG_DIR.parent.parent.parent.parent / "react-seed").resolve()
_CONTRACTS_DIR = _PKG_DIR / "contracts"


class ReactBuilderError(Exception):
    """Anything that prevents publishing a React build (Claude fail, vite
    fail, missing seed, renderer service down)."""


_BUILD_PROMPT = (
    "You are in a fresh React + Vite + Tailwind + shadcn site project "
    "workspace. Read all of these in FULL before writing any TSX:\n\n"
    "  1. brief.md — what to build (content, audience, tone). If brief has "
    "a 'MANDATORY design tokens' section, those tokens OVERRIDE everything "
    "in design.md / frontend-design.md when they conflict. Use the exact "
    "HSL values and font names from the tokens block in src/theme.css.\n"
    "  2. contracts/contract.md — file layout, immutable vs required, "
    "props shape, validation rules.\n"
    "  3. contracts/design.md — Tailwind tokens, hero patterns per "
    "page_type, mobile rules.\n"
    "  4. contracts/frontend-design.md — aesthetic culture (bold, "
    "anti-generic).\n"
    "  5. contracts/shadcn-skill/SKILL.md + rules/* — composition "
    "patterns, styling conventions.\n"
    "  6. contracts/examples/INDEX.md and the *.tsx files there — "
    "production-grade section exemplars. STUDY their structure: asymmetric "
    "grids, off-axis rotations, type contrast, decorative offsets, "
    "micro-trust strips. ADAPT these patterns to your brief; DO NOT "
    "copy verbatim and DO NOT import from contracts/examples (they're "
    "not in the build path).\n\n"
    "Then walk `src/` to see what's already shipped (immutable seed "
    "files: ui/button.tsx, ui/card.tsx, ui/accordion.tsx, types.ts, "
    "lib/*, entry-server.tsx, main.tsx, index.css).\n\n"
    "Then build the site by creating:\n"
    "  - src/App.tsx (REQUIRED — dispatches by page.page_type)\n"
    "  - src/theme.css (REQUIRED — palette + fonts via :root CSS vars; "
    "import from src/index.css)\n"
    "  - src/components/Layout.tsx, Header.tsx, Footer.tsx\n"
    "  - src/pages/<PageType>Page.tsx for EACH page_type used by the site "
    "(see brief.md page list)\n"
    "  - src/components/sections/*.tsx — bespoke composables, AT THE "
    "QUALITY BAR demonstrated in contracts/examples/. Asymmetry, type "
    "contrast, intentional decorative elements — not uniform 3-col grids.\n\n"
    "DO NOT add new npm dependencies (renderer container has fixed deps). "
    "DO NOT modify the immutable seed files. After writing all files, end "
    "with a 2-3 sentence summary: aesthetic direction you committed to, "
    "one concrete non-default choice (font/palette/layout), and which "
    "page_types got dedicated components."
)


_BUILD_SYSTEM = (
    "You are an experienced web developer building a static-output "
    "React+Vite+Tailwind+shadcn site. Use Edit/Write/Read tools. "
    "Don't write outside the workspace. Don't make external network "
    "requests. Don't add npm dependencies (`package.json` is frozen). "
    "Don't run the shadcn CLI (not available — write components inline "
    "instead). Follow the contracts EXACTLY."
)


def _load_seed_files() -> dict[str, str]:
    """Read react-seed/ tree, return {workspace-relative path: content}.

    Files are presented to Claude AT THE WORKSPACE ROOT — package.json
    lives at `package.json`, src/types.ts at `src/types.ts`, etc.
    """
    if not _SEED_DIR.is_dir():
        raise ReactBuilderError(
            f"react-seed dir missing at {_SEED_DIR} (orchestrator package broken)",
        )
    out: dict[str, str] = {}
    for path in sorted(_SEED_DIR.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(_SEED_DIR).as_posix()
        if rel.startswith(("node_modules/", "dist/", ".git/")):
            continue
        try:
            out[rel] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning("seed_skip_binary path=%s", rel)
    return out


def _load_contracts() -> dict[str, str]:
    """React-stack contracts + the frontend-design skill + shadcn-skill."""
    files: dict[str, str] = {}
    for sub in ("react/contract.md", "react/design.md", "frontend-design.md"):
        p = _CONTRACTS_DIR / sub
        if not p.is_file():
            raise ReactBuilderError(f"contract file missing: {p}")
        key = "contracts/" + sub.replace("react/", "", 1)
        files[key] = p.read_text(encoding="utf-8")

    skill_dir = _CONTRACTS_DIR / "shadcn-skill"
    if skill_dir.is_dir():
        for p in sorted(skill_dir.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in {".md"}:
                continue
            rel = p.relative_to(skill_dir).as_posix()
            files[f"contracts/shadcn-skill/{rel}"] = p.read_text(encoding="utf-8")

    examples_dir = _CONTRACTS_DIR / "examples"
    if examples_dir.is_dir():
        for p in sorted(examples_dir.iterdir()):
            if not p.is_file() or p.suffix.lower() not in {".tsx", ".md"}:
                continue
            files[f"contracts/examples/{p.name}"] = p.read_text(encoding="utf-8")
    return files


def build_initial_site(
    session: Session,
    *,
    site_id: int,
    site_content: SiteContent,
    accent_hsl: str | None = None,
    neutral_family: str | None = None,
    display_font: str | None = None,
    body_font: str | None = None,
    extra_notes: str | None = None,
    timeout_seconds: int = 1500,
    comment: str | None = None,
    publish: bool = True,
    design_tokens: dict | None = None,
) -> SiteVersion:
    """Build a fresh React site: seed → Claude → vite build → publish.

    Mirrors `generator.generate_initial_site` API so the caller in
    `workers/tasks.py` can swap one for the other without changing
    surrounding code.
    """
    settings = get_settings()
    page_types = sorted({p.page_type for p in site_content.pages})
    logger.info(
        "react_builder_start site_id=%s pages=%d page_types=%s",
        site_id, len(site_content.pages), page_types,
    )

    brief_md = build_brief(
        site_content,
        accent_hsl=accent_hsl,
        neutral_family=neutral_family,
        display_font=display_font,
        body_font=body_font,
        extra_notes=extra_notes,
        design_tokens=design_tokens,
    )
    seed_files = _load_seed_files()
    seed_files.update(_load_contracts())
    seed_files["brief.md"] = brief_md
    logger.info(
        "react_builder_seeds site_id=%s files=%d has_tokens=%s",
        site_id, len(seed_files), bool(design_tokens),
    )

    adapter = RemoteClaudeProjectAdapter()
    result: ProjectBuildResult = adapter.build(
        seed_files=seed_files,
        prompt=_BUILD_PROMPT,
        system=_BUILD_SYSTEM,
        expected_outputs=[
            "src/**/*.tsx",
            "src/**/*.ts",
            "src/**/*.css",
            "package.json",
        ],
        tools=["Edit", "Write", "Read", "Grep", "Glob"],
        timeout_seconds=timeout_seconds,
    )
    if not result.success:
        raise ReactBuilderError(
            f"Claude build failed: {result.error} "
            f"(duration={result.duration_seconds:.1f}s)",
        )
    if not result.files:
        raise ReactBuilderError(
            "Claude returned success=True but files=[] — Claude wrote nothing. "
            f"Summary: {result.claude_summary!r}",
        )
    logger.info(
        "react_builder_claude_done site_id=%s files_changed=%d duration=%.1fs",
        site_id, len(result.files), result.duration_seconds,
    )

    merged: dict[str, str] = dict(seed_files)
    for k in list(merged):
        if k.startswith("contracts/") or k == "brief.md":
            del merged[k]
    for f in result.files:
        merged[f.path] = f.content

    missing = [
        p for p in ("src/App.tsx", "src/theme.css")
        if p not in merged
    ]
    if missing:
        raise ReactBuilderError(
            f"Claude skipped required files: {missing}. "
            f"Summary: {result.claude_summary!r}",
        )

    storage = FilesystemSiteStorage(session)
    final_comment = comment or f"initial react build — {len(site_content.pages)} pages"
    written = storage.write_version(
        site_id,
        merged,
        comment=final_comment,
        manifest={},
    )
    site_dir = str(written.version_dir.resolve())
    logger.info(
        "react_builder_persisted site_id=%s version=%d files=%d site_dir=%s",
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
            raise ReactBuilderError(
                f"renderer /build HTTP failure: {e}",
            ) from e
        if not body.get("ok"):
            log_tail = (body.get("log") or "")[-2000:]
            raise ReactBuilderError(
                f"vite build failed (stage={body.get('stage')}): "
                f"{log_tail}",
            )
    except Exception:
        import shutil
        try:
            if written.version_dir.exists():
                shutil.rmtree(written.version_dir)
                logger.warning(
                    "react_builder_rollback_fs site_id=%s version=%d dir=%s",
                    site_id, written.version_num, written.version_dir,
                )
        except OSError as cleanup_err:
            logger.error(
                "react_builder_rollback_failed site_id=%s err=%s",
                site_id, cleanup_err,
            )
        raise
    logger.info(
        "react_builder_vite_done site_id=%s version=%d duration_ms=%s",
        site_id, written.version_num, body.get("duration_ms"),
    )

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
                "react_builder_manifest_parse_failed site_id=%s err=%s",
                site_id, e,
            )

    written.db_row.manifest_json = {
        "page_types": page_types,
        "asset_hashes": asset_hashes,
        "stack": "react",
        "renderer_version": body.get("version"),
    }
    session.flush()

    if publish:
        published = storage.switch_current(site_id, written.version_num)
        logger.info(
            "react_builder_published site_id=%s version=%d",
            site_id, written.version_num,
        )
        return published

    logger.info(
        "react_builder_draft site_id=%s version=%d",
        site_id, written.version_num,
    )
    return written.db_row
