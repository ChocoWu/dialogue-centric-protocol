"""First-class enums for DCP (SPEC §1, §2). All are string enums for clean JSON.

Value spaces are owner-confirmed (SPEC §7). ``StrEnum`` requires Python ≥ 3.11.
"""

from __future__ import annotations

from enum import StrEnum


class InstanceStatus(StrEnum):
    """DialogueInstance lifecycle status (SPEC §1.3; TBD-3 confirmed)."""

    CREATED = "created"          # instantiated, not yet started
    RUNNING = "running"
    AWAITING = "awaiting"        # blocked on a gate / required human input
    # terminal (SPEC §2.10):
    DONE = "done"
    PROVISIONAL = "provisional"
    STOPPED = "stopped"
    BUDGET = "budget"
    ERROR = "error"


#: The subset of :class:`InstanceStatus` that is terminal (SPEC §2.10).
TERMINAL_STATUSES: frozenset[InstanceStatus] = frozenset(
    {
        InstanceStatus.DONE,
        InstanceStatus.PROVISIONAL,
        InstanceStatus.STOPPED,
        InstanceStatus.BUDGET,
        InstanceStatus.ERROR,
    }
)


def is_resumable(status: InstanceStatus) -> bool:
    """True iff an instance in ``status`` can be resumed — i.e. is non-terminal (SPEC §2.9, D3)."""
    return status not in TERMINAL_STATUSES


class TerminationStatus(StrEnum):
    """Terminal status recorded in a TerminationRecord (SPEC §2.10, §4.6)."""

    DONE = "done"
    PROVISIONAL = "provisional"
    STOPPED = "stopped"
    BUDGET = "budget"
    ERROR = "error"


class RoleKind(StrEnum):
    """Role/Participant kind (SPEC §1.4/§1.5; TBD-4 confirmed)."""

    AGENT = "agent"
    HUMAN = "human"


class ResponseRequirement(StrEnum):
    """Per-role wait/mandate policy (SPEC §1.4; renamed from ``response_mode``; TBD-5)."""

    REQUIRED = "required"        # orchestrator waits; mandatory
    OPTIONAL = "optional"        # no wait; best-effort enrichment
    GATE = "gate"               # human approval gate (required + decision semantics)


class AccessTier(StrEnum):
    """Per-instance access tier (SPEC §1.6; D5). ``own`` ⊃ ``speak`` ⊃ ``observe``."""

    OWN = "own"
    SPEAK = "speak"
    OBSERVE = "observe"


class Visibility(StrEnum):
    """Instance visibility (SPEC §1.6; D5)."""

    PUBLIC = "public"
    UNLISTED = "unlisted"
    PRIVATE = "private"


class OrchestrationMode(StrEnum):
    """Orchestration mode (SPEC §2.6; TBD-12 confirmed)."""

    PLAN = "plan"               # emergent — orchestrator selects freely (flow, if any, is advisory)
    FLOW = "flow"               # guided — succession constrained to the declared flow graph


class OnTimeout(StrEnum):
    """Human-policy timeout behavior (SPEC §2.8; TBD-14 confirmed)."""

    CONTINUE = "continue"
    FINALIZE_PROVISIONAL = "finalize_provisional"


class Readiness(StrEnum):
    """Pre-action speaker readiness (SPEC §1.7)."""

    READY = "ready"
    NOT_READY = "not_ready"
    UNCERTAIN = "uncertain"


class Availability(StrEnum):
    """Pre-action candidate availability (SPEC §1.7)."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    WAITING = "waiting"
    TIMEOUT = "timeout"


class CapabilityMatch(StrEnum):
    """Pre-action capability fit (SPEC §1.7)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RoleState(StrEnum):
    """Pre-action role state relative to the dialogue need (SPEC §1.7)."""

    NEEDED = "needed"
    ALREADY_SATISFIED = "already_satisfied"
    OVERUSED = "overused"
    BLOCKED = "blocked"


class ContextSufficiency(StrEnum):
    """Pre-action context sufficiency (SPEC §1.7)."""

    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient"


class ExecutionFeasibility(StrEnum):
    """Pre-action execution feasibility (SPEC §1.7)."""

    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    UNCERTAIN = "uncertain"


class RecommendedAction(StrEnum):
    """Pre-action recommended control action (SPEC §1.7 recovery)."""

    SELECT_SPEAKER = "select_speaker"
    INJECT_CONTEXT = "inject_context"
    CHOOSE_ALTERNATIVE = "choose_alternative"
    REQUEST_HUMAN = "request_human"
    WAIT_GATE = "wait_gate"
    STOP = "stop"


class Verdict(StrEnum):
    """Post-action overall judgment (SPEC §1.7)."""

    PASS = "pass"
    REVISE = "revise"
    ESCALATE = "escalate"
    REJECT = "reject"


class Assessment(StrEnum):
    """Per-dimension post-action quality (relevance/consistency/… — SPEC §1.7)."""

    OK = "ok"
    WEAK = "weak"
    FAIL = "fail"


class PostOutcome(StrEnum):
    """Post-action routed control action (SPEC §1.7)."""

    CONTINUE = "continue"
    REQUEST_REVISION = "request_revision"
    REQUEST_VERIFICATION = "request_verification"
    ESCALATE_GATE = "escalate_gate"
    STOP = "stop"


class EventType(StrEnum):
    """Event ``type`` taxonomy (SPEC §1.9; TBD-9 confirmed, living/extensible)."""

    # registry
    TEMPLATE_REGISTERED = "template_registered"
    PARTICIPANT_REGISTERED = "participant_registered"
    TEMPLATE_DEPRECATED = "template_deprecated"
    # instance lifecycle
    INSTANCE_CREATED = "instance_created"
    INSTANCE_STARTED = "instance_started"
    TURN_ASSIGNED = "turn_assigned"
    CONTRIBUTION_RECORDED = "contribution_recorded"
    INSTANCE_SUSPENDED = "instance_suspended"     # paused, non-terminal — resumable later (§2.9)
    INSTANCE_TERMINATED = "instance_terminated"
    # participation
    ROLES_CAST = "roles_cast"
    PARTICIPANT_JOINED = "participant_joined"
    PARTICIPANT_LEFT = "participant_left"
    TIER_CHANGED = "tier_changed"
    HUMAN_INPUT_PENDING = "human_input_pending"
    HUMAN_INPUT_ADDRESSED = "human_input_addressed"
    GATE_OPENED = "gate_opened"
    GATE_RESOLVED = "gate_resolved"
    # oversight
    PRE_ACTION_VERIFIED = "pre_action_verified"
    POST_ACTION_VERIFIED = "post_action_verified"
    REVISION_REQUESTED = "revision_requested"
    VERIFICATION_REQUESTED = "verification_requested"
    CONTEXT_INJECTED = "context_injected"
    CONTEXT_PROJECTED = "context_projected"       # a remote policy transmitted a projection (D12)


__all__ = [
    "InstanceStatus",
    "TERMINAL_STATUSES",
    "TerminationStatus",
    "RoleKind",
    "ResponseRequirement",
    "AccessTier",
    "Visibility",
    "OrchestrationMode",
    "OnTimeout",
    "EventType",
    "Readiness",
    "Availability",
    "CapabilityMatch",
    "RoleState",
    "ContextSufficiency",
    "ExecutionFeasibility",
    "RecommendedAction",
    "Verdict",
    "Assessment",
    "PostOutcome",
]
