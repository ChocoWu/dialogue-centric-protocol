"""DCP hello-world (key-free): a 3-role design review that runs with NO API key.

Run:  python docs/examples/hello_dialogue_mock.py

Uses ``MockProvider`` for deterministic, offline output so anyone can see a full DCP dialogue —
template → participants → instance → orchestrated turns → human approval gate → terminal status —
without credentials. The real-model version is ``hello_dialogue.py``.
"""

from __future__ import annotations

import asyncio

from dcp import Server
from dcp import schema as s
from dcp.orchestration import HumanReply, ScriptedHumanGateway
from dcp.provider import MockProvider

TEMPLATE = s.DialogueTemplate(
    template_id="design-review",
    version="1.0.0",
    # Generic, reusable pattern — the specific objective is set per-instance (see instantiate).
    title="Design review",
    goal="Converge on a proposal the designated approver signs off on.",
    termination_policy=s.TerminationPolicy(condition="approver approves", max_turns=6),
    roles=[
        s.Role(role_id="proposer", name="Proposer", kind=s.RoleKind.AGENT,
               persona="Proposes candidate product names.",
               response_requirement=s.ResponseRequirement.REQUIRED),
        s.Role(role_id="critic", name="Critic", kind=s.RoleKind.AGENT,
               persona="Critiques names for clarity and risk.",
               response_requirement=s.ResponseRequirement.REQUIRED),
        s.Role(role_id="founder", name="Founder", kind=s.RoleKind.HUMAN,
               persona="Approves or rejects the chosen name.",
               response_requirement=s.ResponseRequirement.GATE),
    ],
)


async def main() -> None:
    server = Server(database_url="sqlite:///:memory:")     # in-memory: nothing to clean up
    server.register_template(TEMPLATE)
    for pid, kind in (("proposer", s.RoleKind.AGENT), ("critic", s.RoleKind.AGENT),
                      ("founder", s.RoleKind.HUMAN)):
        server.register_participant(
            s.Participant(participant_id=pid, kind=kind, display_name=pid.title())
        )

    server.instantiate(
        s.TemplateRef(template_id="design-review", version="1.0.0"),
        owner="founder", instance_id="demo",
        # This run's concrete objective (overrides the template's generic goal) + task specifics.
        goal="Agree on a product name the founder approves.",
        brief={"product": "a developer-tools startup", "constraints": ["one word", "memorable"]},
    )

    providers = [p.provider for p in server.server_info().model_providers if p.configured]
    print(f"configured providers: {providers}\n")

    result = await server.run(
        "demo",
        cast={"proposer": "proposer", "critic": "critic", "founder": "founder"},
        # Scripted for determinism; a real model would decide these (see hello_dialogue.py).
        orchestrator_provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "proposer"},
            {"action": "select_speaker", "target_role_id": "critic"},
            {"action": "select_speaker", "target_role_id": "founder"},
            {"action": "stop", "status": "done"},
        ]),
        agent_providers={
            "proposer": MockProvider(texts=["I propose 'Northstar'."]),
            "critic": MockProvider(texts=["'Northstar' is clear and low trademark risk. +1."]),
        },
        human_gateway=ScriptedHumanGateway(
            {"founder": HumanReply(content="Approved — ship it.", decision="approve")}
        ),
    )

    print(f"status: {result.status.value}  (turns: {result.turn})")
    for m in result.messages:
        print(f"  {m.role_id}: {m.content}")


if __name__ == "__main__":
    asyncio.run(main())
