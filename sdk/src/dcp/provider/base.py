"""The provider-neutral ``ModelProvider`` interface (D7/D8; SPEC §1.5/§1.7).

Every model call in the SDK — orchestrator decisions, agent contributions, oversight judgments —
goes through this interface. Concrete providers (OpenAI, Anthropic, Mock) live in sibling modules
and never mix SDKs. A provider instance is bound to one model (built via ``build_provider``).
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

M = TypeVar("M", bound=BaseModel)


class ModelProvider(Protocol):
    """Async interface to a single bound model. The binding's key is resolved from env (D8)."""

    #: The bound model id (e.g. ``gpt-5.4``, ``claude-opus-4-8``, ``mock``).
    model: str

    async def text(self, *, instructions: str, content: str) -> str:
        """Free-text completion — used for agent contributions."""
        ...

    async def structured(self, *, instructions: str, content: str, schema: type[M]) -> M:
        """Structured completion validated into ``schema`` — used for decisions/oversight."""
        ...


__all__ = ["ModelProvider", "M"]
