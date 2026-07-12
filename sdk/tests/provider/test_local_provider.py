"""Phase 6.3a — LocalProvider (OpenAI-compatible endpoint) + factory/discovery wiring."""

from __future__ import annotations

import types

import pytest
from pydantic import BaseModel

from dcp.errors import ProviderError
from dcp.provider import LocalProvider, available_providers, build_provider
from dcp.schema import ModelBinding


class _Decision(BaseModel):
    action: str


def _client(*, content: object = None, parsed: object = None) -> object:
    async def _create(**_: object) -> object:
        msg = types.SimpleNamespace(content=content, parsed=parsed)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    comp = types.SimpleNamespace(create=_create, parse=_create)
    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=comp))


async def test_local_provider_speaks_openai_compatible() -> None:
    p = LocalProvider("llama3.1", base_url="http://localhost:11434/v1",
                      client=_client(content="hi from ollama"))
    assert await p.text(instructions="i", content="c") == "hi from ollama"


async def test_local_structured_returns_schema() -> None:
    p = LocalProvider("m", base_url="http://x/v1", client=_client(parsed=_Decision(action="go")))
    got = await p.structured(instructions="i", content="c", schema=_Decision)
    assert got == _Decision(action="go")


def test_build_provider_local_needs_an_endpoint() -> None:
    with pytest.raises(ProviderError):
        build_provider(ModelBinding(provider="local", model="llama3.1"))   # no base_url


def test_build_provider_local_with_endpoint() -> None:
    p = build_provider(
        ModelBinding(provider="local", model="llama3.1", base_url="http://localhost:11434/v1"))
    assert isinstance(p, LocalProvider) and p.model == "llama3.1"


def test_available_providers_reports_local_by_endpoint() -> None:
    infos = {i.provider: i.configured for i in available_providers(env={})}
    assert infos["local"] is False                                   # no DCP_BASE_URL
    with_ep = {i.provider: i.configured
               for i in available_providers(env={"DCP_BASE_URL": "http://localhost:8000/v1"})}
    assert with_ep["local"] is True
    assert set(infos) == {"openai", "anthropic", "local", "transformers", "mock"}
