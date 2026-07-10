"""M1 — entity validation & invariants (SPEC §1/§4; D1/D4/D8)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from dcp import schema as s

_TS = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def test_agent_participant_may_have_model_binding() -> None:
    p = s.Participant(
        participant_id="agent.critic.v1",
        kind=s.RoleKind.AGENT,
        display_name="Technical Critic",
        model_binding=s.ModelBinding(provider="openai", model="gpt-x"),
    )
    assert p.model_binding is not None


def test_human_participant_must_not_have_model_binding() -> None:
    # D8: model_binding is agent-only.
    with pytest.raises(ValidationError):
        s.Participant(
            participant_id="@founder",
            kind=s.RoleKind.HUMAN,
            display_name="Founder",
            model_binding=s.ModelBinding(provider="openai", model="gpt-x"),
        )


def test_participant_defaults() -> None:
    p = s.Participant(participant_id="p", kind=s.RoleKind.HUMAN, display_name="P")
    assert p.discoverable is False and p.model_binding is None and p.metadata == {}


def test_message_is_immutable() -> None:
    m = s.Message(
        message_id="msg_1",
        instance_id="dlg_1",
        turn_id=3,
        role_id="technical_critic",
        participant_id="agent.critic.v1",
        speaker_kind=s.RoleKind.AGENT,
        content="The main risk is orchestration reliability.",
        created_at=_TS,
    )
    with pytest.raises(ValidationError):
        m.content = "mutated"  # frozen — append-only transcript (D3)


def test_instance_defaults_status_created() -> None:
    inst = s.DialogueInstance(
        instance_id="dlg_1",
        template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@founder",
        dcp_version="0.2.0",
    )
    assert inst.status is s.InstanceStatus.CREATED
    assert inst.visibility is s.Visibility.PRIVATE          # default private (D5)
    assert inst.turn == 0
    assert inst.messages == [] and inst.events == []


def test_template_roundtrips_and_forbids_extra() -> None:
    tmpl = s.DialogueTemplate(
        template_id="eval-ai-edu",
        version="1.0.0",
        title="Evaluate AI Education Platform",
        termination_policy=s.TerminationPolicy(condition="recommendation produced", max_turns=12),
        roles=[
            s.Role(role_id="product", name="Product Strategist", kind=s.RoleKind.AGENT,
                   response_requirement=s.ResponseRequirement.REQUIRED),
            s.Role(role_id="founder", name="Founder", kind=s.RoleKind.HUMAN,
                   response_requirement=s.ResponseRequirement.GATE,
                   human_policy=s.HumanPolicy(wait_window_seconds=60)),
        ],
    )
    again = s.DialogueTemplate.model_validate_json(tmpl.model_dump_json())
    assert again == tmpl
    with pytest.raises(ValidationError):
        s.DialogueTemplate.model_validate({**tmpl.model_dump(), "surprise": 1})
