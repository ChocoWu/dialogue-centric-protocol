"""Provider selection (D7/D8): build a bound :class:`ModelProvider` from a :class:`ModelBinding`.

Called **per binding** (never a global): the orchestrator builds one from the env default, and each
agent participant builds one from its own ``model_binding`` — so a dialogue may mix providers.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterable, Mapping
from importlib.metadata import EntryPoint

from ..config import Config
from ..errors import ProviderError
from ..schema import ModelBinding, ProviderInfo
from .base import ModelProvider
from .mock import MockProvider

#: Built-in providers this SDK can construct (SPEC §1.11 advertisement source). Third-party
#: providers plug in by name via the ``dcp.providers`` entry point (see ``dcp.plugins``).
SUPPORTED_PROVIDERS: tuple[str, ...] = ("openai", "anthropic", "local", "transformers", "mock")


def available_providers(
    env: Mapping[str, str] | None = None,
    *,
    plugin_source: Iterable[EntryPoint] | None = None,
) -> list[ProviderInfo]:
    """Advertise buildable providers + whether each is usable (SPEC §1.11; no keys shown).

    Lists the built-ins, then any installed third-party provider plugins (``dcp.providers``) — those
    are usable by virtue of being installed. ``plugin_source`` is injectable for tests.
    """
    e = os.environ if env is None else env
    infos: list[ProviderInfo] = []
    for provider in SUPPORTED_PROVIDERS:
        if provider == "mock":
            configured = True
        elif provider == "local":                        # usable iff an endpoint is configured
            configured = bool(e.get("DCP_BASE_URL"))
        elif provider == "transformers":                 # usable iff the extra is installed
            configured = importlib.util.find_spec("transformers") is not None
        else:
            configured = Config.api_key_for(provider, env) is not None
        infos.append(ProviderInfo(provider=provider, configured=configured))

    from ..plugins import GROUP_PROVIDERS, list_plugins  # lazy: avoid import cycle at module load

    for plugin in list_plugins(GROUP_PROVIDERS, source=plugin_source):
        if plugin.name not in SUPPORTED_PROVIDERS:        # a built-in name never shadows
            infos.append(ProviderInfo(provider=plugin.name, configured=True))
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
    if provider == "local":
        from .local_provider import LocalProvider

        if not binding.base_url:
            raise ProviderError(
                "local provider needs an endpoint; set DCP_BASE_URL (or ModelBinding.base_url)"
            )
        return LocalProvider(binding.model, base_url=binding.base_url,
                             api_key=api_key or Config.api_key_for("local"))
    if provider == "transformers":
        from .transformers_provider import TransformersProvider

        return TransformersProvider(binding.model)   # in-process HF model (Qwen3 default); no key
    return _build_plugin_provider(provider, binding.model)   # a shared, third-party agent (by name)


def _build_plugin_provider(provider: str, model: str) -> ModelProvider:
    """Resolve a third-party provider registered under the ``dcp.providers`` entry point.

    The target may be a ``ModelProvider`` class/factory (called with the bound model) or a ready
    instance. Not found (or fails to load) → the factory's :class:`ProviderError`.
    """
    from ..errors import PluginError
    from ..plugins import load_model_provider

    try:
        target = load_model_provider(provider)
    except PluginError as exc:
        raise ProviderError(f"unknown model provider {provider!r} (no built-in/plugin)") from exc
    built = target(model) if callable(target) else target    # class/factory → construct; else use
    has_text = callable(getattr(built, "text", None))
    has_structured = callable(getattr(built, "structured", None))
    if not (has_text and has_structured):
        raise ProviderError(f"provider plugin {provider!r} did not resolve to a ModelProvider")
    return built  # type: ignore[no-any-return]


def orchestrator_binding(config: Config) -> ModelBinding:
    """The orchestrator's instance/server-default binding (D8), from env config.

    Requires ``DCP_MODEL`` for real providers (no model id is guessed). ``mock`` needs no model.
    """
    if config.model_provider != "mock" and config.model is None:
        raise ProviderError(
            f"DCP_MODEL is not set for provider {config.model_provider!r}; "
            "set it in the environment (or .env)"
        )
    return ModelBinding(provider=config.model_provider, model=config.model or "mock",
                        base_url=config.base_url)


__all__ = [
    "build_provider",
    "orchestrator_binding",
    "available_providers",
    "SUPPORTED_PROVIDERS",
]
