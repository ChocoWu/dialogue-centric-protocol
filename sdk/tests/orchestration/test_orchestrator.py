"""M5 — orchestration loop end-to-end with MockProvider (SPEC §2.6–§2.10; D3, TBD-25)."""

from __future__ import annotations

from datetime import UTC, datetime

from dcp import schema as s
from dcp.orchestration import HumanReply, Orchestrator, ScriptedHumanGateway
from dcp.provider import MockProvider
from dcp.state import InstanceHeader, SqlStore, restore

_TS = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def _store_with_instance() -> SqlStore:
    store = SqlStore()
    store.create_instance(InstanceHeader(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@owner", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0", created_at=_TS,
    ))
    return store


def _tmpl(roles: list[s.Role], *, mode: s.OrchestrationMode = s.OrchestrationMode.PLAN,
          max_turns: int | None = None, flow: s.Flow | None = None,
          allow_open_mic: bool = False) -> s.DialogueTemplate:
    return s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done", max_turns=max_turns),
        roles=roles, orchestration=s.Orchestration(mode=mode), flow=flow,
        allow_open_mic=allow_open_mic,
    )


def _agent(rid: str) -> s.Role:
    return s.Role(role_id=rid, name=rid, kind=s.RoleKind.AGENT,
                  response_requirement=s.ResponseRequirement.REQUIRED)


def _agent_ps(*rids: str) -> dict[str, s.Participant]:
    return {r: s.Participant(participant_id=r, kind=s.RoleKind.AGENT, display_name=r) for r in rids}


async def test_scripted_plan_dialogue_runs_to_done() -> None:
    store = _store_with_instance()
    tmpl = _tmpl([_agent("a"), _agent("b")])
    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg",
        cast={"a": "a", "b": "b"}, participants=_agent_ps("a", "b"),
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "select_speaker", "target_role_id": "b"},
            {"action": "stop", "status": "done"},
        ]),
        agent_providers={"a": MockProvider(texts=["A: hi"]), "b": MockProvider(texts=["B: reply"])},
    )
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.DONE
    assert [m.content for m in inst.messages] == ["A: hi", "B: reply"]
    assert inst.turn == 2
    # oversight records emitted
    types_ = {e.type for e in inst.events}
    assert s.EventType.PRE_ACTION_VERIFIED in types_
    assert s.EventType.POST_ACTION_VERIFIED in types_


async def test_flow_mode_follows_graph() -> None:
    store = _store_with_instance()
    tmpl = _tmpl([_agent("a"), _agent("b")], mode=s.OrchestrationMode.FLOW,
                 flow=s.Flow(entry="a", edges=[s.Edge(from_role="a", to_role="b")]))
    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg",
        cast={"a": "a", "b": "b"}, participants=_agent_ps("a", "b"),
        provider=MockProvider(),   # unused in flow mode
        agent_providers={"a": MockProvider(texts=["A"]), "b": MockProvider(texts=["B"])},
    )
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.DONE
    assert [m.role_id for m in inst.messages] == ["a", "b"]


async def test_serialized_transcript_one_message_per_turn() -> None:
    store = _store_with_instance()
    tmpl = _tmpl([_agent("a")])
    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg",
        cast={"a": "a"}, participants=_agent_ps("a"),
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"},
        ]),
        agent_providers={"a": MockProvider(texts=["t1", "t2"])},
    )
    inst = await orch.run()
    assert [m.turn_id for m in inst.messages] == [1, 2]     # one contribution per turn


async def test_turn_cap_yields_stopped() -> None:
    store = _store_with_instance()
    tmpl = _tmpl([_agent("a")], max_turns=1)
    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg",
        cast={"a": "a"}, participants=_agent_ps("a"),
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "select_speaker", "target_role_id": "a"},   # would exceed cap
        ]),
        agent_providers={"a": MockProvider(texts=["t1", "t2"])},
    )
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.STOPPED
    assert inst.turn == 1


async def test_gate_timeout_yields_provisional() -> None:
    store = _store_with_instance()
    critic = _agent("critic")
    founder = s.Role(role_id="founder", name="Founder", kind=s.RoleKind.HUMAN,
                     response_requirement=s.ResponseRequirement.GATE,
                     human_policy=s.HumanPolicy(wait_window_seconds=1,
                                                on_timeout=s.OnTimeout.FINALIZE_PROVISIONAL))
    tmpl = _tmpl([critic, founder])
    participants = {**_agent_ps("critic"),
                    "@f": s.Participant(participant_id="@f", kind=s.RoleKind.HUMAN,
                                        display_name="Founder")}
    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg",
        cast={"critic": "critic", "founder": "@f"}, participants=participants,
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "critic"},
            {"action": "select_speaker", "target_role_id": "founder"},
        ]),
        agent_providers={"critic": MockProvider(texts=["risk noted"])},
        human_gateway=ScriptedHumanGateway({}),   # founder never replies -> timeout
    )
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.PROVISIONAL
    assert s.EventType.GATE_OPENED in {e.type for e in inst.events}


async def test_gate_approval_records_decision() -> None:
    store = _store_with_instance()
    founder = s.Role(role_id="founder", name="Founder", kind=s.RoleKind.HUMAN,
                     response_requirement=s.ResponseRequirement.GATE)
    tmpl = _tmpl([founder])
    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg",
        cast={"founder": "@f"},
        participants={"@f": s.Participant(participant_id="@f", kind=s.RoleKind.HUMAN,
                                          display_name="Founder")},
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "founder"},
            {"action": "stop", "status": "done"},
        ]),
        human_gateway=ScriptedHumanGateway(
            {"founder": HumanReply(content="Approved.", decision="approve")}
        ),
    )
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.DONE
    assert inst.messages[0].metadata["decision"] == "approve"
    ev = {e.type for e in inst.events}
    assert s.EventType.GATE_OPENED in ev and s.EventType.GATE_RESOLVED in ev


async def test_open_mic_pending_until_addressed() -> None:
    store = _store_with_instance()
    orch = Orchestrator(
        store=store, template=_tmpl([_agent("a")], allow_open_mic=True), instance_id="dlg",
        cast={"a": "a"}, participants=_agent_ps("a"), provider=MockProvider(),
    )
    orch.submit_open_mic("hi_1", "How does this differ from X?", "@observer")
    inst = restore(store, "dlg")
    assert inst.pending_inputs[0].addressed is False
    orch.address_open_mic("hi_1", "a")
    assert restore(store, "dlg").pending_inputs[0].addressed is True
