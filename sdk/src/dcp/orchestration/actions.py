"""Internal LLM-decision + termination shapes for orchestration (SPEC §1.7, §2.10).

``OrchestratorAction`` is the structured decision the orchestrator asks its model for each turn
(plan mode). ``resolve_termination`` encodes the SPEC §2.10 priority order.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..schema import TerminationStatus


class OrchestratorAction(BaseModel):
    """One control decision (plan mode): pick the next speaker, or stop (SPEC §1.7 subset)."""

    action: Literal["select_speaker", "stop"]
    target_role_id: str | None = None
    status: TerminationStatus = TerminationStatus.DONE   # terminal status when action == "stop"
    reason: str = ""


def resolve_termination(
    *,
    errored: bool = False,
    over_budget: bool = False,
    over_turns: bool = False,
    gate_timeout: bool = False,
    done: bool = False,
) -> TerminationStatus | None:
    """Highest-priority terminal status, or ``None`` if the instance should keep running.

    Priority (SPEC §2.10, TBD-16): error > budget > stopped > provisional > done.
    """
    if errored:
        return TerminationStatus.ERROR
    if over_budget:
        return TerminationStatus.BUDGET
    if over_turns:
        return TerminationStatus.STOPPED
    if gate_timeout:
        return TerminationStatus.PROVISIONAL
    if done:
        return TerminationStatus.DONE
    return None


__all__ = ["OrchestratorAction", "resolve_termination"]
