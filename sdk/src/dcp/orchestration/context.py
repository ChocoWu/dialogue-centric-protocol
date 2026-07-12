"""Read-only, log-derived view of a running dialogue (Phase 6.1a; SPEC §1.7).

A :class:`DialogueContext` is what the orchestrator's *brain* — a pluggable ``ControlPolicy`` (6.1b)
— reads to decide the next control action. It is a **pure function of the replayed instance state**
(D3) plus the orchestrator's model provider: it holds no authoritative state, mutates nothing, and
is reconstructable from the append-only log. Keeping the policy's input read-only is what lets the
runtime retain sole ownership of oversight, termination, and replay ("policy proposes, runtime
disposes").
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..provider import ModelProvider
from ..schema import (
    Budget,
    DialogueInstance,
    DialogueTemplate,
    EventType,
    Flow,
    Gate,
    InstanceStatus,
    Message,
    Metadata,
    OrchestrationMode,
    PendingInput,
    RecommendedAction,
    Role,
    RosterEntry,
    TerminationPolicy,
)


def effective_termination(
    instance: DialogueInstance, template: DialogueTemplate
) -> TerminationPolicy:
    """The termination policy in force for a run: the instance's per-run override, else the
    template's reusable default. Mirrors the ``instance.goal or template.goal`` rule."""
    return instance.termination_policy or template.termination_policy


def render_brief(brief: Mapping[str, object]) -> str:
    """Render an instance brief (the per-run task input) as prompt text — ``key: value`` per line.

    Shared by the control policy and the agent turn so both see the same concrete task; returns
    ``""`` for an empty brief so callers can cheaply skip it.
    """
    lines = []
    for key, value in brief.items():
        if isinstance(value, list | tuple):
            rendered = ", ".join(str(v) for v in value)
        else:
            rendered = str(value)
        lines.append(f"- {key}: {rendered}")
    return "\n".join(lines)


@dataclass(frozen=True)
class DialogueContext:
    """A read-only snapshot of a dialogue's state for a control policy to reason over.

    Immutable and log-derived. Construct with :meth:`from_instance`. Sequence fields are tuples so
    the view cannot be mutated in place.
    """

    instance_id: str
    goal: str
    topic: str
    brief: Metadata
    termination_condition: str
    max_turns: int | None
    roles: tuple[Role, ...]                      # the template's roles (the possible speakers)
    orchestration_mode: OrchestrationMode
    flow: Flow | None
    status: InstanceStatus
    turn: int
    last_speaker: str | None                     # role_id of the most recent contribution
    roster: tuple[RosterEntry, ...]              # cast + joined participants with tiers
    messages: tuple[Message, ...]                # the transcript, in order
    open_gates: tuple[Gate, ...]
    pending_inputs: tuple[PendingInput, ...]
    budget: Budget
    provider: ModelProvider                      # the orchestrator's model, for LLM-based policies
    #: Roles a pre-action check has judged unavailable in the current (pending) turn — a policy
    #: re-selecting a speaker should skip these (log-derived; realizes ``choose_alternative``).
    rejected_this_turn: frozenset[str] = frozenset()

    @classmethod
    def from_instance(
        cls,
        instance: DialogueInstance,
        template: DialogueTemplate,
        provider: ModelProvider,
    ) -> DialogueContext:
        """Build a context from a (replayed) instance + its template + the orchestrator provider."""
        last_speaker = instance.messages[-1].role_id if instance.messages else None
        termination = effective_termination(instance, template)   # per-run override or template
        return cls(
            instance_id=instance.instance_id,
            goal=instance.goal or template.goal,     # per-run objective overrides the template's
            topic=template.topic,
            brief=dict(instance.brief),
            termination_condition=termination.condition,
            max_turns=termination.max_turns,
            roles=tuple(template.roles),
            orchestration_mode=template.orchestration.mode,
            flow=template.flow,
            status=instance.status,
            turn=instance.turn,
            last_speaker=last_speaker,
            roster=tuple(instance.roster),
            messages=tuple(instance.messages),
            open_gates=tuple(instance.open_gates),
            pending_inputs=tuple(instance.pending_inputs),
            budget=instance.budget,
            provider=provider,
            rejected_this_turn=cls._rejected_this_turn(instance),
        )

    @staticmethod
    def _rejected_this_turn(instance: DialogueInstance) -> frozenset[str]:
        """Roles a pre-check recommended replacing (``choose_alternative``) since the last turn.

        Derived purely from the log: a ``turn_assigned`` (a speaker was successfully selected)
        resets the set; a ``pre_action_verified`` recommending ``choose_alternative`` adds its role.
        """
        rejected: set[str] = set()
        for event in instance.events:
            if event.type is EventType.TURN_ASSIGNED:
                rejected.clear()
            elif event.type is EventType.PRE_ACTION_VERIFIED:
                if event.payload.get("recommended_action") == RecommendedAction.CHOOSE_ALTERNATIVE:
                    role_id = event.payload.get("role_id")
                    if isinstance(role_id, str):
                        rejected.add(role_id)
        return frozenset(rejected)

    # --- convenience accessors (no state; pure reads) --------------------------------
    def transcript(self) -> str:
        """The serialized transcript, one ``role_id: content`` line per message."""
        return "\n".join(f"{m.role_id}: {m.content}" for m in self.messages)

    def brief_text(self) -> str:
        """The instance brief rendered for a prompt (``""`` when no brief was supplied)."""
        return render_brief(self.brief)

    def role(self, role_id: str) -> Role | None:
        """The template Role with ``role_id``, or ``None``."""
        return next((r for r in self.roles if r.role_id == role_id), None)

    def filled_role_ids(self) -> set[str]:
        """Role ids that currently have a participant cast into them (from the roster)."""
        return {e.role_id for e in self.roster if e.role_id is not None}

    def over_turn_cap(self) -> bool:
        """True iff the turn cap (``max_turns``) has been reached."""
        return self.max_turns is not None and self.turn >= self.max_turns


__all__ = ["DialogueContext", "render_brief", "effective_termination"]
