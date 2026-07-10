"""Provider selection (D7/D8): build a bound :class:`ModelProvider` from a :class:`ModelBinding`.

Called **per binding** (never a global): the orchestrator builds one from the env default, and each
agent participant builds one from its own ``model_binding`` — so a dialogue may mix providers.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..config import Config
from ..errors import ProviderError
from ..schema import ModelBinding, ProviderInfo
from .base import ModelProvider
from .mock import MockProvider

#: Providers this SDK can construct (SPEC §1.11 advertisement source).
SUPPORTED_PROVIDERS: tuple[str, ...] = ("openai", "anthropic", "mock")


def available_providers(env: Mapping[str, str] | None = None) -> list[ProviderInfo]:
    """Advertise buildable providers + whether each has a credential (SPEC §1.11; no keys shown)."""
    infos: list[ProviderInfo] = []
    for provider in SUPPORTED_PROVIDERS:
        configured = provider == "mock" or Config.api_key_for(provider, env) is not None
        infos.append(ProviderInfo(provider=provider, configured=configured))
    return infos


def build_provider(binding: ModelBinding, *, api_key: str | None = None) -> ModelProvider:
    """Construct the provider for ``binding``. Keys resolve from env by provider unless passed."""
    provider = binding.provider
    if provider == "mock":
        return MockProvider()
    if provider == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider(binding.model, api_key=api_key or Config.api_key_for("openai"))
    if provider == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(binding.model, api_key=api_key or Config.api_key_for("anthropic"))
    raise ProviderError(f"unknown model provider {provider!r}")


def orchestrator_binding(config: Config) -> ModelBinding:
    """The orchestrator's instance/server-default binding (D8), from env config.

    Requires ``DCP_MODEL`` for real providers (no model id is guessed). ``mock`` needs no model.
    """
    if config.model_provider != "mock" and config.model is None:
        raise ProviderError(
            f"DCP_MODEL is not set for provider {config.model_provider!r}; "
            "set it in the environment (or .env)"
        )
    return ModelBinding(provider=config.model_provider, model=config.model or "mock")


__all__ = [
    "build_provider",
    "orchestrator_binding",
    "available_providers",
    "SUPPORTED_PROVIDERS",
]
