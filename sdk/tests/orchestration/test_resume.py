"""M5+ — orchestrator resume: attach to a running instance and continue (SPEC §2.9; D3)."""

from __future__ import annotations

from datetime import UTC, datetime

from dcp import schema as s
from dcp.orchestration import Orchestrator
from dcp.provider import MockProvider
from dcp.state import InstanceHeader, SqlStore

_TS = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def _agent(rid: str) -> s.Role:
    return s.Role(role_id=rid, name=rid, kind=s.RoleKind.AGENT,
                  response_requirement=s.ResponseRequirement.REQUIRED)


def _seed_running_instance() -> SqlStore:
    """A store holding a half-run dialogue: started, role a cast + joined, one turn recorded."""
    store = SqlStore()
    store.create_instance(InstanceHeader(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@owner", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0", created_at=_TS,
    ))
    ev = lambda i, t, **p: s.Event(  # noqa: E731
        event_id=f"e{i}", instance_id="dlg", type=t, payload=p, created_at=_TS)
    store.append("dlg", ev(0, s.EventType.INSTANCE_STARTED))
    store.append("dlg", ev(1, s.EventType.ROLES_CAST,
                           roles=[{"role_id": "a", "participant_id": "a"}]))
    store.append("dlg", ev(2, s.EventType.PARTICIPANT_JOINED, participant_id="a", tier="speak"))
    store.append("dlg", ev(3, s.EventType.TURN_ASSIGNED, target_role_id="a", turn=1))
    store.append("dlg", s.Message(
        message_id="msg_1", instance_id="dlg", turn_id=1, role_id="a", participant_id="a",
        speaker_kind=s.RoleKind.AGENT, content="first", created_at=_TS))
    store.append("dlg", ev(4, s.EventType.CONTRIBUTION_RECORDED, message_id="msg_1", role_id="a"))
    return store


async def test_resume_continues_without_re_bootstrapping() -> None:
    store = _seed_running_instance()
    orch = Orchestrator(
        store=store,
        template=s.DialogueTemplate(
            template_id="t", version="1.0.0", title="T",
            termination_policy=s.TerminationPolicy(condition="done"),
            roles=[_agent("a")], orchestration=s.Orchestration(mode=s.OrchestrationMode.PLAN),
        ),
        instance_id="dlg", cast={"a": "a"},
        participants={"a": s.Participant(
            participant_id="a", kind=s.RoleKind.AGENT, display_name="A")},
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"},
        ]),
        agent_providers={"a": MockProvider(texts=["second"])},
    )
    inst = await orch.run()

    assert inst.status is s.InstanceStatus.DONE
    # prior message preserved + new one appended; resume picked up at turn 2
    assert [m.content for m in inst.messages] == ["first", "second"]
    assert inst.messages[-1].turn_id == 2
    # bootstrap events are NOT duplicated on resume
    started = [e for e in inst.events if e.type is s.EventType.INSTANCE_STARTED]
    assert len(started) == 1


async def test_resume_on_terminal_instance_is_noop() -> None:
    store = _seed_running_instance()
    store.append("dlg", s.Event(
        event_id="term", instance_id="dlg", type=s.EventType.INSTANCE_TERMINATED,
        payload={"status": "done", "reason": "finished"}, created_at=_TS))
    orch = Orchestrator(
        store=store,
        template=s.DialogueTemplate(
            template_id="t", version="1.0.0", title="T",
            termination_policy=s.TerminationPolicy(condition="done"), roles=[_agent("a")]),
        instance_id="dlg", cast={"a": "a"},
        participants={"a": s.Participant(
            participant_id="a", kind=s.RoleKind.AGENT, display_name="A")},
        provider=MockProvider(),                 # must not be consulted
        agent_providers={"a": MockProvider()},
    )
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.DONE
    assert [m.content for m in inst.messages] == ["first"]     # unchanged
