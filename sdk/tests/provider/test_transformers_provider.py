"""In-process HF/Qwen3 provider — logic tested with an injected generator (no torch needed)."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from dcp.errors import ProviderError
from dcp.provider import TransformersProvider, build_provider
from dcp.schema import ModelBinding


class _Decision(BaseModel):
    action: str


def _provider(reply: str) -> TransformersProvider:
    return TransformersProvider("Qwen/Qwen3-4B", generate=lambda messages: reply)


async def test_text_returns_generated_output() -> None:
    p = _provider("hi from qwen")
    assert await p.text(instructions="i", content="c") == "hi from qwen"


async def test_structured_parses_json() -> None:
    got = await _provider('{"action": "go"}').structured(instructions="i", content="c",
                                                          schema=_Decision)
    assert got == _Decision(action="go")


async def test_structured_tolerates_prose_and_thinking() -> None:
    reply = 'Sure!<think>hmm</think> Here you go: {"action": "stop"} — done.'
    got = await _provider(reply).structured(instructions="i", content="c", schema=_Decision)
    assert got == _Decision(action="stop")


async def test_structured_no_json_raises() -> None:
    with pytest.raises(ProviderError):
        await _provider("no json here").structured(instructions="i", content="c", schema=_Decision)


async def test_structured_schema_mismatch_raises() -> None:
    with pytest.raises(ProviderError):
        await _provider('{"wrong": 1}').structured(instructions="i", content="c", schema=_Decision)


def test_build_provider_transformers() -> None:
    p = build_provider(ModelBinding(provider="transformers", model="Qwen/Qwen3-4B"))
    assert isinstance(p, TransformersProvider) and p.model == "Qwen/Qwen3-4B"
