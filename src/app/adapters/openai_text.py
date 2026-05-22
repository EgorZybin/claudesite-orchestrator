from __future__ import annotations

from typing import Any

import httpx

from app.adapters.errors import AdapterConfigurationError, HttpAdapterError
from app.adapters.http_retry import request_with_retries
from app.adapters.protocols import LLMProvider
from app.core.config import Settings, get_settings


class OpenAITextAdapter(LLMProvider):
    """Адаптер LLM через OpenAI-совместимый endpoint `chat/completions` (VSELLM)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._s = settings or get_settings()

    def generate(self, *, prompt: str, system: str | None = None) -> str:
        key = (self._s.openai_api_key or "").strip()
        if not key:
            raise AdapterConfigurationError("OPENAI_API_KEY is not set (required for OpenAI text adapter)")

        url = f"{self._s.openai_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        messages: list[dict[str, str]] = []
        if system and system.strip():
            messages.append({"role": "system", "content": system.strip()})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": self._s.llm_openai_model,
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
                dlq_context={"adapter": "openai_text", "model": self._s.llm_openai_model},
            )
        except httpx.HTTPStatusError as e:
            snippet = (e.response.text or "")[:400]
            raise HttpAdapterError(
                f"OpenAI text HTTP {e.response.status_code}",
                status_code=e.response.status_code,
                body_snippet=snippet,
            ) from e
        except httpx.HTTPError as e:
            raise HttpAdapterError(f"OpenAI text request failed: {e}") from e

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise HttpAdapterError("OpenAI text: missing choices", body_snippet=str(resp.text)[:400])
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

        raise HttpAdapterError("OpenAI text: empty response content", body_snippet=str(resp.text)[:400])

