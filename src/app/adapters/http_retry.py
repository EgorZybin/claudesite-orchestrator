from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx

T = TypeVar("T")


def request_with_retries(
    fn: Callable[[], T],
    *,
    max_attempts: int,
    base_delay_s: float = 0.5,
    retry_on: tuple[type[BaseException], ...] = (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError),
    dlq_context: dict[str, Any] | None = None,
) -> T:
    """Выполнить ``fn`` (обычно ``lambda: client.post(...)``). Повторяет при временных ошибках и 429/503."""
    attempt = 0
    last: BaseException | None = None
    while attempt < max_attempts:
        attempt += 1
        try:
            return fn()
        except retry_on as e:
            last = e
            if attempt >= max_attempts:
                break
            if isinstance(e, httpx.HTTPStatusError):
                code = e.response.status_code
                if code not in (429, 502, 503, 504):
                    raise
            delay = base_delay_s * (2 ** (attempt - 1))
            delay *= 0.8 + 0.4 * random.random()
            time.sleep(delay)
    assert last is not None
    from app.core.dlq import append_adapter_dlq

    append_adapter_dlq(
        {
            "kind": "http_retry_exhausted",
            "error": repr(last),
            "attempts": max_attempts,
            **(dlq_context or {}),
        },
    )
    raise last
