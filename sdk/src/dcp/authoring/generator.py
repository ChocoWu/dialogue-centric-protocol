"""Auto-generate a DialogueTemplate from a natural-language query (SPEC §2.2; D10).

A **standalone** generator, deliberately **not** an Orchestrator action: the orchestrator (§1.7)
controls a *running instance* and holds no state outside an instance log (D3), whereas authoring is
an upstream, instance-less step. The generator reuses the same model layer (a
:class:`~dcp.provider.ModelProvider`) and returns a **draft** (unregistered) template the caller
reviews, edits, then registers (§2.1) and instantiates (§2.3).
"""

from __future__ import annotations

from ..provider import ModelProvider
from ..schema import DialogueTemplate

_INSTRUCTIONS = (
    "You author DCP dialogue templates. Given a user's goal, produce ONE valid DialogueTemplate: "
    "a clear title/goal, a small set of roles (each with kind agent|human, a persona, and a "
    "response_requirement of required|optional|gate), a termination_policy, and an orchestration "
    "mode of plan (emergent) or flow (a declared graph). Keep it minimal and coherent; do not "
    "invent fields outside the schema."
)


class TemplateGenerator:
    """Turns a query into a draft :class:`DialogueTemplate` via a model provider (SPEC §2.2)."""

    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider

    async def generate(
        self, query: str, *, constraints: str | None = None
    ) -> DialogueTemplate:
        """Return a draft template for ``query`` (unregistered — caller reviews then registers)."""
        content = query if constraints is None else f"{query}\n\nConstraints: {constraints}"
        return await self._provider.structured(
            instructions=_INSTRUCTIONS, content=content, schema=DialogueTemplate
        )


__all__ = ["TemplateGenerator"]
