from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.adapters.errors import AdapterConfigurationError, ClaudeCliError
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class ProjectFile(BaseModel):
    """One file produced by Claude in the EU workspace."""
    path: str                                   # workspace-relative, POSIX
    content: str                                # UTF-8 text


class ProjectBuildResult(BaseModel):
    success: bool
    files: list[ProjectFile] = Field(default_factory=list)
    claude_summary: str | None = None           # final stdout from claude
    duration_seconds: float = 0.0
    error: str | None = None


class ProjectEditResult(BaseModel):
    success: bool
    files_changed: list[ProjectFile] = Field(default_factory=list)
    summary: str | None = None
    duration_seconds: float = 0.0
    error: str | None = None


class RemoteClaudeProjectAdapter:
    """RU → EU gateway client for project-mode Claude CLI invocations."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._s = settings or get_settings()
        if not self._s.claude_gateway_url:
            raise AdapterConfigurationError("CLAUDE_GATEWAY_URL is not set")
        if not self._s.claude_gateway_token:
            raise AdapterConfigurationError("CLAUDE_GATEWAY_TOKEN is not set")
        self._base = self._s.claude_gateway_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {self._s.claude_gateway_token}"}
        self._verify: str | bool = self._s.claude_gateway_ca_bundle or True

    def build(
        self,
        *,
        seed_files: dict[str, str],
        prompt: str,
        system: str | None = None,
        expected_outputs: list[str] | None = None,
        tools: list[str] | None = None,
        timeout_seconds: int | None = None,
    ) -> ProjectBuildResult:
        """Build a new site in a fresh EU workspace.

        Args:
            seed_files: files seeded into workspace before Claude starts
                (e.g. {"brief.md": ..., "contract.md": ..., "design.md": ...}).
            prompt: instruction to Claude.
            system: optional system prompt.
            expected_outputs: glob patterns of files to return (default: everything).
            tools: tool allowlist (default: Edit, Write, Read, Grep, Glob).
            timeout_seconds: per-request override of CLAUDE_CLI_TIMEOUT_SECONDS.

        Returns:
            ProjectBuildResult with all files matching expected_outputs.
            Seed files are excluded from result (caller already has them).
        """
        body: dict[str, Any] = {"seed_files": seed_files, "prompt": prompt}
        if system:
            body["system"] = system
        if expected_outputs is not None:
            body["expected_outputs"] = expected_outputs
        if tools is not None:
            body["tools"] = tools
        if timeout_seconds is not None:
            body["timeout_seconds"] = timeout_seconds

        return self._post("/project/build", body, ProjectBuildResult, timeout_seconds)

    def edit(
        self,
        *,
        seed_files: dict[str, str],
        scope: list[str],
        prompt: str,
        system: str | None = None,
        tools: list[str] | None = None,
        timeout_seconds: int | None = None,
    ) -> ProjectEditResult:
        """Edit an existing project — Claude sees seed_files, may modify only
        files matching `scope` glob patterns.

        Out-of-scope modifications cause success=False with an error message.
        """
        body: dict[str, Any] = {
            "seed_files": seed_files,
            "scope": scope,
            "prompt": prompt,
        }
        if system:
            body["system"] = system
        if tools is not None:
            body["tools"] = tools
        if timeout_seconds is not None:
            body["timeout_seconds"] = timeout_seconds

        return self._post("/project/edit", body, ProjectEditResult, timeout_seconds)

    def _post(
        self,
        path: str,
        body: dict[str, Any],
        result_cls: type[BaseModel],
        timeout_seconds: int | None,
    ) -> Any:
        endpoint = f"{self._base}{path}"
        # HTTP timeout = Claude timeout + 30s transit padding (gateway may take a
        # moment to package response after Claude finishes).
        client_timeout = (timeout_seconds or self._s.claude_cli_timeout_seconds) + 30

        try:
            r = httpx.post(
                endpoint,
                headers=self._headers,
                json=body,
                timeout=client_timeout,
                verify=self._verify,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            raise ClaudeCliError(
                f"Gateway {path} unreachable: {type(e).__name__}: {e}",
            ) from e
        except httpx.HTTPError as e:
            raise ClaudeCliError(f"Gateway {path} request failed: {e}") from e

        if r.status_code != 200:
            text = (r.text or "")[:2000]
            raise ClaudeCliError(
                f"Gateway {path} HTTP {r.status_code}: {text[:500]}",
                detail={"status": r.status_code, "body": text, "endpoint": path},
            )

        try:
            data = r.json()
        except ValueError as e:
            raise ClaudeCliError(
                f"Gateway {path} returned non-JSON: {(r.text or '')[:500]}",
            ) from e

        return result_cls(**data)
