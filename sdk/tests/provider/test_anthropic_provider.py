"""M4 — AnthropicProvider adapter mapping via a stubbed client + key-gated live test."""

from __future__ import annotations

import os
import types

import pytest
from pydantic import BaseModel

from dcp.errors import ProviderError
from dcp.provider import AnthropicProvider, build_provider
from dcp.schema import ModelBinding


class _Decision(BaseModel):
    action: str


class _Messages:
    def __init__(
        self, *, blocks: object = None, parsed: object = None, exc: Exception | None = None
    ):
        self._blocks, self._parsed, self._exc = blocks, parsed, exc

    async def create(self, **_: object) -> object:
        if self._exc:
            raise self._exc
        return types.SimpleNamespace(content=self._blocks)

    async def parse(self, **_: object) -> object:
        if self._exc:
            raise self._exc
        return types.SimpleNamespace(parsed_output=self._parsed)


def _client(**kw: object) -> object:
    return types.SimpleNamespace(messages=_Messages(**kw))


def _block(kind: str, text: str) -> object:
    return types.SimpleNamespace(type=kind, text=text)


async def test_text_joins_text_blocks_only() -> None:
    blocks = [_block("text", "hel"), _block("thinking", "IGNORE"), _block("text", "lo")]
    p = AnthropicProvider("m", client=_client(blocks=blocks))
    assert await p.text(instructions="i", content="c") == "hello"


async def test_structured_returns_schema_instance() -> None:
    p = AnthropicProvider("m", client=_client(parsed=_Decision(action="go")))
    d = await p.structured(instructions="i", content="c", schema=_Decision)
    assert d == _Decision(action="go")


async def test_structured_none_raises() -> None:
    p = AnthropicProvider("m", client=_client(parsed=None))
    with pytest.raises(ProviderError):
        await p.structured(instructions="i", content="c", schema=_Decision)


async def test_errors_are_wrapped() -> None:
    p = AnthropicProvider("m", client=_client(exc=RuntimeError("boom")))
    with pytest.raises(ProviderError):
        await p.text(instructions="i", content="c")


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY (live)")
async def test_anthropic_live() -> None:
    p = build_provider(ModelBinding(provider="anthropic", model="claude-opus-4-8"))
    out = await p.text(instructions="You are terse.", content="Reply with the word OK.")
    assert isinstance(out, str) and out
