"""M5 — termination priority order (SPEC §2.10, TBD-16)."""

from __future__ import annotations

from dcp.orchestration import resolve_termination
from dcp.schema import TerminationStatus as T


def test_none_when_nothing_triggers() -> None:
    assert resolve_termination() is None


def test_priority_error_beats_all() -> None:
    assert resolve_termination(errored=True, over_budget=True, over_turns=True,
                               gate_timeout=True, done=True) is T.ERROR


def test_budget_beats_done() -> None:
    assert resolve_termination(over_budget=True, done=True) is T.BUDGET


def test_stopped_beats_provisional_and_done() -> None:
    assert resolve_termination(over_turns=True, gate_timeout=True, done=True) is T.STOPPED


def test_provisional_beats_done() -> None:
    assert resolve_termination(gate_timeout=True, done=True) is T.PROVISIONAL


def test_done_last() -> None:
    assert resolve_termination(done=True) is T.DONE
