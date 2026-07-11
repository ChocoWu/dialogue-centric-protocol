"""Adaptive flow: a not-ready candidate makes the orchestrator select another (SPEC §1.7, §2.6).

``choose_alternative`` is not a special action — it routes back to normal ``select_speaker``, and
the re-selection avoids the just-rejected candidate (``rejected_this_turn``), so the realized path
diverges from the flow when a candidate isn't available.
"""

from __future__ import annotations

from datetime import UTC, datetime

from dcp import schema as s
from dcp.orchestration import Orchestrator, ScriptedOversight
from dcp.provider import MockProvider
from dcp.state import InstanceHeader, SqlStore

_TS = datetime(2026, 7, 11, tzinfo=UTC)


def _agent(rid: str) -> s.Role:
    return s.Role(role_id=rid, name=rid, kind=s.RoleKind.AGENT,
                  response_requirement=s.ResponseRequirement.REQUIRED)


def _ready() -> s.PreActionVerification:
    return s.PreActionVerification(
        readiness="ready", availability="available", capability_match="high", role_state="needed",
        context_sufficiency="sufficient", execution_feasibility="feasible",
        recommended_action="select_speaker")


def _unavailable() -> s.PreActionVerification:
    return s.PreActionVerification(
        readiness="not_ready", availability="unavailable", capability_match="high",
        role_state="needed", context_sufficiency="sufficient", execution_feasibility="feasible",
        recommended_action="choose_alternative",
        issues=[s.Issue(type="availability", description="agent offline")])


async def test_unavailable_candidate_switches_to_a_flow_alternative() -> None:
    store = SqlStore()
    store.create_instance(InstanceHeader(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@o", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0", created_at=_TS))
    # flow: a → {b, c} (a branch); b will be unavailable, so the turn must route to c
    tmpl = s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done", max_turns=6),
        roles=[_agent("a"), _agent("b"), _agent("c")],
        orchestration=s.Orchestration(mode=s.OrchestrationMode.FLOW),
        flow=s.Flow(entry="a", edges=[s.Edge(from_role="a", to_role="b"),
                                      s.Edge(from_role="a", to_role="c")]))
    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg",
        cast={"a": "a", "b": "b", "c": "c"},
        participants={r: s.Participant(participant_id=r, kind=s.RoleKind.AGENT, display_name=r)
                      for r in ("a", "b", "c")},
        # orchestrator model only chooses at the a→{b,c} branch; it picks b (which is unavailable)
        provider=MockProvider(
            structured_queue=[{"action": "select_speaker", "target_role_id": "b"}]),
        agent_providers={"a": MockProvider(texts=["a speaks"]),
                         "b": MockProvider(texts=["b speaks"]),   # never used
                         "c": MockProvider(texts=["c speaks"])},
        # readiness FIFO: a ready (entry) → b unavailable → c ready (the alternative)
        oversight=ScriptedOversight(pre=[_ready(), _unavailable(), _ready()]),
    )
    inst = await orch.run()

    assert inst.status is s.InstanceStatus.DONE
    assert [m.role_id for m in inst.messages] == ["a", "c"]     # b skipped; path diverged to c
    # the divergence is on record: a choose_alternative pre-verification for b
    rejected = [
        e for e in inst.events
        if e.type is s.EventType.PRE_ACTION_VERIFIED
        and e.payload.get("role_id") == "b"
        and e.payload.get("recommended_action") == "choose_alternative"
    ]
    assert len(rejected) == 1
