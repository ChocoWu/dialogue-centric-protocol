"""Phase 6.1b — the ControlPolicy seam: built-ins + a custom orchestrator end-to-end (SPEC §1.7)."""

from __future__ import annotations

from datetime import UTC, datetime

from dcp import schema as s
from dcp.orchestration import (
    ControlPolicy,
    DialogueContext,
    FlowPolicy,
    Orchestrator,
    OrchestratorAction,
    PlanPolicy,
)
from dcp.provider import MockProvider
from dcp.state import InstanceHeader, SqlStore

_TS = datetime(2026, 7, 11, tzinfo=UTC)


def _agent(rid: str) -> s.Role:
    return s.Role(role_id=rid, name=rid, kind=s.RoleKind.AGENT,
                  response_requirement=s.ResponseRequirement.REQUIRED)


def _template(*, mode: s.OrchestrationMode = s.OrchestrationMode.PLAN,
              flow: s.Flow | None = None) -> s.DialogueTemplate:
    return s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done", max_turns=6),
        roles=[_agent("a"), _agent("b")], orchestration=s.Orchestration(mode=mode), flow=flow)


def _msg(role: str, turn: int) -> s.Message:
    return s.Message(
        message_id=f"m{turn}", instance_id="dlg", turn_id=turn, role_id=role,
        participant_id=role, speaker_kind=s.RoleKind.AGENT, content="x", created_at=_TS)


def _ctx(template: s.DialogueTemplate, provider: object, *messages: s.Message) -> DialogueContext:
    inst = s.DialogueInstance(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@o", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0",
        status=s.InstanceStatus.RUNNING, turn=len(messages), roster=[],
        messages=list(messages), events=[], open_gates=[], pending_inputs=[],
        budget=s.Budget(turns_used=len(messages)))
    return DialogueContext.from_instance(inst, template, provider)  # type: ignore[arg-type]


# --- built-in policies -------------------------------------------------------------------

async def test_plan_policy_delegates_to_the_model() -> None:
    provider = MockProvider(structured_queue=[
        {"action": "select_speaker", "target_role_id": "b"}])
    action = await PlanPolicy().decide(_ctx(_template(), provider))
    assert action.action == "select_speaker" and action.target_role_id == "b"


async def test_flow_policy_follows_the_graph() -> None:
    tmpl = _template(mode=s.OrchestrationMode.FLOW,
                     flow=s.Flow(entry="a", edges=[s.Edge(from_role="a", to_role="b")]))
    policy = FlowPolicy()
    # no prior speaker -> entry
    assert (await policy.decide(_ctx(tmpl, MockProvider()))).target_role_id == "a"
    # after a -> edge to b
    assert (await policy.decide(_ctx(tmpl, MockProvider(), _msg("a", 1)))).target_role_id == "b"
    # after b -> no edge -> stop
    end = await policy.decide(_ctx(tmpl, MockProvider(), _msg("a", 1), _msg("b", 2)))
    assert end.action == "stop"


# --- default selection preserves behavior (backward-compat) ------------------------------

def _orch(template: s.DialogueTemplate, *, control_policy: ControlPolicy | None = None,
          provider: MockProvider | None = None) -> Orchestrator:
    store = SqlStore()
    store.create_instance(InstanceHeader(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@o", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0", created_at=_TS))
    return Orchestrator(
        store=store, template=template, instance_id="dlg", cast={"a": "a", "b": "b"},
        participants={r: s.Participant(participant_id=r, kind=s.RoleKind.AGENT, display_name=r)
                      for r in ("a", "b")},
        provider=provider or MockProvider(),
        agent_providers={"a": MockProvider(texts=["A"]), "b": MockProvider(texts=["B"])},
        control_policy=control_policy)


def test_default_policy_is_plan_or_flow_by_mode() -> None:
    assert isinstance(_orch(_template()).control_policy, PlanPolicy)
    flow_tmpl = _template(mode=s.OrchestrationMode.FLOW, flow=s.Flow(entry="a", edges=[]))
    assert isinstance(_orch(flow_tmpl).control_policy, FlowPolicy)


# --- a custom orchestrator drives a dialogue end-to-end, no model needed -----------------

class RoundRobin:
    """A tiny custom ControlPolicy: each role speaks once in order, then stop. No model calls."""

    def __init__(self, order: list[str]) -> None:
        self._order = order

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        spoken = {m.role_id for m in ctx.messages}
        for rid in self._order:
            if rid not in spoken:
                return OrchestratorAction(action="select_speaker", target_role_id=rid)
        return OrchestratorAction(action="stop", status=s.TerminationStatus.DONE)


async def test_custom_control_policy_runs_end_to_end() -> None:
    orch = _orch(_template(), control_policy=RoundRobin(["a", "b"]))
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.DONE
    assert [m.role_id for m in inst.messages] == ["a", "b"]     # policy drove the order


async def test_custom_policy_overrides_plan_mode() -> None:
    # PLAN-mode template, but a custom policy is supplied -> policy wins; model never consulted.
    orch = _orch(_template(), control_policy=RoundRobin(["b", "a"]),
                 provider=MockProvider())  # empty structured queue: would raise if consulted
    inst = await orch.run()
    assert [m.role_id for m in inst.messages] == ["b", "a"]
