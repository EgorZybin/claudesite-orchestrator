from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from app.adapters.errors import AdapterConfigurationError, HttpAdapterError
from app.adapters.http_retry import request_with_retries
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class OpenAIVisionAdapter:
    """OpenAI-совместимый chat/completions с image attachment.

    Использует тот же endpoint, что и ``OpenAITextAdapter``, но шлёт
    ``messages[].content`` массивом из ``{type:"text"}`` + ``{type:"image_url"}``.
    Модель — ``llm_openai_vision_model`` (default ``gpt-4o-mini``).
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._s = settings or get_settings()

    def generate_from_image(
        self,
        *,
        prompt: str,
        image_bytes: bytes,
        system: str | None = None,
        mime_type: str = "image/png",
    ) -> str:
        key = (self._s.openai_api_key or "").strip()
        if not key:
            raise AdapterConfigurationError(
                "OPENAI_API_KEY is not set (required for OpenAI vision adapter)",
            )
        if not image_bytes:
            raise ValueError("image_bytes is empty")

        url = f"{self._s.openai_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        messages: list[dict[str, Any]] = []
        if system and system.strip():
            messages.append({"role": "system", "content": system.strip()})
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        )
        body: dict[str, Any] = {
            "model": self._s.llm_openai_vision_model,
            "messages": messages,
        }

        def do_req() -> httpx.Response:
            with httpx.Client(timeout=self._s.llm_openai_timeout_seconds) as client:
                r = client.post(url, json=body, headers=headers)
                r.raise_for_status()
                return r

        try:
            resp = request_with_retries(
                do_req,
                max_attempts=self._s.adapter_http_max_retries,
                dlq_context={
                    "adapter": "openai_vision",
                    "model": self._s.llm_openai_vision_model,
                },
            )
        except httpx.HTTPStatusError as e:
            snippet = (e.response.text or "")[:400]
            raise HttpAdapterError(
                f"OpenAI vision HTTP {e.response.status_code}",
                status_code=e.response.status_code,
                body_snippet=snippet,
            ) from e
        except httpx.HTTPError as e:
            raise HttpAdapterError(f"OpenAI vision request failed: {e}") from e

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise HttpAdapterError(
                "OpenAI vision: missing choices",
                body_snippet=str(resp.text)[:400],
            )
        message = choices[0].get("message") or {}
        content = message.get("content")

        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            merged = "\n".join(p.strip() for p in parts if p.strip()).strip()
            if merged:
                return merged

        raise HttpAdapterError(
            "OpenAI vision: empty response content",
            body_snippet=str(resp.text)[:400],
        )
