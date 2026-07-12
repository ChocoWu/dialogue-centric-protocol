"""Model Provider layer (D7/D8): the provider-neutral interface + OpenAI/Anthropic/Mock impls."""

from __future__ import annotations

from .anthropic_provider import AnthropicProvider
from .base import ModelProvider
from .factory import (
    SUPPORTED_PROVIDERS,
    available_providers,
    build_provider,
    orchestrator_binding,
)
from .local_provider import LocalProvider
from .mock import MockProvider
from .openai_provider import OpenAIProvider
from .transformers_provider import TransformersProvider

__all__ = [
    "ModelProvider",
    "MockProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "LocalProvider",
    "TransformersProvider",
    "build_provider",
    "orchestrator_binding",
    "available_providers",
    "SUPPORTED_PROVIDERS",
]
