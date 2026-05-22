from __future__ import annotations

import logging
from pathlib import Path

from app.adapters.errors import AdapterError
from app.adapters.protocols import TextHumanizer, LLMProvider
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_SKILL_PATH = Path(__file__).resolve().parent / "_humanizer_ru_skill.md"


def _load_skill() -> str:
    try:
        return _SKILL_PATH.read_text(encoding="utf-8")
    except OSError as e:
        raise AdapterError(f"humanizer_ru skill file not found: {e}") from e


_TAIL_INSTRUCTION = (
    "\n\n---\n\n"
    "Текст для переписывания (между тегами <input>):\n"
    "<input>\n"
    "{text}\n"
    "</input>\n\n"
    "Жёсткие требования к ответу:\n"
    "- Верни ТОЛЬКО переписанный текст. Никаких диагностик, списков изменений,\n"
    "  оценок «что было / что стало», преамбул, эпилогов.\n"
    "- Сохрани markdown-разметку 1-в-1: заголовки `## ...`, списки, ссылки,\n"
    "  кодовые блоки. Не оборачивай ответ в ```...```.\n"
    "- Сохрани все цифры, названия инструментов/брендов/платформ, ссылки\n"
    "  как есть. Меняй только формулировки и стиль.\n"
    "- Длину итогового текста сохрани в пределах ±20% от исходной.\n"
)


class HumanizerRuAdapter(TextHumanizer):
    """Стандартный ``TextHumanizer.humanize(text)`` поверх внутреннего LLM."""

    def __init__(self, llm: LLMProvider, settings: Settings | None = None) -> None:
        self._llm = llm
        self._s = settings or get_settings()
        self._skill = _load_skill()

    def humanize(self, *, text: str) -> str:
        clean = (text or "").strip()
        if not clean:
            return text
        prompt = self._skill + _TAIL_INSTRUCTION.format(text=clean)
        try:
            out = self._llm.generate(prompt=prompt)
        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError(f"humanizer_ru LLM call failed: {e}") from e
        result = (out or "").strip()
        if not result:
            raise AdapterError("humanizer_ru returned empty text")
        if result.startswith("```"):
            lines = result.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            result = "\n".join(lines).strip()
        return result
