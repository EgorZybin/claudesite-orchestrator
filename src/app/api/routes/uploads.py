from __future__ import annotations

import mimetypes
from pathlib import Path

mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/avif", ".avif")

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.exceptions import OrchestratorError
from app.core.site_runtime import SiteRuntimeResolver
from app.db.models.enums import SiteMode
from app.api.deps import readonly_session

router = APIRouter(prefix="/uploads", tags=["uploads"])


def _resolve_uploads_root(slug: str, session: Session) -> Path:
    try:
        rt = SiteRuntimeResolver().resolve(session, slug)
    except OrchestratorError as exc:
        raise HTTPException(status_code=404, detail=f"site not found: {slug}") from exc
    base: str | None = None
    if rt.effective_mode == SiteMode.CUSTOM and rt.file.custom and rt.file.custom.uploads_base_path:
        base = rt.file.custom.uploads_base_path
    elif rt.file.wordpress and rt.file.wordpress.uploads_base_path:
        base = rt.file.wordpress.uploads_base_path
    if not base:
        raise HTTPException(status_code=404, detail=f"uploads not configured for site: {slug}")
    return Path(base).expanduser().resolve()


@router.get("/{site_slug}/{rel_path:path}")
def serve_upload(
    site_slug: str,
    rel_path: str,
    request: Request,
    session: Session = Depends(readonly_session),
) -> Response:
    if not rel_path or rel_path.startswith("/") or ".." in rel_path.split("/"):
        raise HTTPException(status_code=400, detail="invalid path")
    root = _resolve_uploads_root(site_slug, session)
    target = (root / rel_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path escapes uploads root") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    content_type, _ = mimetypes.guess_type(target.name)
    headers = {"Cache-Control": "public, max-age=31536000, immutable"}
    return FileResponse(
        path=str(target),
        media_type=content_type or "application/octet-stream",
        headers=headers,
    )
