from __future__ import annotations

import hashlib
import os
from pathlib import Path


def _compute_version() -> str:
    h = hashlib.sha256()
    h.update(("env=" + os.environ.get("RENDER_VERSION", "1")).encode())
    app_root = Path(__file__).resolve().parent.parent
    for rel in ("custom_render.py", "api/routes/custom_public.py"):
        f = app_root / rel
        if f.is_file():
            h.update(b"|file:" + rel.encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


RENDER_VERSION: str = _compute_version()
