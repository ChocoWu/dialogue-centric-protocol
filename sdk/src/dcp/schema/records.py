"""Oversight + lifecycle records (SPEC §1.7, §2.10, §4.6).

Verification records drive control (D11), so their categorical fields are **enums** (not loose
strings): the orchestrator routes on `recommended_action` (pre) and `outcome` (post). This closes
the oversight part of TBD-18.
"""

from __future__ import annotations

from .base import DCPModel
from .enums import (
    Assessment,
    Availability,
    CapabilityMatch,
    ContextSufficiency,
    ExecutionFeasibility,
    PostOutcome,
    Readiness,
    RecommendedAction,
    RoleState,
    TerminationStatus,
    Verdict,
)
from .values import NonEmptyStr


class Issue(DCPModel):
    """A problem noted during oversight (SPEC §1.7 ``issues[]``)."""

    type: str
    description: str


class PreActionVerification(DCPModel):
    """Structured speaker-readiness record (SPEC §1.7; TBD-7). Drives pre-action recovery (D11)."""

    readiness: Readiness
    availability: Availability
    capability_match: CapabilityMatch
    role_state: RoleState
    context_sufficiency: ContextSufficiency
    execution_feasibility: ExecutionFeasibility
    issues: list[Issue] = []
    recommended_action: RecommendedAction
    recovered: bool = False                     # set when the orchestrator acted on the recovery


class PostActionVerification(DCPModel):
    """Structured output-verification record (SPEC §1.7; resolves TBD-8). Drives routing (D11)."""

    verdict: Verdict
    relevance: Assessment
    role_consistency: Assessment
    completeness: Assessment
    grounding: Assessment
    safety: Assessment
    human_input_addressed: bool
    issues: list[Issue] = []
    outcome: PostOutcome
    escalated: bool = False                     # set when the outcome escalated to a human gate


class TerminationRecord(DCPModel):
    """Terminal status + reason (SPEC §2.10/§4.6)."""

    status: TerminationStatus
    reason: str


class RoleCastEntry(DCPModel):
    """One role→participant casting (SPEC §2.4)."""

    role_id: NonEmptyStr
    participant_id: NonEmptyStr


class RolesCast(DCPModel):
    """The ``roles_cast`` record for auditability (SPEC §2.4/§4.6)."""

    instance_id: NonEmptyStr
    roles: list[RoleCastEntry]


__all__ = [
    "Issue",
    "PreActionVerification",
    "PostActionVerification",
    "TerminationRecord",
    "RoleCastEntry",
    "RolesCast",
]
