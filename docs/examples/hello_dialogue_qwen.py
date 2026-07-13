#!/usr/bin/env python3
"""Explicitly bind orchestrator + agents to a local Qwen TransformersProvider.

This script demonstrates the local / in-process Qwen setup you asked for:
- orchestrator uses a local Qwen model via TransformersProvider
- agents also use local Qwen models via TransformersProvider

Requirements:
  pip install -e "./sdk[transformers]"

This will download the model the first time it runs, so it may take a while.

Run from the repo root:
  python docs/examples/hello_dialogue_qwen.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add sdk to path
sys.path.insert(0, str(Path(__file__).parent.parent / "sdk" / "src"))

from dcp import Server, load_dotenv
from dcp import schema as s
from dcp.orchestration import HumanReply, ScriptedHumanGateway
from dcp.provider import TransformersProvider


TEMPLATE = s.DialogueTemplate(
    template_id="design-review",
    version="1.0.0",
    title="Product-name design review",
    goal="Agree on a product name the founder approves.",
    termination_policy=s.TerminationPolicy(condition="founder approves", max_turns=6),
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

    server.instantiate(
        s.TemplateRef(template_id="design-review", version="1.0.0"),
        owner="founder",
        instance_id="demo-qwen",
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
