"""M5.1 — oversight governs control: pre-recovery + post-routing (SPEC §1.7; D11)."""

from __future__ import annotations

from datetime import UTC, datetime

from dcp import schema as s
from dcp.orchestration import (
    HumanReply,
    Orchestrator,
    ScriptedHumanGateway,
    ScriptedOversight,
)
from dcp.provider import MockProvider
from dcp.state import InstanceHeader, SqlStore

_TS = datetime(2026, 7, 10, tzinfo=UTC)


def _store() -> SqlStore:
    store = SqlStore()
    store.create_instance(InstanceHeader(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@o", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0", created_at=_TS))
    return store


def _agent(rid: str) -> s.Role:
    return s.Role(role_id=rid, name=rid, kind=s.RoleKind.AGENT,
                  response_requirement=s.ResponseRequirement.REQUIRED)


def _tmpl(roles: list[s.Role], **kw: object) -> s.DialogueTemplate:
    return s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done", **kw), roles=roles)


def _ps(*rids: str) -> dict[str, s.Participant]:
    return {r: s.Participant(participant_id=r, kind=s.RoleKind.AGENT, display_name=r) for r in rids}


def _pre(readiness: str, action: str, *, issue: str = "") -> s.PreActionVerification:
    return s.PreActionVerification(
        readiness=readiness, availability="available", capability_match="high",
        role_state="needed", context_sufficiency="sufficient",
        execution_feasibility="feasible", recommended_action=action,
        issues=[s.Issue(type="gap", description=issue)] if issue else [])


def _post(outcome: str, *, verdict: str = "pass") -> s.PostActionVerification:
    return s.PostActionVerification(
        verdict=verdict, relevance="ok", role_consistency="ok", completeness="ok",
        grounding="ok", safety="ok", human_input_addressed=True, outcome=outcome)


# --- pre-action recovery -----------------------------------------------------------------

async def test_pre_inject_context_then_retry() -> None:
    store = _store()
    orch = Orchestrator(
        store=store, template=_tmpl([_agent("a")]), instance_id="dlg",
        cast={"a": "a"}, participants=_ps("a"),
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"}]),
        agent_providers={"a": MockProvider(texts=["contribution"])},
        oversight=ScriptedOversight(pre=[
            _pre("not_ready", "inject_context", issue="needs constraints"),  # recover...
            _pre("ready", "select_speaker"),                                 # ...then ready
        ]),
    )
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.DONE
    types_ = [e.type for e in inst.events]
    assert s.EventType.CONTEXT_INJECTED in types_          # recovery actually happened
    # the pre record that triggered recovery is flagged recovered
    pre_events = [e for e in inst.events if e.type is s.EventType.PRE_ACTION_VERIFIED]
    assert pre_events[0].payload["recovered"] is True
    assert [m.content for m in inst.messages] == ["contribution"]


async def test_pre_stop_terminates_provisional() -> None:
    store = _store()
    orch = Orchestrator(
        store=store, template=_tmpl([_agent("a")]), instance_id="dlg",
        cast={"a": "a"}, participants=_ps("a"),
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"}]),
        agent_providers={"a": MockProvider(texts=["x"])},
        oversight=ScriptedOversight(pre=[_pre("not_ready", "stop", issue="unsafe")]),
    )
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.PROVISIONAL
    assert not inst.messages                                # never contributed


async def test_pre_recovery_exhaustion_is_provisional() -> None:
    store = _store()
    # inject_context forever -> never ready -> bounded recovery exhausts
    orch = Orchestrator(
        store=store, template=_tmpl([_agent("a")]), instance_id="dlg",
        cast={"a": "a"}, participants=_ps("a"),
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"}]),
        agent_providers={"a": MockProvider(texts=["x"])},
        oversight=ScriptedOversight(pre=[_pre("not_ready", "inject_context") for _ in range(10)]),
        max_recovery_attempts=2,
    )
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.PROVISIONAL


