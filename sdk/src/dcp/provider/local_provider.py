"""Local / self-hosted models via an OpenAI-compatible endpoint (Phase 6.3a).

Most local runtimes — **vLLM**, **Ollama**, **LM Studio**, **TGI**, **llama.cpp server** — expose an
OpenAI-compatible HTTP API, so DCP reaches them by pointing the OpenAI SDK at a ``base_url``. No
frontier key required (local servers usually ignore the key; a placeholder is sent). Set the
endpoint with ``DCP_BASE_URL`` (e.g. ``http://localhost:11434/v1`` for Ollama, or
``http://localhost:8000/v1`` for vLLM) and select it with ``DCP_MODEL_PROVIDER=local``.
"""

from __future__ import annotations

from typing import Any

from .openai_provider import OpenAIProvider


class LocalProvider(OpenAIProvider):
    """An OpenAI-compatible provider for a local/self-hosted model server (via ``base_url``)."""

    def __init__(
        self, model: str, *, base_url: str, api_key: str | None = None, client: Any | None = None
    ) -> None:
        # local servers require *a* key on the SDK but usually ignore its value
        super().__init__(model, api_key=api_key or "local", base_url=base_url, client=client)


__all__ = ["LocalProvider"]
