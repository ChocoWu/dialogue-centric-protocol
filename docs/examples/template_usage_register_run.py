#!/usr/bin/env python3
"""Demonstrate registering a template, creating an instance with per-run overrides,
binding participants, and running with MockProvider + ScriptedHumanGateway.

Run:
  python docs/examples/template_usage_register_run.py
"""
import asyncio

from dcp import Server, load_dotenv
from dcp import schema as s
from dcp.orchestration import HumanReply, ScriptedHumanGateway
from dcp.provider import MockProvider


TEMPLATE = s.DialogueTemplate(
    template_id="usage-demo",
    version="1.0.0",
    title="Usage demo",
    goal="Pick one of the suggested names.",
    termination_policy=s.TerminationPolicy(condition="owner approves", max_turns=6),
    roles=[
        s.Role(role_id="proposer", name="Proposer", kind=s.RoleKind.AGENT,
               persona="Propose names.", response_requirement=s.ResponseRequirement.REQUIRED),
        s.Role(role_id="owner", name="Owner", kind=s.RoleKind.HUMAN,
               persona="Approve or reject.", response_requirement=s.ResponseRequirement.GATE),
    ],
)


async def main() -> None:
    load_dotenv()

    server = Server(database_url="sqlite:///:memory:")
    # register template
    server.register_template(TEMPLATE)
    print("Registered template 'usage-demo'")

    # register participants with per-agent model bindings
    server.register_participant(s.Participant(participant_id="proposer", kind=s.RoleKind.AGENT,
                                              display_name="Proposer", model_binding=s.ModelBinding(provider="mock", model="echo")))
    server.register_participant(s.Participant(participant_id="owner", kind=s.RoleKind.HUMAN,
                                              display_name="Owner"))
    print("Registered participants: proposer, owner")

    # instantiate with per-run overrides (goal + brief + termination)
    inst = server.instantiate(s.TemplateRef(template_id="usage-demo", version="1.0.0"),
                              owner="owner",
                              goal="Select a short brandable name.",
                              termination=s.TerminationPolicy(condition="owner approves", max_turns=4))
    print(f"Instantiated instance: {inst.instance_id}")

    # Run deterministically: the template is in `plan` mode, so the orchestrator asks its provider
    # for an OrchestratorAction each turn — script those decisions on the MockProvider (proposer
    # speaks, then the owner gate, then stop). A bare MockProvider() would raise here because it has
    # no scripted structured response for OrchestratorAction. (The proposer's own mock model — bound
    # via its `model_binding` above — needs no script; MockProvider.text() falls back to a stub.)
    orchestrator_provider = MockProvider(structured_queue=[
        {"action": "select_speaker", "target_role_id": "proposer"},
        {"action": "select_speaker", "target_role_id": "owner"},
        {"action": "stop", "status": "done"},
    ])

    result = await server.run(
        inst.instance_id,
        cast={"proposer": "proposer", "owner": "owner"},
        orchestrator_provider=orchestrator_provider,
        human_gateway=ScriptedHumanGateway(
            {"owner": HumanReply(content="Approved — ship it.", decision="approve")}),
    )

    print("\nRun result:")
    print(f" status: {result.status.value} (turns: {result.turn})")
    for m in result.messages:
        print(f"  {m.role_id}: {m.content}")

    # Demonstrate restore from the same server
    restored = server.registry.restore(inst.instance_id)
    print("\nRestored instance status:", restored.status.value)


if __name__ == "__main__":
    asyncio.run(main())
