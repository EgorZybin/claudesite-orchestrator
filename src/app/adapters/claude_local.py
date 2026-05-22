from __future__ import annotations

import logging
import shlex
import subprocess
import time
from app.adapters.errors import AdapterConfigurationError, ClaudeCliError
from app.adapters.protocols import LLMProvider
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LocalClaudeAdapter(LLMProvider):
    """Вызвать CLI из ``CLAUDE_CLI_ARGV`` (shell-split); промпт передается через stdin."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._s = settings or get_settings()
        parts = shlex.split(self._s.claude_cli_argv, posix=True)
        if not parts:
            raise AdapterConfigurationError("CLAUDE_CLI_ARGV expands to an empty argv")
        self._argv0 = parts

    def generate(self, *, prompt: str, system: str | None = None) -> str:
        body = prompt if not system else f"{system.strip()}\n\n{prompt.strip()}"
        for attempt in range(1, self._s.claude_cli_max_retries + 1):
            try:
                return self._run_once(body)
            except subprocess.TimeoutExpired as e:
                logger.warning("claude_cli_timeout attempt=%s/%s", attempt, self._s.claude_cli_max_retries)
                if attempt >= self._s.claude_cli_max_retries:
                    raise ClaudeCliError(
                        f"Claude CLI timed out after {self._s.claude_cli_timeout_seconds}s",
                    ) from e
                time.sleep(min(2**attempt, 30))
            except ClaudeCliError:
                raise

    def _run_once(self, stdin_text: str) -> str:
        try:
            proc = subprocess.run(
                self._argv0,
                input=stdin_text,
                capture_output=True,
                text=True,
                timeout=self._s.claude_cli_timeout_seconds,
                check=False,
                env=None,
            )
        except OSError as e:
            raise ClaudeCliError(f"failed to spawn Claude CLI: {e}") from e

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise ClaudeCliError(
                f"Claude CLI exit {proc.returncode}: {err[:2000]}",
                detail={"returncode": proc.returncode, "stderr": proc.stderr},
            )

        out = (proc.stdout or "").strip()
        if not out:
            raise ClaudeCliError("Claude CLI produced empty stdout")
        return out
