from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    def generate(self, *, prompt: str, system: str | None = None) -> str:
        """Вернуть текст ответа модели."""


class TextHumanizer(Protocol):
    def humanize(self, *, text: str) -> str:
        """Очеловечивание текста текстов через Smodin."""


class TextQualityGate(Protocol):
    """Зарезервирован для будущего AI-detection gate (Turgenev / GPTZero / ...).

    """

    def analyze(self, *, text: str) -> object:
        ...
