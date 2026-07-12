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


class _CapturingAgent:
    """An agent provider that records the instructions it is given."""

    def __init__(self) -> None:
        self.instructions = ""

    async def text(self, *, instructions: str, content: str) -> str:
        self.instructions = instructions
        return "named it"

    async def structured(self, *, instructions: str, content: str, schema: type) -> object:
        raise AssertionError("agent should not be asked for a structured decision")


async def test_agent_instructions_carry_goal_and_brief() -> None:
    # The per-run brief (recorded in instance-created) must reach the agent's turn instructions.
    store = _store_with_instance()
    store.append("dlg", s.Event(
        event_id="evt_created", instance_id="dlg", type=s.EventType.INSTANCE_CREATED,
        payload={"owner": "@owner", "brief": {"product": "B2B analytics"}}, created_at=_TS))
    tmpl = s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T", goal="Agree on a name.",
        termination_policy=s.TerminationPolicy(condition="done"),
        roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT, persona="You name things.",
                      response_requirement=s.ResponseRequirement.REQUIRED)])
    agent = _CapturingAgent()
    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg", cast={"a": "a"}, participants=_agent_ps("a"),
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"}]),
        agent_providers={"a": agent})
    await orch.run()
    assert "You name things." in agent.instructions        # persona
    assert "Dialogue goal: Agree on a name." in agent.instructions
    assert "- product: B2B analytics" in agent.instructions  # the per-run brief


async def test_instance_goal_override_reaches_agent_instructions() -> None:
    # An instance-level goal overrides the template's generic goal in the agent's instructions.
    store = _store_with_instance()
    store.append("dlg", s.Event(
        event_id="evt_created", instance_id="dlg", type=s.EventType.INSTANCE_CREATED,
        payload={"owner": "@owner", "goal": "Name this product"}, created_at=_TS))
    tmpl = s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T", goal="Generic pattern goal.",
        termination_policy=s.TerminationPolicy(condition="done"),
        roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                      response_requirement=s.ResponseRequirement.REQUIRED)])
    agent = _CapturingAgent()
    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg", cast={"a": "a"}, participants=_agent_ps("a"),
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"}]),
        agent_providers={"a": agent})
    await orch.run()
    assert "Dialogue goal: Name this product" in agent.instructions  # instance goal wins
    assert "Generic pattern goal." not in agent.instructions          # template goal overridden


async def test_resolve_role_tolerates_name_or_case_variant() -> None:
    # A plan-mode model often returns the role's display name ("Proposer") or a case variant instead
    # of the exact id ("proposer"); the orchestrator resolves it rather than crashing.
    store = _store_with_instance()
    tmpl = s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done"),
        roles=[s.Role(role_id="proposer", name="Proposer", kind=s.RoleKind.AGENT,
                      response_requirement=s.ResponseRequirement.REQUIRED)])
    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg", cast={"proposer": "proposer"},
        participants={"proposer": s.Participant(
            participant_id="proposer", kind=s.RoleKind.AGENT, display_name="P")},
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "Proposer"},   # display name, not id
            {"action": "stop", "status": "done"}]),
        agent_providers={"proposer": MockProvider(texts=["hi"])})
    inst = await orch.run()
    assert [m.role_id for m in inst.messages] == ["proposer"]   # resolved despite the name variant


async def test_instance_termination_override_caps_turns() -> None:
    # Template has no turn cap; the per-run override caps it at 1, so the run stops after one turn.
    store = _store_with_instance()
    override = {"condition": "done", "max_turns": 1}
    store.append("dlg", s.Event(
        event_id="evt_created", instance_id="dlg", type=s.EventType.INSTANCE_CREATED,
        payload={"owner": "@owner", "termination_policy": override}, created_at=_TS))
    tmpl = _tmpl([_agent("a")], max_turns=None)               # template: unbounded
    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg", cast={"a": "a"}, participants=_agent_ps("a"),
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},   # one turn, then the cap trips
            {"action": "select_speaker", "target_role_id": "a"}]),
        agent_providers={"a": MockProvider(texts=["A", "A2"])})
    inst = await orch.run()
    assert inst.turn == 1                                     # capped by the instance override
    assert inst.status is s.InstanceStatus.STOPPED           # turn cap reached (§2.10)


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
