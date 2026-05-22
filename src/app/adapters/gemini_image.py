from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from app.adapters.errors import AdapterConfigurationError, HttpAdapterError
from app.adapters.http_retry import request_with_retries
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _extract_image_bytes(payload: dict[str, Any]) -> bytes:
    for cand in payload.get("candidates") or []:
        content = cand.get("content") or {}
        for part in content.get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if not inline:
                continue
            raw_b64 = inline.get("data") or inline.get("bytesBase64Encoded")
            if raw_b64:
                try:
                    return base64.b64decode(raw_b64)
                except Exception as e:
                    raise HttpAdapterError(f"Gemini: invalid base64 in inlineData: {e}") from e

    raise HttpAdapterError(
        "Gemini: no image bytes in response",
        body_snippet=str(payload)[:700],
    )


class GeminiImageAdapter:
    """Вызывает ``models/{model}:generateContent`` с ``responseModalities``, включающим ``IMAGE``."""

    def __init__(
        self,
        *,
        model: str,
        aspect_ratio: str,
        image_size: str,
        settings: Settings | None = None,
    ) -> None:
        self._model = model
        self._aspect_ratio = aspect_ratio
        self._image_size = image_size
        self._s = settings or get_settings()

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        key = self._s.gemini_api_key
        if not key:
            raise AdapterConfigurationError(
                "GEMINI_API_KEY is not set (required when pipeline.images.provider is gemini)",
            )
        url = f"{self._s.gemini_api_base.rstrip('/')}/models/{self._model}:generateContent"
        headers = {
            "x-goog-api-key": key,
            "Content-Type": "application/json",
        }

        def do_req() -> httpx.Response:
            with httpx.Client(timeout=self._s.gemini_image_timeout_seconds) as client:
                r = client.post(url, json=body, headers=headers)
                r.raise_for_status()
                return r

        try:
            resp = request_with_retries(
                do_req,
                max_attempts=self._s.adapter_http_max_retries,
                dlq_context={"adapter": "gemini_image"},
            )
        except httpx.HTTPStatusError as e:
            snippet = (e.response.text or "")[:600]
            raise HttpAdapterError(
                f"Gemini generateContent HTTP {e.response.status_code}",
                status_code=e.response.status_code,
                body_snippet=snippet,
            ) from e
        except httpx.HTTPError as e:
            raise HttpAdapterError(f"Gemini request failed: {e}") from e

        try:
            return resp.json()
        except Exception as e:
            raise HttpAdapterError(f"Gemini: response not JSON: {e}") from e

    def generate(self, *, prompt: str) -> bytes:
        primary: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {
                    "aspectRatio": self._aspect_ratio,
                    "imageSize": self._image_size,
                },
            },
        }

        data = self._post(primary)
        try:
            return _extract_image_bytes(data)
        except HttpAdapterError as first:
            logger.info("gemini_image_fallback TEXT+IMAGE model=%s", self._model)
            fallback: dict[str, Any] = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseModalities": ["TEXT", "IMAGE"],
                },
            }
            try:
                data2 = self._post(fallback)
                return _extract_image_bytes(data2)
            except HttpAdapterError as second:
                raise second from first
