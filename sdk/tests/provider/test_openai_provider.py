"""M4 — OpenAIProvider adapter mapping via a stubbed client (no network) + key-gated live test."""

from __future__ import annotations

import os
import types

import pytest
from pydantic import BaseModel

from dcp.errors import ProviderError
from dcp.provider import OpenAIProvider, build_provider
from dcp.schema import ModelBinding


class _Decision(BaseModel):
    action: str


class _Completions:
    def __init__(
        self, *, content: object = None, parsed: object = None, exc: Exception | None = None
    ):
        self._content, self._parsed, self._exc = content, parsed, exc

    def _resp(self) -> object:
        msg = types.SimpleNamespace(content=self._content, parsed=self._parsed)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

    async def create(self, **_: object) -> object:
        if self._exc:
            raise self._exc
        return self._resp()

    async def parse(self, **_: object) -> object:
        if self._exc:
            raise self._exc
        return self._resp()


def _client(**kw: object) -> object:
    return types.SimpleNamespace(chat=types.SimpleNamespace(completions=_Completions(**kw)))


async def test_text_maps_content() -> None:
    p = OpenAIProvider("m", client=_client(content="hello"))
    assert await p.text(instructions="i", content="c") == "hello"


async def test_text_none_content_is_empty() -> None:
    p = OpenAIProvider("m", client=_client(content=None))
    assert await p.text(instructions="i", content="c") == ""


async def test_structured_returns_schema_instance() -> None:
    p = OpenAIProvider("m", client=_client(parsed=_Decision(action="go")))
    d = await p.structured(instructions="i", content="c", schema=_Decision)
    assert d == _Decision(action="go")


async def test_structured_none_raises() -> None:
    p = OpenAIProvider("m", client=_client(parsed=None))
    with pytest.raises(ProviderError):
        await p.structured(instructions="i", content="c", schema=_Decision)


async def test_errors_are_wrapped() -> None:
    p = OpenAIProvider("m", client=_client(exc=RuntimeError("boom")))
    with pytest.raises(ProviderError):
        await p.text(instructions="i", content="c")


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="needs OPENAI_API_KEY (live)")
async def test_openai_live() -> None:
    model = os.getenv("DCP_MODEL", "gpt-5.4")
    p = build_provider(ModelBinding(provider="openai", model=model))
    out = await p.text(instructions="You are terse.", content="Reply with the word OK.")
    assert isinstance(out, str) and out
