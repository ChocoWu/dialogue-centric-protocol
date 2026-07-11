"""`suspend` pauses a run without terminating; a later run() resumes it (SPEC §1.7, §2.9)."""

from __future__ import annotations

from datetime import UTC, datetime

from dcp import schema as s
from dcp.orchestration import DialogueContext, Orchestrator, OrchestratorAction
from dcp.provider import MockProvider
from dcp.state import InstanceHeader, SqlStore

_TS = datetime(2026, 7, 11, tzinfo=UTC)


def _agent(rid: str) -> s.Role:
    return s.Role(role_id=rid, name=rid, kind=s.RoleKind.AGENT,
                  response_requirement=s.ResponseRequirement.REQUIRED)


class _SuspendAfterFirst:
    """Session 1: let one agent speak, then suspend (pause the dialogue)."""

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        if not ctx.messages:
            return OrchestratorAction(action="select_speaker", target_role_id="a")
        return OrchestratorAction(action="suspend", reason="pause for the day")


class _RunToEnd:
    """Session 2: run the remaining roles to completion."""

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        spoken = {m.role_id for m in ctx.messages}
        for rid in ("a", "b"):
            if rid not in spoken:
                return OrchestratorAction(action="select_speaker", target_role_id=rid)
        return OrchestratorAction(action="stop", status=s.TerminationStatus.DONE)


def _store() -> SqlStore:
    store = SqlStore()
    store.create_instance(InstanceHeader(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@o", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0", created_at=_TS))
    return store


def _orch(store: SqlStore, policy: object) -> Orchestrator:
    tmpl = s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done", max_turns=6),
        roles=[_agent("a"), _agent("b")])
    return Orchestrator(
        store=store, template=tmpl, instance_id="dlg", cast={"a": "a", "b": "b"},
        participants={r: s.Participant(participant_id=r, kind=s.RoleKind.AGENT, display_name=r)
                      for r in ("a", "b")},
        provider=MockProvider(),
        agent_providers={"a": MockProvider(texts=["a speaks"]),
                         "b": MockProvider(texts=["b speaks"])},
        control_policy=policy)  # type: ignore[arg-type]


async def test_suspend_leaves_a_resumable_instance_then_resumes_to_done() -> None:
    store = _store()

    # session 1: one turn, then suspend
    paused = await _orch(store, _SuspendAfterFirst()).run()
    assert paused.status is s.InstanceStatus.RUNNING          # non-terminal → resumable
    assert s.is_resumable(paused.status)
    assert s.EventType.INSTANCE_SUSPENDED in {e.type for e in paused.events}
    assert [m.content for m in paused.messages] == ["a speaks"]
    assert s.EventType.INSTANCE_TERMINATED not in {e.type for e in paused.events}

    # session 2: a fresh orchestrator over the same store resumes and finishes
    done = await _orch(store, _RunToEnd()).run()
    assert done.status is s.InstanceStatus.DONE
    assert [m.content for m in done.messages] == ["a speaks", "b speaks"]   # continued, not reset