# --- post-action routing -----------------------------------------------------------------

async def test_post_request_revision_reinvokes_same_role() -> None:
    store = _store()
    orch = Orchestrator(
        store=store, template=_tmpl([_agent("a")]), instance_id="dlg",
        cast={"a": "a"}, participants=_ps("a"),
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"}]),
        agent_providers={"a": MockProvider(texts=["draft", "revised"])},
        oversight=ScriptedOversight(post=[
            _post("request_revision", verdict="revise"),   # first output -> revise
            _post("continue"),                             # revision accepted
        ]),
    )
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.DONE
    assert [m.content for m in inst.messages] == ["draft", "revised"]
    assert s.EventType.REVISION_REQUESTED in {e.type for e in inst.events}


async def test_post_revision_bounded_by_max_revisions() -> None:
    store = _store()
    orch = Orchestrator(
        store=store, template=_tmpl([_agent("a")]), instance_id="dlg",
        cast={"a": "a"}, participants=_ps("a"),
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"}]),
        agent_providers={"a": MockProvider(texts=["d0", "d1", "d2", "d3"])},
        oversight=ScriptedOversight(post=[_post("request_revision", verdict="revise")] * 6),
        max_revisions=2,
    )
    inst = await orch.run()
    # original + exactly 2 revisions, then accept-and-continue
    revision_events = [e for e in inst.events if e.type is s.EventType.REVISION_REQUESTED]
    assert len(revision_events) == 2
    assert inst.status is s.InstanceStatus.DONE


async def test_post_request_verification_routes_to_verifier() -> None:
    store = _store()
    orch = Orchestrator(
        store=store, template=_tmpl([_agent("a"), _agent("b")]), instance_id="dlg",
        cast={"a": "a", "b": "b"}, participants=_ps("a", "b"),
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"}]),
        agent_providers={"a": MockProvider(texts=["claim"]), "b": MockProvider(texts=["verified"])},
        oversight=ScriptedOversight(post=[_post("request_verification", verdict="escalate")]),
    )
    inst = await orch.run()
    assert s.EventType.VERIFICATION_REQUESTED in {e.type for e in inst.events}
    # the verifier (role b) took a turn after a's contribution
    assert [m.role_id for m in inst.messages] == ["a", "b"]


async def test_post_stop_terminates_done() -> None:
    store = _store()
    orch = Orchestrator(
        store=store, template=_tmpl([_agent("a")]), instance_id="dlg",
        cast={"a": "a"}, participants=_ps("a"),
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"}]),
        agent_providers={"a": MockProvider(texts=["final"])},
        oversight=ScriptedOversight(post=[_post("stop")]),
    )
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.DONE
    assert inst.messages[-1].content == "final"


async def test_post_escalate_gate_opens_human_gate() -> None:
    store = _store()
    founder = s.Role(role_id="founder", name="Founder", kind=s.RoleKind.HUMAN,
                     response_requirement=s.ResponseRequirement.GATE)
    tmpl = _tmpl([_agent("a"), founder])
    participants = {**_ps("a"),
                    "@f": s.Participant(participant_id="@f", kind=s.RoleKind.HUMAN,
                                        display_name="F")}
    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg",
        cast={"a": "a", "founder": "@f"}, participants=participants,
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"}]),
        agent_providers={"a": MockProvider(texts=["risky proposal"])},
        oversight=ScriptedOversight(post=[
            _post("escalate_gate", verdict="escalate"),    # a's output escalates
            _post("continue"),                             # founder's gate reply is fine
        ]),
        human_gateway=ScriptedHumanGateway(
            {"founder": HumanReply(content="Approved.", decision="approve")}),
    )
    inst = await orch.run()
    ev = {e.type for e in inst.events}
    assert s.EventType.GATE_OPENED in ev and s.EventType.GATE_RESOLVED in ev
    post_events = [e for e in inst.events if e.type is s.EventType.POST_ACTION_VERIFIED]
    assert post_events[0].payload["escalated"] is True


