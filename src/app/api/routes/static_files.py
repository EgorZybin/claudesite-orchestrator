from __future__ import annotations

import mimetypes
from pathlib import Path

mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

router = APIRouter(prefix="/static", tags=["static"])

_STATIC_ROOT = Path("/app/static").resolve()
_ALLOWED_EXT = {
    ".woff2", ".woff", ".css", ".js",
    ".png", ".jpg", ".jpeg", ".svg", ".webp", ".ico", ".gif",
    ".txt",
}


@router.get("/{rel_path:path}")
def serve_static(rel_path: str) -> Response:
    if not rel_path or rel_path.startswith("/") or ".." in rel_path.split("/"):
        raise HTTPException(status_code=400, detail="invalid path")
    target = (_STATIC_ROOT / rel_path).resolve()
    try:
        target.relative_to(_STATIC_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path escapes static root") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    if target.suffix.lower() not in _ALLOWED_EXT:
        raise HTTPException(status_code=403, detail="extension not allowed")

    content_type, _ = mimetypes.guess_type(target.name)
    return FileResponse(
        path=str(target),
        media_type=content_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
