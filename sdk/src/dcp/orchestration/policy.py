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

from ..schema import Edge, TerminationStatus
from .actions import OrchestratorAction
from .context import DialogueContext


@runtime_checkable
class ControlPolicy(Protocol):
    """Decides the next control action for a turn (SPEC §1.7). The runtime does everything else."""

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction: ...


def _flow_hint(ctx: DialogueContext) -> str:
    """Render the template ``flow`` as an **advisory** hint for plan mode (SPEC §2.6).

    The flow is a suggested structure the model MAY follow or deviate from — unlike ``flow`` mode,
    which is binding. Returns ``""`` when no flow is declared.
    """
    flow = ctx.flow
    if flow is None:
        return ""
    lines = [
        "Advisory flow (a suggested structure — follow it unless the dialogue needs otherwise):",
        f"- entry: {flow.entry}",
    ]
    for edge in flow.edges:
        cond = f" (when {edge.condition})" if edge.condition else ""
        lines.append(f"- after {edge.from_role} → {edge.to_role}{cond}")
    if ctx.last_speaker is not None:
        nexts = [e.to_role for e in flow.edges if e.from_role == ctx.last_speaker]
        if nexts:
            lines.append(f"- suggested next after {ctx.last_speaker}: {', '.join(nexts)}")
    return "\n".join(lines)


class PlanPolicy:
    """Emergent selection: ask the orchestrator's model for the next action (``mode: plan``).

    If the template declares a ``flow``, it is passed as an **advisory** hint (SPEC §2.6) — a bias
    the model may follow or override — not a binding graph.
    """

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        instructions = "Choose the next role to speak, or stop the dialogue."
        hint = _flow_hint(ctx)
        if hint:
            instructions = f"{instructions}\n\n{hint}"
        if ctx.rejected_this_turn:                       # steer around unavailable candidates
            avoid = ", ".join(sorted(ctx.rejected_this_turn))
            instructions = f"{instructions}\n\nDo NOT select these roles (not ready now): {avoid}."
        return await ctx.provider.structured(
            instructions=instructions,
            content=ctx.transcript(),
            schema=OrchestratorAction,
        )


class FlowPolicy:
    """Follow the template's declared ``flow`` as a **guided** graph (``mode: flow``; SPEC §2.6).

    The flow constrains succession to its declared edges. From the last speaker: exactly one
    outgoing edge → take it (deterministic); several → the orchestrator's model chooses among **only
    those allowed roles** (edge ``condition``s shown as guidance); none → the flow ends. The flow is
    the *initial/default* order — the oversight loop may still adapt it at runtime (e.g. switch to
    an alternative when a candidate is not ready), so realized paths may diverge from the graph.
    """

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        flow = ctx.flow
        if flow is None:
            return OrchestratorAction(action="stop", reason="no flow defined")
        if ctx.last_speaker is None:
            if flow.entry in ctx.rejected_this_turn:
                return OrchestratorAction(
                    action="stop", status=TerminationStatus.PROVISIONAL, reason="entry unavailable")
            return OrchestratorAction(action="select_speaker", target_role_id=flow.entry)
        # constrain to the allowed outgoing edges, dropping candidates already found unavailable
        allowed = [
            e for e in flow.edges
            if e.from_role == ctx.last_speaker and e.to_role not in ctx.rejected_this_turn
        ]
        if not allowed:
            return OrchestratorAction(
                action="stop", status=TerminationStatus.DONE, reason="flow end")
        if len(allowed) == 1:
            return OrchestratorAction(action="select_speaker", target_role_id=allowed[0].to_role)
        return await self._choose_branch(ctx, allowed)

    async def _choose_branch(self, ctx: DialogueContext, allowed: list[Edge]) -> OrchestratorAction:
        """At a branch, let the model pick among the flow-allowed next roles (then constrain)."""
        options = "\n".join(
            f"- {e.to_role}" + (f" (when {e.condition})" if e.condition else "") for e in allowed
        )
        action = await ctx.provider.structured(
            instructions=(
                "Choose the next role to speak from ONLY these flow-allowed options, "
                f"or stop the dialogue:\n{options}"
            ),
            content=ctx.transcript(),
            schema=OrchestratorAction,
        )
        allowed_ids = {e.to_role for e in allowed}
        if action.action == "stop" or action.target_role_id in allowed_ids:
            return action
        # the model wandered outside the allowed set → constrain to the first allowed edge
        return OrchestratorAction(action="select_speaker", target_role_id=allowed[0].to_role)


__all__ = ["ControlPolicy", "PlanPolicy", "FlowPolicy"]
