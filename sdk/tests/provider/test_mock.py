"""M4 — MockProvider (D7): deterministic text + structured, no network."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from dcp.errors import ProviderError
from dcp.provider import MockProvider


class _Decision(BaseModel):
    action: str
    reason: str = ""


async def test_text_queue_and_default() -> None:
    p = MockProvider(texts=["first", "second"])
    assert await p.text(instructions="i", content="c") == "first"
    assert await p.text(instructions="i", content="c") == "second"
    assert await p.text(instructions="i", content="c") == "(mock reply)"   # falls back


async def test_structured_queue_fifo() -> None:
    p = MockProvider(structured_queue=[{"action": "select_speaker"}, {"action": "stop"}])
    d1 = await p.structured(instructions="i", content="c", schema=_Decision)
    d2 = await p.structured(instructions="i", content="c", schema=_Decision)
    assert (d1.action, d2.action) == ("select_speaker", "stop")


async def test_structured_by_type_default() -> None:
    p = MockProvider(structured_by_type={_Decision: {"action": "continue"}})
    d = await p.structured(instructions="i", content="c", schema=_Decision)
    assert d.action == "continue"


async def test_structured_exhausted_raises() -> None:
    p = MockProvider()
    with pytest.raises(ProviderError):
        await p.structured(instructions="i", content="c", schema=_Decision)
