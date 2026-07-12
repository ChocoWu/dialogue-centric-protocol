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


class _FlakyCompletions:
    """Fails ``fail_first`` parse calls (as a real model emitting bad JSON does), then succeeds."""

    def __init__(self, *, fail_first: int, parsed: object) -> None:
        self._left, self._parsed, self.calls = fail_first, parsed, 0

    async def parse(self, **_: object) -> object:
        self.calls += 1
        if self._left > 0:
            self._left -= 1
            raise ValueError("Invalid JSON: trailing characters")   # the observed failure mode
        msg = types.SimpleNamespace(content=None, parsed=self._parsed)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


async def test_structured_salvages_json_with_trailing_prose() -> None:
    # The observed real failure: model emits a valid object then extra text; the strict parser
    # rejects the whole string. We recover the leading JSON object instead of failing the dialogue.
    try:
        _Decision.model_validate_json('{"action":"go"}\n{"note":"trailing"}')
    except Exception as exc:                       # a real pydantic ValidationError (json_invalid)
        boom = exc
    comp = _Completions(exc=boom)
    p = OpenAIProvider("m", client=types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=comp)))
    assert await p.structured(instructions="i", content="c", schema=_Decision) == _Decision(
        action="go")


async def test_structured_retries_transient_parse_failures() -> None:
    # A couple of bad emissions must not kill the call — it retries and returns the good parse.
    comp = _FlakyCompletions(fail_first=2, parsed=_Decision(action="go"))
    p = OpenAIProvider("m", client=types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=comp)))
    assert await p.structured(instructions="i", content="c", schema=_Decision) == _Decision(
        action="go")
    assert comp.calls == 3          # two failures, then success


async def test_structured_gives_up_after_bounded_retries() -> None:
    comp = _FlakyCompletions(fail_first=99, parsed=_Decision(action="go"))
    p = OpenAIProvider("m", client=types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=comp)))
    with pytest.raises(ProviderError):
        await p.structured(instructions="i", content="c", schema=_Decision)
    assert comp.calls == 4          # bounded, not infinite (_STRUCTURED_ATTEMPTS)


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
