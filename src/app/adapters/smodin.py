from __future__ import annotations

import logging
from typing import Any

import httpx

from app.adapters.errors import AdapterConfigurationError, HttpAdapterError
from app.adapters.http_retry import request_with_retries
from app.adapters.protocols import TextHumanizer
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _pick_humanized_text(payload: dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return None
    rewrites = payload.get("rewrites")
    if isinstance(rewrites, list):
        parts = [
            r["rewrite"].strip()
            for r in rewrites
            if isinstance(r, dict) and isinstance(r.get("rewrite"), str) and r["rewrite"].strip()
        ]
        if parts:
            return "\n\n".join(parts)
    for key in ("humanized_text", "humanizedText", "text", "result", "output", "content"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    data = payload.get("data")
    if isinstance(data, dict):
        return _pick_humanized_text(data)
    return None


class SmodinAdapter(TextHumanizer):
    def __init__(self, settings: Settings | None = None) -> None:
        self._s = settings or get_settings()

    def humanize(self, *, text: str) -> str:
        if not self._s.smodin_humanize_url:
            raise AdapterConfigurationError("SMODIN_HUMANIZE_URL is not set")
        if not self._s.smodin_api_key:
            raise AdapterConfigurationError("SMODIN_API_KEY is not set")

        headers = {
            "x-api-key": self._s.smodin_api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        body = {
            "text": text,
            "language": self._s.smodin_language,
            "outputLanguage": self._s.smodin_language,
            "strength": self._s.smodin_strength,
        }

        def do_req() -> httpx.Response:
            with httpx.Client(timeout=self._s.smodin_timeout_seconds) as client:
                r = client.post(self._s.smodin_humanize_url, json=body, headers=headers)
                r.raise_for_status()
                return r

        try:
            resp = request_with_retries(
                do_req,
                max_attempts=self._s.adapter_http_max_retries,
                dlq_context={"adapter": "smodin"},
            )
        except httpx.HTTPStatusError as e:
            snippet = (e.response.text or "")[:800]
            raise HttpAdapterError(
                f"Smodin HTTP {e.response.status_code}",
                status_code=e.response.status_code,
                body_snippet=snippet,
            ) from e
        except httpx.RequestError as e:
            raise HttpAdapterError(f"Smodin request failed: {e}") from e

        try:
            payload = resp.json()
        except ValueError as e:
            raise HttpAdapterError("Smodin response is not JSON") from e

        if not isinstance(payload, dict):
            raise HttpAdapterError("Smodin JSON root must be an object")

        out = _pick_humanized_text(payload)
        if not out:
            raise HttpAdapterError(f"Smodin JSON missing humanized text keys: {list(payload.keys())[:20]}")
        return out
