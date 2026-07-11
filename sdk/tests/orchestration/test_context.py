"""Phase 6.1a — DialogueContext: a read-only, log-derived view for a control policy (SPEC §1.7)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from dcp import schema as s
from dcp.orchestration import DialogueContext
from dcp.provider import MockProvider

_TS = datetime(2026, 7, 11, tzinfo=UTC)


def _msg(mid: str, role: str, content: str, turn: int) -> s.Message:
    return s.Message(
        message_id=mid, instance_id="dlg", turn_id=turn, role_id=role, participant_id=role,
        speaker_kind=s.RoleKind.AGENT, content=content, created_at=_TS)


def _template() -> s.DialogueTemplate:
    return s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T", goal="Reach consensus", topic="naming",
        termination_policy=s.TerminationPolicy(condition="agreed", max_turns=6),
        roles=[
            s.Role(role_id="proposer", name="Proposer", kind=s.RoleKind.AGENT,
                   response_requirement=s.ResponseRequirement.REQUIRED),
            s.Role(role_id="critic", name="Critic", kind=s.RoleKind.AGENT,
                   response_requirement=s.ResponseRequirement.REQUIRED),
        ],
        orchestration=s.Orchestration(mode=s.OrchestrationMode.PLAN),
    )


def _instance(*messages: s.Message) -> s.DialogueInstance:
    return s.DialogueInstance(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@o", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0",
        status=s.InstanceStatus.RUNNING, turn=len(messages),
        roster=[s.RosterEntry(participant_id="proposer", tier=s.AccessTier.SPEAK,
                              role_id="proposer")],
        messages=list(messages), events=[], open_gates=[], pending_inputs=[],
        budget=s.Budget(turns_used=len(messages)))


def _ctx(*messages: s.Message) -> DialogueContext:
    provider = MockProvider()
    return DialogueContext.from_instance(_instance(*messages), _template(), provider)


def test_from_instance_populates_state() -> None:
    ctx = _ctx(_msg("m1", "proposer", "hi", 1))
    assert ctx.instance_id == "dlg"
    assert ctx.goal == "Reach consensus"
    assert ctx.topic == "naming"
    assert ctx.termination_condition == "agreed"
    assert ctx.max_turns == 6
    assert ctx.orchestration_mode is s.OrchestrationMode.PLAN
    assert ctx.status is s.InstanceStatus.RUNNING
    assert ctx.turn == 1
    assert {r.role_id for r in ctx.roles} == {"proposer", "critic"}


def test_transcript_serializes_messages_in_order() -> None:
    ctx = _ctx(_msg("m1", "proposer", "A", 1), _msg("m2", "critic", "B", 2))
    assert ctx.transcript() == "proposer: A\ncritic: B"


def test_last_speaker_is_the_final_message_role() -> None:
    ctx = _ctx(_msg("m1", "proposer", "A", 1), _msg("m2", "critic", "B", 2))
    assert ctx.last_speaker == "critic"
    assert _ctx().last_speaker is None                     # empty transcript


def test_role_lookup_and_filled_roles() -> None:
    ctx = _ctx(_msg("m1", "proposer", "A", 1))
    assert ctx.role("critic").kind is s.RoleKind.AGENT     # type: ignore[union-attr]
    assert ctx.role("missing") is None
    assert ctx.filled_role_ids() == {"proposer"}           # only cast role on the roster


def test_over_turn_cap_reflects_max_turns() -> None:
    # instance turn == len(messages); build 6 messages against a max_turns=6 template
    msgs = tuple(_msg(f"m{i}", "proposer", "x", i) for i in range(1, 7))
    assert _ctx(*msgs).over_turn_cap() is True
    assert _ctx(_msg("m1", "proposer", "x", 1)).over_turn_cap() is False


def test_provider_is_carried_for_llm_policies() -> None:
    provider = MockProvider(texts=["decision"])
    ctx = DialogueContext.from_instance(_instance(), _template(), provider)
    assert ctx.provider is provider


def test_context_is_immutable() -> None:
    ctx = _ctx()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.turn = 99  # type: ignore[misc]
