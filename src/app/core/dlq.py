from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def append_adapter_dlq(event: dict[str, Any]) -> None:
    """Если в настройках задан ``adapter_dlq_path``, дописать одну JSON-строку."""
    from app.core.config import get_settings

    path_str = get_settings().adapter_dlq_path
    if not path_str:
        return
    path = Path(path_str).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": datetime.now(UTC).isoformat(), **event}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.error("adapter_dlq write failed: %s", e)