# --- deepened pre-action recovery: request_human + wait_gate ------------------------------

async def test_pre_request_human_injects_input_then_retries() -> None:
    store = _store()
    advisor = s.Role(role_id="advisor", name="Advisor", kind=s.RoleKind.HUMAN,
                     response_requirement=s.ResponseRequirement.OPTIONAL)
    tmpl = _tmpl([_agent("a"), advisor])
    participants = {**_ps("a"),
                    "@h": s.Participant(participant_id="@h", kind=s.RoleKind.HUMAN,
                                        display_name="H")}
    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg",
        cast={"a": "a", "advisor": "@h"}, participants=participants,
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"}]),
        agent_providers={"a": MockProvider(texts=["now-informed answer"])},
        oversight=ScriptedOversight(pre=[
            _pre("not_ready", "request_human", issue="needs a human decision"),  # solicit...
            _pre("ready", "select_speaker"),                                     # ...then ready
        ]),
        human_gateway=ScriptedHumanGateway(
            {"advisor": HumanReply(content="Go with option B.", decision=None)}),
    )
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.DONE
    types_ = [e.type for e in inst.events]
    assert s.EventType.HUMAN_INPUT_PENDING in types_
    assert s.EventType.HUMAN_INPUT_ADDRESSED in types_
    assert s.EventType.CONTEXT_INJECTED in types_          # human input became context
    assert [m.content for m in inst.messages] == ["now-informed answer"]


async def test_pre_request_human_without_gateway_redecides() -> None:
    store = _store()
    orch = Orchestrator(
        store=store, template=_tmpl([_agent("a"), _agent("b")]), instance_id="dlg",
        cast={"a": "a", "b": "b"}, participants=_ps("a", "b"),
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},   # a not-ready, no gateway
            {"action": "select_speaker", "target_role_id": "b"},   # re-decide to b
            {"action": "stop", "status": "done"}]),
        agent_providers={"a": MockProvider(texts=["x"]), "b": MockProvider(texts=["from b"])},
        oversight=ScriptedOversight(pre=[
            _pre("not_ready", "request_human"),    # no gateway -> redecide
            _pre("ready", "select_speaker"),       # b is ready
        ]),
    )
    inst = await orch.run()
    assert [m.role_id for m in inst.messages] == ["b"]


async def test_pre_wait_gate_blocks_until_resolved_then_retries() -> None:
    store = _store()
    # seed an already-open gate the candidate must wait on
    store.append("dlg", s.Event(
        event_id="g_seed", instance_id="dlg", type=s.EventType.GATE_OPENED,
        payload={"gate_id": "g1", "role_id": "approver"}, created_at=_TS))
    approver = s.Role(role_id="approver", name="Approver", kind=s.RoleKind.HUMAN,
                      response_requirement=s.ResponseRequirement.GATE)
    tmpl = _tmpl([_agent("a"), approver])
    participants = {**_ps("a"),
                    "@h": s.Participant(participant_id="@h", kind=s.RoleKind.HUMAN,
                                        display_name="H")}
    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg",
        cast={"a": "a", "approver": "@h"}, participants=participants,
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"}]),
        agent_providers={"a": MockProvider(texts=["proceeds after gate"])},
        oversight=ScriptedOversight(pre=[
            _pre("not_ready", "wait_gate", issue="blocked on approval"),   # wait...
            _pre("ready", "select_speaker"),                               # ...then proceed
        ]),
        human_gateway=ScriptedHumanGateway(
            {"approver": HumanReply(content="Approved.", decision="approve")}),
    )
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.DONE
    assert s.EventType.GATE_RESOLVED in {e.type for e in inst.events}
    assert not inst.open_gates                             # gate cleared
    assert [m.content for m in inst.messages] == ["proceeds after gate"]
