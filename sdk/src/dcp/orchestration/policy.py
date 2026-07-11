"""Pluggable orchestrator control policy — the orchestrator's *brain* (Phase 6.1b; SPEC §1.7).

A ``ControlPolicy`` decides the **next control action** from a read-only :class:`DialogueContext`.
The DCP runtime keeps sole ownership of the correctness-critical machinery — pre/post oversight,
recovery/routing, turn serialization, the append-only log, replay/resume, and termination priority
— so a custom orchestrator can be powerful *and* safe ("policy proposes, runtime disposes").

Two built-ins reproduce the previous behavior: :class:`PlanPolicy` (emergent LLM speaker selection)
and :class:`FlowPolicy` (follow the template's declared graph). Researchers supply their own by
implementing ``decide`` — a single method, not a whole loop.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..schema import TerminationStatus
from .actions import OrchestratorAction
from .context import DialogueContext


@runtime_checkable
class ControlPolicy(Protocol):
    """Decides the next control action for a turn (SPEC §1.7). The runtime does everything else."""

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction: ...


class PlanPolicy:
    """Emergent selection: ask the orchestrator's model for the next action (``mode: plan``)."""

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        return await ctx.provider.structured(
            instructions="Choose the next role to speak, or stop the dialogue.",
            content=ctx.transcript(),
            schema=OrchestratorAction,
        )


class FlowPolicy:
    """Deterministic: follow the template's declared ``flow`` graph (``mode: flow``)."""

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        flow = ctx.flow
        if flow is None:
            return OrchestratorAction(action="stop", reason="no flow defined")
        if ctx.last_speaker is None:
            return OrchestratorAction(action="select_speaker", target_role_id=flow.entry)
        for edge in flow.edges:
            if edge.from_role == ctx.last_speaker:
                return OrchestratorAction(action="select_speaker", target_role_id=edge.to_role)
        return OrchestratorAction(action="stop", status=TerminationStatus.DONE, reason="flow end")


__all__ = ["ControlPolicy", "PlanPolicy", "FlowPolicy"]
