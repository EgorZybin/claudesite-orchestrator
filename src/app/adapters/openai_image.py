from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from app.adapters.errors import AdapterConfigurationError, HttpAdapterError
from app.adapters.http_retry import request_with_retries
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class OpenAIImageAdapter:
    def __init__(
        self,
        *,
        model: str,
        size: str,
        settings: Settings | None = None,
    ) -> None:
        self._model = model
        self._size = size
        self._s = settings or get_settings()

    def generate(self, *, prompt: str) -> bytes:
        key = self._s.openai_api_key
        if not key:
            raise AdapterConfigurationError("OPENAI_API_KEY is not set (required for OpenAI images)")
        url = f"{self._s.openai_base_url.rstrip('/')}/images/generations"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        body: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "n": 1,
            "size": self._size,
            "response_format": "b64_json",
        }

        def do_req() -> httpx.Response:
            with httpx.Client(timeout=self._s.openai_image_timeout_seconds) as client:
                r = client.post(url, json=body, headers=headers)
                r.raise_for_status()
                return r

        try:
            resp = request_with_retries(
                do_req,
                max_attempts=self._s.adapter_http_max_retries,
                dlq_context={"adapter": "openai_image"},
            )
        except httpx.HTTPStatusError as e:
            snippet = (e.response.text or "")[:400]
            raise HttpAdapterError(
                f"OpenAI images HTTP {e.response.status_code}",
                status_code=e.response.status_code,
                body_snippet=snippet,
            ) from e
        except httpx.HTTPError as e:
            raise HttpAdapterError(f"OpenAI images request failed: {e}") from e

        data = resp.json().get("data") or []
        if not data or "b64_json" not in data[0]:
            raise HttpAdapterError("OpenAI images: missing data[0].b64_json", body_snippet=str(resp.text)[:400])
        try:
            return base64.b64decode(data[0]["b64_json"])
        except Exception as e:
            raise HttpAdapterError(f"OpenAI images: invalid base64 payload: {e}") from e
