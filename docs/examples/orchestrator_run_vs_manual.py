#!/usr/bin/env python3
"""Two ways to create an orchestrator: the `Server.run` convenience vs. building it by hand.

`Server.run` is the usual path — it constructs the Orchestrator for you (derives each agent's
provider, wires oversight/gateway) and auto-resumes a partway instance. Constructing
`Orchestrator(...)` yourself gives full control over every collaborator. Both drive the same
dialogue to the same terminal state. Deterministic, key-free (MockProvider).

Run:  python docs/examples/orchestrator_run_vs_manual.py
"""
from __future__ import annotations

import asyncio

from dcp import Server
from dcp import schema as s
from dcp.orchestration import Orchestrator
from dcp.provider import MockProvider

TEMPLATE = s.DialogueTemplate(
    template_id="two-agent", version="1.0.0", title="Two-agent chat",
    goal="Exchange one line each.",
    termination_policy=s.TerminationPolicy(condition="both spoke", max_turns=4),
    roles=[
        s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
               response_requirement=s.ResponseRequirement.REQUIRED),
        s.Role(role_id="b", name="B", kind=s.RoleKind.AGENT,
               response_requirement=s.ResponseRequirement.REQUIRED),
    ],
)
REF = s.TemplateRef(template_id="two-agent", version="1.0.0")
PARTICIPANTS = [
    s.Participant(participant_id="a", kind=s.RoleKind.AGENT, display_name="A"),
    s.Participant(participant_id="b", kind=s.RoleKind.AGENT, display_name="B"),
]


def _plan_mock() -> MockProvider:
    # plan mode asks the orchestrator's provider for an OrchestratorAction each turn — script them.
    return MockProvider(structured_queue=[
        {"action": "select_speaker", "target_role_id": "a"},
        {"action": "select_speaker", "target_role_id": "b"},
        {"action": "stop", "status": "done"},
    ])


def _agents() -> dict[str, MockProvider]:
    return {"a": MockProvider(texts=["Hi from A."]), "b": MockProvider(texts=["Hi from B."])}


def _line(label: str, inst: s.DialogueInstance) -> str:
    body = " | ".join(f"{m.role_id}:{m.content}" for m in inst.messages)
    return f"{label}: status={inst.status.value} turns={inst.turn}  ->  {body}"


async def main() -> None:
    server = Server(database_url="sqlite:///:memory:")
    server.register_template(TEMPLATE)
    for p in PARTICIPANTS:
        server.register_participant(p)

    # --- Way 1: Server.run builds and runs the orchestrator for you ----------------------
    server.instantiate(REF, owner="a", instance_id="auto")
    auto = await server.run("auto", cast={"a": "a", "b": "b"},
                            orchestrator_provider=_plan_mock(), agent_providers=_agents())
    print(_line("Way 1 — Server.run (auto)     ", auto))

    # --- Way 2: construct the Orchestrator by hand (same store) --------------------------
    server.instantiate(REF, owner="a", instance_id="manual")
    orch = Orchestrator(
        store=server.store, template=TEMPLATE, instance_id="manual",
        cast={"a": "a", "b": "b"},
        participants={p.participant_id: p for p in PARTICIPANTS},
        provider=_plan_mock(),                 # the orchestrator's own model (plan decisions)
        agent_providers=_agents(),
        # also available: oversight=…, human_gateway=…, control_policy=…,
        #                 max_recovery_attempts=…, max_revisions=…
    )
    manual = await orch.run()
    print(_line("Way 2 — Orchestrator(...) by hand", manual))


if __name__ == "__main__":
    asyncio.run(main())
