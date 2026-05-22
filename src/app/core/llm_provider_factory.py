from __future__ import annotations

from app.adapters.errors import AdapterConfigurationError
from app.adapters.claude_local import LocalClaudeAdapter
from app.adapters.claude_remote import RemoteClaudeAdapter
from app.adapters.openai_text import OpenAITextAdapter
from app.adapters.protocols import LLMProvider
from app.adapters.refusal_guard import RefusalGuardedLLM


def make_text_llm(settings) -> LLMProvider:
    p = (settings.llm_provider or "claude_local").strip().lower()
    inner: LLMProvider
    if p == "claude_local":
        inner = LocalClaudeAdapter(settings=settings)
    elif p == "claude_remote":
        inner = RemoteClaudeAdapter(settings=settings)
    elif p == "openai":
        inner = OpenAITextAdapter(settings=settings)
    else:
        raise AdapterConfigurationError(f"Unsupported LLM_PROVIDER={settings.llm_provider!r}")
    return RefusalGuardedLLM(inner)
