"""Deterministic in-process provider for tests and the key-free demo (D7)."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from typing import TypeVar

from pydantic import BaseModel

from ..errors import ProviderError

M = TypeVar("M", bound=BaseModel)


class MockProvider:
    """Scripted :class:`~dcp.provider.base.ModelProvider` — no network, no key.

    - ``texts``: FIFO of text replies (falls back to ``"(mock reply)"`` when empty).
    - ``structured_queue``: FIFO of dicts, each validated into the requested schema (specific,
      ordered decisions).
    - ``structured_by_type``: default dict per schema class, used when the queue is empty (handy
      for oversight records that recur every turn).
    """

    model = "mock"

    def __init__(
        self,
        *,
        texts: list[str] | None = None,
        structured_queue: list[dict[str, object]] | None = None,
        structured_by_type: Mapping[type[BaseModel], dict[str, object]] | None = None,
    ) -> None:
        self._texts: deque[str] = deque(texts or [])
        self._queue: deque[dict[str, object]] = deque(structured_queue or [])
        self._by_type: dict[type[BaseModel], dict[str, object]] = dict(structured_by_type or {})

    async def text(self, *, instructions: str, content: str) -> str:
        return self._texts.popleft() if self._texts else "(mock reply)"

    async def structured(self, *, instructions: str, content: str, schema: type[M]) -> M:
        if self._queue:
            return schema.model_validate(self._queue.popleft())
        if schema in self._by_type:
            return schema.model_validate(self._by_type[schema])
        raise ProviderError(f"MockProvider: no scripted structured response for {schema.__name__}")


__all__ = ["MockProvider"]
