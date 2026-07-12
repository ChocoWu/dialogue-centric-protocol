"""Sharing an agent: third-party ``ModelProvider`` plugins (``dcp.providers`` entry point).

A shared agent is a ``ModelProvider`` packaged by someone else. Once installed it must resolve
**by name** through ``build_provider`` (so a ``ModelBinding(provider="their-name")`` just works) and
be advertised in ``server_info`` — full symmetry with control-policy / oversight / template plugins.

Entry-point ``source`` is injected so the round-trip is proven without installing a package.
"""

from __future__ import annotations

from importlib.metadata import EntryPoint

import pytest
from pydantic import BaseModel

from dcp.errors import PluginError, ProviderError
from dcp.plugins import GROUP_PROVIDERS, available_plugins, load_model_provider, load_plugin
from dcp.provider import available_providers, build_provider
from dcp.schema import ModelBinding


class EchoProvider:
    """A minimal shareable agent: text-only (agents only ever need ``text``)."""

    def __init__(self, model: str = "echo") -> None:
        self.model = model

    async def text(self, *, instructions: str, content: str) -> str:
        return f"[{self.model}] echo"

    async def structured(self, *, instructions: str, content: str, schema: type[BaseModel]):
        raise ProviderError("EchoProvider is text-only")


# `__name__` target survives pytest import mode (module already in sys.modules).
_SOURCE = [EntryPoint("echo", f"{__name__}:EchoProvider", GROUP_PROVIDERS)]


def test_load_model_provider_resolves_by_name() -> None:
    assert load_model_provider("echo", source=_SOURCE) is EchoProvider
    assert load_plugin(GROUP_PROVIDERS, "echo", source=_SOURCE) is EchoProvider


def test_load_model_provider_unknown_raises() -> None:
    with pytest.raises(PluginError):
        load_model_provider("nope", source=_SOURCE)


def test_provider_group_is_advertised() -> None:
    from dcp.plugins import GROUPS, list_plugins

    assert GROUP_PROVIDERS in GROUPS       # a first-class DCP entry-point group
    assert [p.name for p in list_plugins(GROUP_PROVIDERS, source=_SOURCE)] == ["echo"]


def test_build_provider_resolves_a_plugin_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    # build_provider does a lazy `from ..plugins import load_model_provider`, so patching the
    # attribute on dcp.plugins is picked up at call time.
    monkeypatch.setattr("dcp.plugins.load_model_provider", lambda name: EchoProvider)
    built = build_provider(ModelBinding(provider="echo", model="my-agent"))
    assert isinstance(built, EchoProvider)
    assert built.model == "my-agent"          # constructed with the binding's model


def test_build_provider_accepts_a_ready_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    ready = EchoProvider("fixed")
    monkeypatch.setattr("dcp.plugins.load_model_provider", lambda name: ready)
    assert build_provider(ModelBinding(provider="echo", model="ignored")) is ready


def test_build_provider_unknown_name_raises_provider_error() -> None:
    # no such plugin installed → PluginError inside, surfaced as the factory's ProviderError
    with pytest.raises(ProviderError):
        build_provider(ModelBinding(provider="does-not-exist", model="m"))


def test_available_providers_lists_installed_provider_plugins() -> None:
    infos = available_providers(env={}, plugin_source=_SOURCE)
    echo = [i for i in infos if i.provider == "echo"]
    assert echo and echo[0].configured is True                 # installed ⇒ usable
    assert {"openai", "anthropic", "local", "transformers", "mock"} <= {i.provider for i in infos}


def test_available_providers_without_plugins_is_builtins_only() -> None:
    assert {i.provider for i in available_providers(env={})} == {
        "openai", "anthropic", "local", "transformers", "mock"}


def test_available_plugins_includes_providers_group() -> None:
    assert available_plugins(source=_SOURCE) == {GROUP_PROVIDERS: ["echo"]}
