"""DCP hello-world (real model): the same design review, driven by a live provider.

Run:  python docs/examples/hello_dialogue.py

Needs a provider key + model in the environment (or a local ``.env``):
    DCP_MODEL_PROVIDER=openai        # or anthropic
    OPENAI_API_KEY=sk-...            # (ANTHROPIC_API_KEY for anthropic)
    DCP_MODEL=gpt-5.4                # the model id for that provider

The orchestrator's model decides who speaks and when to stop (plan mode); each agent's model
produces its contribution; the founder's approval is scripted here so the example is
non-interactive. For a zero-setup version, run ``hello_dialogue_mock.py`` instead.
"""

from __future__ import annotations

import asyncio

from dcp import Server, load_dotenv
from dcp import schema as s
from dcp.orchestration import HumanReply, ScriptedHumanGateway

TEMPLATE = s.DialogueTemplate(
    template_id="design-review",
    version="1.0.0",
    title="Product-name design review",
    goal="Agree on a product name the founder approves.",
    termination_policy=s.TerminationPolicy(condition="founder approves", max_turns=6),
    roles=[
        s.Role(role_id="proposer", name="Proposer", kind=s.RoleKind.AGENT,
               persona="You propose candidate product names, one at a time, each with a rationale.",
               response_requirement=s.ResponseRequirement.REQUIRED),
        s.Role(role_id="critic", name="Critic", kind=s.RoleKind.AGENT,
               persona="You critique proposed names for clarity, memorability, and trademark risk.",
               response_requirement=s.ResponseRequirement.REQUIRED),
        s.Role(role_id="founder", name="Founder", kind=s.RoleKind.HUMAN,
               persona="You approve or reject the chosen name.",
               response_requirement=s.ResponseRequirement.GATE),
    ],
)


async def main() -> None:
    load_dotenv()                                          # pick up keys/model from .env if present
    server = Server(database_url="sqlite:///:memory:")

    info = server.server_info()
    configured = [p.provider for p in info.model_providers if p.configured]
    if server.config.model_provider not in configured:
        raise SystemExit(
            f"provider {server.config.model_provider!r} has no key configured; "
            f"set it in the environment or run hello_dialogue_mock.py (configured: {configured})"
        )

    server.register_template(TEMPLATE)
    for pid, kind in (("proposer", s.RoleKind.AGENT), ("critic", s.RoleKind.AGENT),
                      ("founder", s.RoleKind.HUMAN)):
        server.register_participant(
            s.Participant(participant_id=pid, kind=kind, display_name=pid.title())
        )
    server.instantiate(
        s.TemplateRef(template_id="design-review", version="1.0.0"),
        owner="founder", instance_id="demo",
    )

    result = await server.run(
        "demo",
        cast={"proposer": "proposer", "critic": "critic", "founder": "founder"},
        # No scripted providers: orchestrator + agents use the configured model (plan mode).
        human_gateway=ScriptedHumanGateway(
            {"founder": HumanReply(content="Approved — ship it.", decision="approve")}
        ),
    )

    print(f"status: {result.status.value}  (turns: {result.turn})")
    for m in result.messages:
        print(f"  {m.role_id}: {m.content}")


if __name__ == "__main__":
    asyncio.run(main())
