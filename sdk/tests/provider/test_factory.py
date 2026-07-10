"""M4 — provider factory + orchestrator binding (D7/D8)."""

from __future__ import annotations

import pytest

from dcp.config import Config
from dcp.errors import ProviderError
from dcp.provider import (
    AnthropicProvider,
    MockProvider,
    OpenAIProvider,
    build_provider,
    orchestrator_binding,
)
from dcp.schema import ModelBinding


def test_build_mock() -> None:
    p = build_provider(ModelBinding(provider="mock", model="mock"))
    assert isinstance(p, MockProvider)


def test_build_openai_and_anthropic() -> None:
    # api_key passed explicitly so client construction needs no env / network.
    o = build_provider(ModelBinding(provider="openai", model="gpt-5.4"), api_key="test")
    a = build_provider(ModelBinding(provider="anthropic", model="claude-opus-4-8"), api_key="test")
    assert isinstance(o, OpenAIProvider) and o.model == "gpt-5.4"
    assert isinstance(a, AnthropicProvider) and a.model == "claude-opus-4-8"


def test_build_unknown_provider_raises() -> None:
    with pytest.raises(ProviderError):
        build_provider(ModelBinding(provider="grok", model="x"))


def test_orchestrator_binding_from_config() -> None:
    b = orchestrator_binding(Config(model_provider="openai", model="gpt-5.4"))
    assert (b.provider, b.model) == ("openai", "gpt-5.4")


def test_orchestrator_binding_requires_model_for_real_provider() -> None:
    with pytest.raises(ProviderError):
        orchestrator_binding(Config(model_provider="openai", model=None))
    # mock needs no model
    assert orchestrator_binding(Config(model_provider="mock", model=None)).provider == "mock"
