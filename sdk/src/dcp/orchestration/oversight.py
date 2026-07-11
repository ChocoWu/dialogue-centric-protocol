"""Pre/post-action oversight (SPEC §1.7; D11). Pluggable; drives control, not just audit.

The orchestrator acts on these records (pre → recovery, post → routing). Policies ship:
``DefaultOversight`` (deterministic all-pass — the key-free happy path), ``ScriptedOversight``
(FIFO of records, for deterministically exercising the recovery/routing branches without a model),
``LlmOversight`` (asks the orchestrator's provider for the structured records), and
``RubricOversight`` (6.1c — compose per-dimension check callables so a verification researcher
writes one function, not a whole policy).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..provider import ModelProvider
from ..schema import (
    Assessment,
    Availability,
    CapabilityMatch,
    ContextSufficiency,
    ExecutionFeasibility,
    Issue,
    Message,
    PostActionVerification,
    PostOutcome,
    PreActionVerification,
    Readiness,
    RecommendedAction,
    Role,
    RoleState,
    Verdict,
)


class OversightPolicy(Protocol):
    """Produces the structured verification records recorded around each contribution."""

    async def pre(self, *, role: Role, transcript: str) -> PreActionVerification: ...
    async def post(
        self, *, role: Role, message: Message, transcript: str
    ) -> PostActionVerification: ...


def _ready() -> PreActionVerification:
    return PreActionVerification(
        readiness=Readiness.READY,
        availability=Availability.AVAILABLE,
        capability_match=CapabilityMatch.HIGH,
        role_state=RoleState.NEEDED,
        context_sufficiency=ContextSufficiency.SUFFICIENT,
        execution_feasibility=ExecutionFeasibility.FEASIBLE,
        recommended_action=RecommendedAction.SELECT_SPEAKER,
    )


def _continue() -> PostActionVerification:
    return PostActionVerification(
        verdict=Verdict.PASS,
        relevance=Assessment.OK,
        role_consistency=Assessment.OK,
        completeness=Assessment.OK,
        grounding=Assessment.OK,
        safety=Assessment.OK,
        human_input_addressed=True,
        outcome=PostOutcome.CONTINUE,
    )


class DefaultOversight:
    """Deterministic all-pass oversight — ``ready``/``continue`` without a model call."""

    async def pre(self, *, role: Role, transcript: str) -> PreActionVerification:
        return _ready()

    async def post(
        self, *, role: Role, message: Message, transcript: str
    ) -> PostActionVerification:
        return _continue()


class ScriptedOversight:
    """FIFO-scripted oversight for tests: drives specific recovery/routing branches, no model.

    ``pre``/``post`` each pop the next scripted record (falling back to all-pass when empty), so a
    test can, e.g., queue a ``not_ready``/``inject_context`` pre then a ``ready`` pre to exercise
    recovery-then-retry without a live model.
    """

    def __init__(
        self,
        *,
        pre: list[PreActionVerification] | None = None,
        post: list[PostActionVerification] | None = None,
    ) -> None:
        self._pre: deque[PreActionVerification] = deque(pre or [])
        self._post: deque[PostActionVerification] = deque(post or [])

    async def pre(self, *, role: Role, transcript: str) -> PreActionVerification:
        return self._pre.popleft() if self._pre else _ready()

    async def post(
        self, *, role: Role, message: Message, transcript: str
    ) -> PostActionVerification:
        return self._post.popleft() if self._post else _continue()


class LlmOversight:
    """Model-backed oversight (SPEC §1.7) — asks the provider for the structured records."""

    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider

    async def pre(self, *, role: Role, transcript: str) -> PreActionVerification:
        return await self._provider.structured(
            instructions=f"Verify readiness of role {role.role_id!r} before it speaks.",
            content=transcript,
            schema=PreActionVerification,
        )

    async def post(
        self, *, role: Role, message: Message, transcript: str
    ) -> PostActionVerification:
        return await self._provider.structured(
            instructions=f"Verify the last contribution from role {role.role_id!r}.",
            content=f"{transcript}\n---\n{message.content}",
            schema=PostActionVerification,
        )


# --- rubric oversight (6.1c): write one check function, not a whole policy ---------------

#: The five post-action quality dimensions of a PostActionVerification (SPEC §1.7).
_DIMENSIONS = ("relevance", "role_consistency", "completeness", "grounding", "safety")


@dataclass(frozen=True)
class CheckOutcome:
    """The result of one rubric check: a per-dimension assessment + an optional issue note."""

    assessment: Assessment
    issue: str | None = None


@runtime_checkable
class Check(Protocol):
    """One post-action quality check for a single dimension.

    A check inspects the contribution and returns either a bare :class:`Assessment`
    (``ok``/``weak``/``fail``) or a :class:`CheckOutcome` carrying an issue note.
    """

    async def __call__(
        self, *, role: Role, message: Message, transcript: str
    ) -> Assessment | CheckOutcome: ...


def _default_verdict(assessments: dict[str, Assessment]) -> tuple[Verdict, PostOutcome]:
    """Derive verdict + routing from the dimension assessments (overridable).

    A safety failure escalates to a human gate; any other non-``ok`` dimension requests a revision;
    an all-``ok`` contribution continues.
    """
    if assessments.get("safety") is Assessment.FAIL:
        return Verdict.ESCALATE, PostOutcome.ESCALATE_GATE
    if any(a is not Assessment.OK for a in assessments.values()):
        return Verdict.REVISE, PostOutcome.REQUEST_REVISION
    return Verdict.PASS, PostOutcome.CONTINUE


class RubricOversight:
    """Compose per-dimension checks into post-action verification (6.1c).

    Pass a check callable for any of ``relevance``/``role_consistency``/``completeness``/
    ``grounding``/``safety``; unset dimensions default to ``ok``. The verdict + routed outcome are
    derived by ``verdict_fn`` (default :func:`_default_verdict`). Pre-action readiness defaults to
    ``ready`` — subclass or wrap if you also want pre-checks.
    """

    def __init__(
        self,
        *,
        relevance: Check | None = None,
        role_consistency: Check | None = None,
        completeness: Check | None = None,
        grounding: Check | None = None,
        safety: Check | None = None,
        verdict_fn: Callable[[dict[str, Assessment]], tuple[Verdict, PostOutcome]] | None = None,
    ) -> None:
        self._checks: dict[str, Check | None] = {
            "relevance": relevance,
            "role_consistency": role_consistency,
            "completeness": completeness,
            "grounding": grounding,
            "safety": safety,
        }
        self._verdict_fn = verdict_fn or _default_verdict

    async def pre(self, *, role: Role, transcript: str) -> PreActionVerification:
        return _ready()

    async def post(
        self, *, role: Role, message: Message, transcript: str
    ) -> PostActionVerification:
        assessments: dict[str, Assessment] = {}
        issues: list[Issue] = []
        for dim in _DIMENSIONS:
            check = self._checks[dim]
            if check is None:
                assessments[dim] = Assessment.OK
                continue
            raw = await check(role=role, message=message, transcript=transcript)
            result = raw if isinstance(raw, CheckOutcome) else CheckOutcome(raw)
            assessments[dim] = result.assessment
            if result.assessment is not Assessment.OK and result.issue:
                issues.append(Issue(type=dim, description=result.issue))
        verdict, outcome = self._verdict_fn(assessments)
        return PostActionVerification(
            verdict=verdict,
            relevance=assessments["relevance"],
            role_consistency=assessments["role_consistency"],
            completeness=assessments["completeness"],
            grounding=assessments["grounding"],
            safety=assessments["safety"],
            human_input_addressed=True,
            issues=issues,
            outcome=outcome,
            escalated=outcome is PostOutcome.ESCALATE_GATE,
        )


__all__ = [
    "OversightPolicy",
    "DefaultOversight",
    "ScriptedOversight",
    "LlmOversight",
    "RubricOversight",
    "Check",
    "CheckOutcome",
]
