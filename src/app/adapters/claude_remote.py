from __future__ import annotations

import logging
import time

import httpx

from app.adapters.errors import AdapterConfigurationError, ClaudeCliError
from app.adapters.protocols import LLMProvider
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class RemoteClaudeAdapter(LLMProvider):
    """Вызвать Claude CLI на удаленном гейтвее по HTTP.

    Контракт идентичен ``LocalClaudeAdapter``: тот же ``generate(prompt, system) -> str``,
    тот же таймаут (``CLAUDE_CLI_TIMEOUT_SECONDS``), та же логика ретраев на таймауты.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._s = settings or get_settings()
        if not self._s.claude_gateway_url:
            raise AdapterConfigurationError("CLAUDE_GATEWAY_URL is not set")
        if not self._s.claude_gateway_token:
            raise AdapterConfigurationError("CLAUDE_GATEWAY_TOKEN is not set")
        self._endpoint = self._s.claude_gateway_url.rstrip("/") + "/generate"
        self._headers = {"Authorization": f"Bearer {self._s.claude_gateway_token}"}
        self._verify: str | bool = self._s.claude_gateway_ca_bundle or True

    def generate(self, *, prompt: str, system: str | None = None) -> str:
        for attempt in range(1, self._s.claude_cli_max_retries + 1):
            try:
                return self._run_once(prompt=prompt, system=system)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                logger.warning(
                    "claude_gateway_transient attempt=%s/%s err=%s",
                    attempt,
                    self._s.claude_cli_max_retries,
                    type(e).__name__,
                )
                if attempt >= self._s.claude_cli_max_retries:
                    raise ClaudeCliError(
                        f"Claude gateway unreachable after {attempt} attempts: {e}",
                    ) from e
                time.sleep(min(2**attempt, 30))
            except ClaudeCliError:
                raise

    def _run_once(self, *, prompt: str, system: str | None) -> str:
        try:
            r = httpx.post(
                self._endpoint,
                headers=self._headers,
                json={"prompt": prompt, "system": system},
                timeout=self._s.claude_cli_timeout_seconds,
                verify=self._verify,
            )
        except (httpx.TimeoutException, httpx.NetworkError):
            raise
        except httpx.HTTPError as e:
            raise ClaudeCliError(f"Claude gateway request failed: {e}") from e

        if r.status_code != 200:
            body = (r.text or "")[:2000]
            raise ClaudeCliError(
                f"Claude gateway HTTP {r.status_code}: {body[:500]}",
                detail={"status": r.status_code, "body": body},
            )

        try:
            data = r.json()
        except ValueError as e:
            raise ClaudeCliError(
                f"Claude gateway returned non-JSON: {(r.text or '')[:500]}",
            ) from e

        text = (data.get("text") or "").strip()
        if not text:
            raise ClaudeCliError("Claude gateway produced empty text")
        return text
