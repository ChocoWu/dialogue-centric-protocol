"""M9 — DCP conformance vectors: one test per SPEC §6 acceptance criterion.

This suite is the executable form of SPEC §5/§6: each test maps to a named criterion and asserts
a MUST. It intentionally re-expresses behavior covered by unit tests as the canonical conformance
surface for a single-node deployment.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dcp import schema as s
from dcp.errors import AccessError, AuthError, OrchestrationError, RegistryError
from dcp.orchestration import (
    Orchestrator,
    ScriptedHumanGateway,
    ScriptedOversight,
    resolve_termination,
)
from dcp.provider import MockProvider
from dcp.registry import AnonymousAuthenticator, Registry, SimpleTokenAuthenticator
from dcp.schema import TerminationStatus as T
from dcp.state import InstanceHeader, SqlStore, replay, restore

_TS = datetime(2026, 7, 10, tzinfo=UTC)


# --- fixtures -----------------------------------------------------------------------------

def _role(rid: str, kind: s.RoleKind, req: s.ResponseRequirement) -> s.Role:
    return s.Role(role_id=rid, name=rid, kind=kind, response_requirement=req)


def _template(
    *, visibility: s.Visibility | None = None, max_turns: int | None = None,
    allow_open_mic: bool = False, roles: list[s.Role] | None = None,
) -> s.DialogueTemplate:
    return s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done", max_turns=max_turns),
        default_visibility=visibility, allow_open_mic=allow_open_mic,
        roles=roles or [_role("a", s.RoleKind.AGENT, s.ResponseRequirement.REQUIRED)],
    )


def _registry(**tmpl_kw: object) -> Registry:
    reg = Registry(SqlStore())
    reg.register_template(_template(**tmpl_kw))  # type: ignore[arg-type]
    return reg


def _ref() -> s.TemplateRef:
    return s.TemplateRef(template_id="t", version="1.0.0")


def _header(iid: str = "dlg", *, visibility: s.Visibility = s.Visibility.PRIVATE) -> InstanceHeader:
    return InstanceHeader(
        instance_id=iid, template_ref=_ref(), owner="@o",
        visibility=visibility, dcp_version="0.2.0", created_at=_TS)


def _ev(i: int, t: s.EventType, **p: object) -> s.Event:
    return s.Event(event_id=f"e{i}", instance_id="dlg", type=t, payload=p, created_at=_TS)


# --- §6 criteria --------------------------------------------------------------------------

def test_template_immutability() -> None:
    reg = _registry()
    with pytest.raises(RegistryError):
        reg.register_template(_template(max_turns=99))          # same (id,version), changed content
    reg.register_template(s.DialogueTemplate(                    # new version MUST succeed
        template_id="t", version="2.0.0", title="T2",
        termination_policy=s.TerminationPolicy(condition="done"),
        roles=[_role("a", s.RoleKind.AGENT, s.ResponseRequirement.REQUIRED)]))
    assert reg.get_template("t", "2.0.0") is not None


def test_instantiation_ownership_and_created_status() -> None:
    reg = _registry()
    inst = reg.instantiate(_ref(), owner="@o", instance_id="dlg")
    assert inst.owner == "@o" and inst.status is s.InstanceStatus.CREATED


def test_first_control_action_transitions_to_running() -> None:
    store = SqlStore()
    store.create_instance(_header())
    store.append("dlg", _ev(0, s.EventType.INSTANCE_CREATED))
    assert restore(store, "dlg").status is s.InstanceStatus.CREATED
    store.append("dlg", _ev(1, s.EventType.INSTANCE_STARTED))    # first control action
    assert restore(store, "dlg").status is s.InstanceStatus.RUNNING


def test_observe_tier_not_castable_into_speak_role() -> None:
    from dcp.participation import assert_castable
    with pytest.raises(AccessError):
        assert_castable(s.AccessTier.OBSERVE)


def test_open_mic_rejected_unless_template_enables() -> None:
    store = SqlStore()
    store.create_instance(_header())
    common = dict(store=store, instance_id="dlg", cast={"a": "a"},
                  participants={"a": s.Participant(
                      participant_id="a", kind=s.RoleKind.AGENT, display_name="A")},
                  provider=MockProvider())
    with pytest.raises(OrchestrationError):
        Orchestrator(template=_template(allow_open_mic=False), **common).submit_open_mic(
            "i1", "hi", "@obs")
    # enabled: accepted and pending
    Orchestrator(template=_template(allow_open_mic=True), **common).submit_open_mic(
        "i1", "hi", "@obs")
    assert restore(store, "dlg").pending_inputs[0].addressed is False


def test_visibility_join_rules() -> None:
    pub = _registry(visibility=s.Visibility.PUBLIC)
    pub.instantiate(_ref(), owner="@o", instance_id="dlg")
    assert any(r.participant_id == "@g" and r.tier is s.AccessTier.OBSERVE
               for r in pub.join("dlg", participant_id="@g").roster)

    priv = _registry(visibility=s.Visibility.PRIVATE)
    priv.instantiate(_ref(), owner="@o", instance_id="dlg")
    with pytest.raises(AccessError):
        priv.join("dlg", participant_id="@intruder")


def test_restore_is_full_replay_in_order() -> None:
    store = SqlStore()
    store.create_instance(_header())
    for i in range(5):
        store.append("dlg", _ev(i, s.EventType.CONTEXT_INJECTED, n=i))
    events = [e for e in restore(store, "dlg").events]
    assert [e.payload["n"] for e in events] == [0, 1, 2, 3, 4]   # all N, in order


def test_termination_priority_budget_over_done() -> None:
    assert resolve_termination(over_budget=True, done=True) is T.BUDGET


async def test_gate_timeout_yields_provisional() -> None:
    store = SqlStore()
    store.create_instance(_header())
    founder = s.Role(role_id="f", name="F", kind=s.RoleKind.HUMAN,
                     response_requirement=s.ResponseRequirement.GATE,
                     human_policy=s.HumanPolicy(wait_window_seconds=1,
                                                on_timeout=s.OnTimeout.FINALIZE_PROVISIONAL))
    orch = Orchestrator(
        store=store, template=_template(roles=[founder]), instance_id="dlg",
        cast={"f": "@f"},
        participants={"@f": s.Participant(participant_id="@f", kind=s.RoleKind.HUMAN,
                                          display_name="F")},
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "f"}]),
        human_gateway=ScriptedHumanGateway({}),             # never replies -> timeout
    )
    assert (await orch.run()).status is s.InstanceStatus.PROVISIONAL


def test_auth_bearer_resolves_one_id_and_anon_is_synthetic() -> None:
    bearer = SimpleTokenAuthenticator({"tok": "@alice"})
    assert bearer.authenticate("tok") == "@alice"
    with pytest.raises(AuthError):
        bearer.authenticate(None)
    assert AnonymousAuthenticator().authenticate(None) == "@local"


def test_replay_determinism_reproduces_status_turn_roster() -> None:
    records = [
        _ev(0, s.EventType.INSTANCE_STARTED),
        _ev(1, s.EventType.ROLES_CAST, roles=[{"role_id": "a", "participant_id": "@a"}]),
        _ev(2, s.EventType.TURN_ASSIGNED, target_role_id="a", turn=1),
    ]
    a = replay(_header(), list(records))
    b = replay(_header(), list(records))
    assert (a.status, a.turn, [r.participant_id for r in a.roster]) == \
           (b.status, b.turn, [r.participant_id for r in b.roster])


async def test_resume_continues_a_running_instance() -> None:
    store = SqlStore()
    store.create_instance(_header())
    store.append("dlg", _ev(0, s.EventType.INSTANCE_STARTED))
    store.append("dlg", _ev(1, s.EventType.ROLES_CAST,
                            roles=[{"role_id": "a", "participant_id": "a"}]))
    store.append("dlg", _ev(2, s.EventType.PARTICIPANT_JOINED, participant_id="a", tier="speak"))
    orch = Orchestrator(
        store=store, template=_template(), instance_id="dlg", cast={"a": "a"},
        participants={"a": s.Participant(participant_id="a", kind=s.RoleKind.AGENT,
                                         display_name="A")},
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"}]),
        agent_providers={"a": MockProvider(texts=["resumed contribution"])},
    )
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.DONE
    assert [e for e in inst.events if e.type is s.EventType.INSTANCE_STARTED].__len__() == 1


def test_server_info_advertises_version_and_providers() -> None:
    info = Registry(SqlStore()).server_info(env={})
    assert info.dcp_version == "0.2.0"
    assert {p.provider for p in info.model_providers} == {"openai", "anthropic", "mock"}


async def test_oversight_governs_control_pre_recovery_and_post_routing() -> None:
    # D11: a not-ready pre triggers recovery (context_injected); a request_revision post re-invokes.
    store = SqlStore()
    store.create_instance(_header())
    pre_bad = s.PreActionVerification(
        readiness="not_ready", availability="available", capability_match="high",
        role_state="needed", context_sufficiency="insufficient",
        execution_feasibility="feasible", recommended_action="inject_context",
        issues=[s.Issue(type="gap", description="missing context")])
    pre_ok = s.PreActionVerification(
        readiness="ready", availability="available", capability_match="high",
        role_state="needed", context_sufficiency="sufficient",
        execution_feasibility="feasible", recommended_action="select_speaker")
    post_revise = s.PostActionVerification(
        verdict="revise", relevance="ok", role_consistency="ok", completeness="weak",
        grounding="ok", safety="ok", human_input_addressed=True, outcome="request_revision")
    post_ok = s.PostActionVerification(
        verdict="pass", relevance="ok", role_consistency="ok", completeness="ok",
        grounding="ok", safety="ok", human_input_addressed=True, outcome="continue")
    orch = Orchestrator(
        store=store, template=_template(), instance_id="dlg", cast={"a": "a"},
        participants={"a": s.Participant(participant_id="a", kind=s.RoleKind.AGENT,
                                         display_name="A")},
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"}]),
        agent_providers={"a": MockProvider(texts=["draft", "revised"])},
        oversight=ScriptedOversight(pre=[pre_bad, pre_ok], post=[post_revise, post_ok]),
    )
    inst = await orch.run()
    types_ = {e.type for e in inst.events}
    assert s.EventType.CONTEXT_INJECTED in types_          # pre → recovery
    assert s.EventType.REVISION_REQUESTED in types_        # post → routing
    assert [m.content for m in inst.messages] == ["draft", "revised"]
    assert inst.status is s.InstanceStatus.DONE
