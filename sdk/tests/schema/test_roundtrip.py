"""M1 — JSON round-trip for every top-level entity/record (methodology playbook item 11).

Each representative example is built from the SPEC §4 field tables + the D1–D8 model, then
``model_dump_json -> model_validate_json`` must reproduce it exactly. (The illustrative JSON
in ``protocol_design.md`` predates the D1 template/instance split and is not used verbatim.)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dcp import schema as s
from dcp.schema.base import DCPModel

_TS = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def _examples() -> list[DCPModel]:
    binding = s.ModelBinding(provider="openai", model="gpt-x")
    template = s.DialogueTemplate(
        template_id="eval-ai-edu",
        version="1.0.0",
        title="Evaluate AI Education Platform",
        topic="AI for education",
        goal="Produce a recommendation on product feasibility.",
        termination_policy=s.TerminationPolicy(
            condition="A final recommendation with risks and next steps is produced.",
            max_turns=12,
            token_budget=10000,
        ),
        roles=[
            s.Role(role_id="product", name="Product Strategist", kind=s.RoleKind.AGENT,
                   persona="Analyze product-market fit.",
                   response_requirement=s.ResponseRequirement.REQUIRED),
            s.Role(role_id="founder", name="Founder", kind=s.RoleKind.HUMAN,
                   response_requirement=s.ResponseRequirement.GATE,
                   binding=s.RoleBinding(participant_id="@founder"),
                   human_policy=s.HumanPolicy(wait_window_seconds=60)),
        ],
        flow=s.Flow(entry="product", edges=[s.Edge(from_role="product", to_role="founder")]),
        orchestration=s.Orchestration(mode=s.OrchestrationMode.PLAN, model_binding=binding),
        default_visibility=s.Visibility.PRIVATE,
    )
    participant_agent = s.Participant(
        participant_id="agent.product.v1", kind=s.RoleKind.AGENT,
        display_name="Product Strategist", discoverable=True, model_binding=binding,
    )
    participant_human = s.Participant(
        participant_id="@founder", kind=s.RoleKind.HUMAN, display_name="Founder",
    )
    role = s.Role(
        role_id="founder", name="Founder", kind=s.RoleKind.HUMAN,
        response_requirement=s.ResponseRequirement.GATE,
        binding=s.RoleBinding(participant_id="@founder"),
        human_policy=s.HumanPolicy(wait_window_seconds=60),
    )
    message = s.Message(
        message_id="msg_001", instance_id="dlg_001", turn_id=3, role_id="product",
        participant_id="agent.product.v1", speaker_kind=s.RoleKind.AGENT,
        content="Product-market fit looks strong for universities.", created_at=_TS,
    )
    event = s.Event(
        event_id="evt_001", instance_id="dlg_001", type=s.EventType.TURN_ASSIGNED,
        payload={"target_role_id": "founder", "reason": "gate"}, created_at=_TS,
    )
    instance = s.DialogueInstance(
        instance_id="dlg_001",
        template_ref=s.TemplateRef(template_id="eval-ai-edu", version="1.0.0"),
        owner="@founder", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0",
        status=s.InstanceStatus.RUNNING, turn=3,
        roster=[
            s.RosterEntry(
                participant_id="agent.product.v1", tier=s.AccessTier.SPEAK, role_id="product"
            ),
            s.RosterEntry(participant_id="@founder", tier=s.AccessTier.OWN, role_id="founder"),
        ],
        messages=[message], events=[event],
        open_gates=[s.Gate(gate_id="g1", role_id="founder")],
        pending_inputs=[
            s.PendingInput(
                input_id="hi_1", kind="open_mic", content="Q?", from_participant="@obs"
            )
        ],
        budget=s.Budget(turns_used=3, tokens_used=1200, max_turns=12, token_budget=10000),
    )
    pre = s.PreActionVerification(
        readiness="ready", availability="available", capability_match="high",
        role_state="needed", context_sufficiency="sufficient",
        execution_feasibility="feasible", recommended_action="select_speaker",
    )
    post = s.PostActionVerification(
        verdict="pass", relevance="ok", role_consistency="ok", completeness="ok",
        grounding="ok", safety="ok", human_input_addressed=True, outcome="continue",
        issues=[s.Issue(type="none", description="")],
    )
    termination = s.TerminationRecord(status=s.TerminationStatus.DONE, reason="Goal satisfied.")
    roles_cast = s.RolesCast(
        instance_id="dlg_001",
        roles=[s.RoleCastEntry(role_id="product", participant_id="agent.product.v1")],
    )
    access_grant = s.AccessGrant(
        instance_id="dlg_001", participant_id="@obs", tier=s.AccessTier.OBSERVE,
        granted_by="@founder", granted_at=_TS,
    )
    return [
        binding, template, participant_agent, participant_human, role, message, event, instance,
        pre, post, termination, roles_cast, access_grant,
    ]


@pytest.mark.parametrize("example", _examples(), ids=lambda e: type(e).__name__)
def test_json_roundtrip(example: DCPModel) -> None:
    reloaded = type(example).model_validate_json(example.model_dump_json())
    assert reloaded == example


def test_examples_cover_all_top_level_types() -> None:
    covered = {type(e).__name__ for e in _examples()}
    for name in (
        "DialogueTemplate", "DialogueInstance", "Participant", "Role", "Message", "Event",
        "PreActionVerification", "PostActionVerification", "TerminationRecord",
        "RolesCast", "AccessGrant", "ModelBinding",
    ):
        assert name in covered
