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

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from ..schema import Edge, TerminationStatus
from .actions import OrchestratorAction
from .context import DialogueContext


@runtime_checkable
class ControlPolicy(Protocol):
    """Decides the next control action for a turn (SPEC §1.7). The runtime does everything else."""

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction: ...


@runtime_checkable
class RecordsContextProjection(Protocol):
    """Optional seam: a policy that transmits context off-box (e.g. a remote proxy) surfaces an
    audit of *what it sent* so the runtime can record it in the event log (D12). Payloads are plain
    JSON-able mappings — the core stays free of any Phase-7 component types."""

    def drain_projection_audits(self) -> Sequence[Mapping[str, object]]: ...


def _situation(ctx: DialogueContext) -> str:
    """Render the dialogue's goal, roles, and progress so the model can choose a speaker.

    A control policy's model gets *only* what we put in its prompt: the transcript alone is not
    enough — on the opening turn it is empty, and without the goal and the roster of roles the model
    has no basis to start. This block gives it the standing context every ``decide`` call needs.
    """
    lines = [
        "You are the orchestrator of a multi-party dialogue. Choose the single next "
        "control action.",
        "",
        f"Goal: {ctx.goal}",
    ]
    if ctx.topic:
        lines.append(f"Topic: {ctx.topic}")
    brief = ctx.brief_text()
    if brief:
        lines.append(f"This dialogue's specific brief:\n{brief}")
    lines.append(f"Termination condition: {ctx.termination_condition}")
    cap = f" of at most {ctx.max_turns}" if ctx.max_turns is not None else ""
    lines.append(f"Progress: {ctx.turn} turn(s) taken{cap} so far.")
    lines.append("")
    lines.append("Roles that can speak (pick target_role_id from these ids):")
    filled = ctx.filled_role_ids()
    # Prefer roles with a participant cast in; fall back to all template roles if none are cast yet.
    speakable = [r for r in ctx.roles if r.role_id in filled] or list(ctx.roles)
    for r in speakable:
        persona = f" — {r.persona}" if r.persona else ""
        lines.append(f"- {r.role_id} ({r.name}){persona}")
    lines.append("")
    lines.append(
        "select_speaker (with target_role_id) to have that role contribute next; stop (with a "
        "terminal status) once the termination condition is met. The transcript below is the "
        "conversation so far — if it is empty the dialogue is just beginning, so open it by "
        "selecting the role best suited to start. Do not stop before anyone has spoken unless the "
        "goal is already satisfied."
    )
    return "\n".join(lines)


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
        instructions = _situation(ctx)
        hint = _flow_hint(ctx)
        if hint:
            instructions = f"{instructions}\n\n{hint}"
        if ctx.rejected_this_turn:                       # steer around unavailable candidates
            avoid = ", ".join(sorted(ctx.rejected_this_turn))
            instructions = f"{instructions}\n\nDo NOT select these roles (not ready now): {avoid}."
        transcript = ctx.transcript() or "(no messages yet — the dialogue is just beginning)"
        return await ctx.provider.structured(
            instructions=instructions,
            content=transcript,
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


__all__ = ["ControlPolicy", "RecordsContextProjection", "PlanPolicy", "FlowPolicy"]
