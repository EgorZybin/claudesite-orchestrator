from __future__ import annotations

import logging

from app.adapters.errors import LlmRefusalError
from app.adapters.protocols import LLMProvider
from app.adapters.refusal_detection import detect_refusal

logger = logging.getLogger(__name__)


class RefusalGuardedLLM(LLMProvider):
    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner

    def generate(self, *, prompt: str, system: str | None = None) -> str:
        text = self._inner.generate(prompt=prompt, system=system)
        matched = detect_refusal(text)
        if matched:
            head = text[:300].replace("\n", " ")
            logger.warning("llm_refusal_detected matched=%r head=%r", matched, head)
            raise LlmRefusalError(
                f"LLM refused to generate content (matched: {matched!r})",
                detail={"matched_pattern": matched, "head": text[:500]},
            )
        return text
