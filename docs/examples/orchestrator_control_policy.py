#!/usr/bin/env python3
"""The orchestrator's "brain" is a pluggable ControlPolicy — three ways to pick the next speaker.

- PlanPolicy  (mode=plan, the default): emergent — asks the orchestrator's model each turn.
- FlowPolicy  (mode=flow): guided — follows the template's declared flow graph (a linear graph is
  deterministic, so no model decision is needed).
- a custom policy: implement `async decide(ctx) -> OrchestratorAction`; pass it to `run(...)` and it
  wins over the template's mode. Here a round-robin policy uses no model at all.

"Policy proposes, runtime disposes": whatever the policy returns, the orchestrator still applies
oversight, recovery, and termination around it. Deterministic, key-free.

Run:  python docs/examples/orchestrator_control_policy.py
"""
from __future__ import annotations

import asyncio

from dcp import Server
from dcp import schema as s
from dcp.orchestration import DialogueContext, OrchestratorAction
from dcp.provider import MockProvider


def _roles() -> list[s.Role]:
    return [
        s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
               response_requirement=s.ResponseRequirement.REQUIRED),
        s.Role(role_id="b", name="B", kind=s.RoleKind.AGENT,
               response_requirement=s.ResponseRequirement.REQUIRED),
    ]


class RoundRobinPolicy:
    """Each role speaks once in template order, then stop — no model at all."""

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        spoken = {m.role_id for m in ctx.messages}
        for role in ctx.roles:
            if role.role_id not in spoken:
                return OrchestratorAction(action="select_speaker", target_role_id=role.role_id)
        return OrchestratorAction(action="stop", status=s.TerminationStatus.DONE)


async def _run(template: s.DialogueTemplate, *, orchestrator_provider: MockProvider,
               control_policy: object | None = None) -> s.DialogueInstance:
    server = Server(database_url="sqlite:///:memory:")
    server.register_template(template)
    for pid in ("a", "b"):
        server.register_participant(
            s.Participant(participant_id=pid, kind=s.RoleKind.AGENT, display_name=pid.upper()))
    server.instantiate(s.TemplateRef(template_id=template.template_id, version="1.0.0"),
                       owner="a", instance_id="demo")
    return await server.run(
        "demo", cast={"a": "a", "b": "b"}, orchestrator_provider=orchestrator_provider,
        agent_providers={"a": MockProvider(texts=["A speaks"]), "b": MockProvider(texts=["B speaks"])},
        control_policy=control_policy)   # type: ignore[arg-type]


async def main() -> None:
    # 1) PlanPolicy — script the model's per-turn decisions (mode=plan is the default).
    plan_tmpl = s.DialogueTemplate(
        template_id="plan-demo", version="1.0.0", title="Plan", goal="chat",
        termination_policy=s.TerminationPolicy(condition="done", max_turns=4), roles=_roles(),
        orchestration=s.Orchestration(mode=s.OrchestrationMode.PLAN))
    plan = await _run(plan_tmpl, orchestrator_provider=MockProvider(structured_queue=[
        {"action": "select_speaker", "target_role_id": "a"},
        {"action": "select_speaker", "target_role_id": "b"},
        {"action": "stop", "status": "done"}]))
    print("PlanPolicy   (emergent, model-driven) ->", [m.role_id for m in plan.messages],
          plan.status.value)

    # 2) FlowPolicy — a linear flow a->b is deterministic, so the model is never consulted.
    flow_tmpl = s.DialogueTemplate(
        template_id="flow-demo", version="1.0.0", title="Flow", goal="chat",
        termination_policy=s.TerminationPolicy(condition="done", max_turns=4), roles=_roles(),
        orchestration=s.Orchestration(mode=s.OrchestrationMode.FLOW),
        flow=s.Flow(entry="a", edges=[s.Edge(from_role="a", to_role="b")]))
    flow = await _run(flow_tmpl, orchestrator_provider=MockProvider())   # unused in a linear flow
    print("FlowPolicy   (guided by the graph)    ->", [m.role_id for m in flow.messages],
          flow.status.value)

    # 3) Custom policy — pass control_policy=…; it wins over the template's mode. No model.
    custom_tmpl = s.DialogueTemplate(
        template_id="custom-demo", version="1.0.0", title="Custom", goal="chat",
        termination_policy=s.TerminationPolicy(condition="done", max_turns=4), roles=_roles())
    custom = await _run(custom_tmpl, orchestrator_provider=MockProvider(),
                        control_policy=RoundRobinPolicy())
    print("RoundRobin   (custom, no model)       ->", [m.role_id for m in custom.messages],
          custom.status.value)


if __name__ == "__main__":
    asyncio.run(main())
