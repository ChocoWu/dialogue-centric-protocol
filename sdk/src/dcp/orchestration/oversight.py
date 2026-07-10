"""Pre/post-action oversight (SPEC §1.7; D11). Pluggable; drives control, not just audit.

The orchestrator acts on these records (pre → recovery, post → routing). Three policies ship:
``DefaultOversight`` (deterministic all-pass — the key-free happy path), ``ScriptedOversight``
(FIFO of records, for deterministically exercising the recovery/routing branches without a model),
and ``LlmOversight`` (asks the orchestrator's provider for the structured records).
"""

from __future__ import annotations

from collections import deque
from typing import Protocol

from ..provider import ModelProvider
from ..schema import (
    Assessment,
    Availability,
    CapabilityMatch,
    ContextSufficiency,
    ExecutionFeasibility,
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


__all__ = ["OversightPolicy", "DefaultOversight", "ScriptedOversight", "LlmOversight"]
