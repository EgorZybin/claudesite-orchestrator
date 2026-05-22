from fastapi import APIRouter
from app.core.config import get_settings

router = APIRouter()


@router.get("/health", tags=["monitoring"])
def health() -> dict[str, object]:
    s = get_settings()
    return {
        "status": "ok",
        "react_renderer_enabled": bool((s.react_renderer_url or "").strip()),
        "react_renderer_fail_open": s.react_renderer_fail_open,
    }
