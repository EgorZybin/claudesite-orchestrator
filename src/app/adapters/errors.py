from __future__ import annotations

from typing import Any

from app.core.exceptions import OrchestratorError


class AdapterError(OrchestratorError):
    """Сбой внешнего инструмента, HTTP или subprocess-адаптера."""

    def __init__(self, message: str, *, detail: Any | None = None) -> None:
        super().__init__(message)
        self.detail = detail


class AdapterConfigurationError(AdapterError):
    """Отсутствует URL/API-ключ или некорректны настройки."""


class ClaudeCliError(AdapterError):
    """Локальный Claude CLI завершился с ошибкой или не вернул вывод."""


class LlmRefusalError(AdapterError):
    """LLM вернула отказ ("я не буду…", "As an AI…") вместо запрошенного контента."""


class SmtpEmailError(AdapterError):
    """SMTP не настроен, недоступен, или отверг сообщение."""


class HttpAdapterError(AdapterError):
    """HTTP 4xx/5xx или нечитаемый ответ."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body_snippet: str | None = None,
    ) -> None:
        super().__init__(message, detail={"status_code": status_code, "body_snippet": body_snippet})
        self.status_code = status_code
        self.body_snippet = body_snippet
