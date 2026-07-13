#!/usr/bin/env python3
"""Mix providers in one dialogue — a local Qwen orchestrator with OpenAI agents.

This demonstrates that provider selection is per-role (see docs/01-quickstart.md and 05-participant):
- orchestrator → a local Qwen model, in-process via TransformersProvider (passed as an instance)
- proposer / critic → OpenAI, bound declaratively per participant via `model_binding` (D8)
- founder → a human role, no model binding

Requirements:
  pip install -e "./sdk[transformers]"   # for the local Qwen orchestrator
  OPENAI_API_KEY in the environment      # for the two OpenAI agents

The first run downloads the Qwen weights, so it may take a while.

Run from the repo root:
  python docs/examples/hello_dialogue_qwen.py
"""

from __future__ import annotations

import asyncio

from dcp import Server, load_dotenv
from dcp import schema as s
from dcp.orchestration import HumanReply, ScriptedHumanGateway
from dcp.provider import TransformersProvider


# Template = the reusable *pattern*: a generic title/goal/termination that fit any design review,
# not one task. The run-specific objective and task details are supplied per-instance (see the
# `goal=` / `termination=` / `brief=` on instantiate below).
TEMPLATE = s.DialogueTemplate(
    template_id="design-review",
    version="1.0.0",
    title="Design review",
    goal="Converge on a proposal the designated approver signs off on.",
    termination_policy=s.TerminationPolicy(condition="the approver approves", max_turns=8),
    roles=[
        s.Role(
            role_id="proposer",
            name="Proposer",
            kind=s.RoleKind.AGENT,
            persona="You propose candidate product names, one at a time, each with a rationale.",
            response_requirement=s.ResponseRequirement.REQUIRED,
        ),
        s.Role(
            role_id="critic",
            name="Critic",
            kind=s.RoleKind.AGENT,
            persona="You critique proposed names for clarity, memorability, and trademark risk.",
            response_requirement=s.ResponseRequirement.REQUIRED,
        ),
        s.Role(
            role_id="founder",
            name="Founder",
            kind=s.RoleKind.HUMAN,
            persona="You approve or reject the chosen name.",
            response_requirement=s.ResponseRequirement.GATE,
        ),
    ],
)


async def main() -> None:
    print("=" * 70)
    print("Explicit Qwen TransformersProvider demo")
    print("=" * 70)

    # Choose a local Hugging Face model repo.
    # You can change this to a smaller model if your machine is limited.
    model_name = "Qwen/Qwen3-4B-Instruct-2507"

    print(f"Using orchestrator model: {model_name}")
    print("This will load the orchestrator model locally via transformers/torch.")
    print("The first run may take a while while weights are downloaded.")
    print("Note: proposer and critic will use per-agent OpenAI model bindings.")

    load_dotenv()

    # Build explicit orchestrator provider.
    orchestrator_provider = TransformersProvider(model_name, enable_thinking=False, max_new_tokens=512)

    # Per-agent model bindings (D8): None means inherit orchestrator default.
    AGENT_MODELS: dict[str, s.ModelBinding] = {
        "proposer": s.ModelBinding(provider="openai", model="gpt-4o-mini"),
        "critic": s.ModelBinding(provider="openai", model="gpt-4o-mini"),
    }

    server = Server(database_url="sqlite:///:memory:")  
    # memory DB for demo; use a file for persistent storage, e.g. sqlite:///./dcp.db
    # dcp show <instance_id> --db sqlite:///./dcp.db --timeline
    server.register_template(TEMPLATE)

    for pid, kind in (("proposer", s.RoleKind.AGENT), ("critic", s.RoleKind.AGENT), ("founder", s.RoleKind.HUMAN)):
        server.register_participant(
            s.Participant(
                participant_id=pid,
                kind=kind,
                display_name=pid.title(),
                model_binding=AGENT_MODELS.get(pid),
            )
        )

    # Aim the generic template at *this* run: goal + termination override the template's defaults,
    # and brief carries the task specifics — all reach the orchestrator and every agent.
    server.instantiate(
        s.TemplateRef(template_id="design-review", version="1.0.0"),
        owner="founder",
        instance_id="demo-qwen",
        goal="Agree on a product name the founder approves.",
        termination=s.TerminationPolicy(condition="the founder approves the name", max_turns=6),
        brief={
            "product": "a B2B analytics platform for fintech CFOs",
            "constraints": ["one or two words", "avoid the '-ly' suffix", "low trademark risk"],
        },
    )

    result = await server.run(
        "demo-qwen",
        cast={"proposer": "proposer", "critic": "critic", "founder": "founder"},
        orchestrator_provider=orchestrator_provider,
        human_gateway=ScriptedHumanGateway(
            {"founder": HumanReply(content="Approved — ship it.", decision="approve")}
        ),
    )

    print("\nResult:")
    print(f"status: {result.status.value}  (turns: {result.turn})")
    for message in result.messages:
        print(f"  {message.role_id}: {message.content}")


if __name__ == "__main__":
    asyncio.run(main())
