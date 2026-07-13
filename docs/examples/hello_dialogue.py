"""DCP hello-world (real model): the same design review, driven by a live provider.

Run:  python docs/examples/hello_dialogue.py

Needs a provider key + model in the environment (or a local ``.env``):
    DCP_MODEL_PROVIDER=openai        # or anthropic
    OPENAI_API_KEY=sk-...            # (ANTHROPIC_API_KEY for anthropic)
    DCP_MODEL=gpt-5.4                # the model id for that provider

The orchestrator's model decides who speaks and when to stop (plan mode); each agent's model
produces its contribution; the founder's approval is scripted here so the example is
non-interactive. For a zero-setup version, run ``hello_dialogue_mock.py`` instead.

By default every agent uses the one provider from ``.env``; see ``AGENT_MODELS`` below to give each
agent its own provider/model (e.g. a Claude proposer and a GPT critic in the same dialogue).
"""

from __future__ import annotations

import asyncio

from dcp import Server, load_dotenv
from dcp import schema as s
from dcp.orchestration import HumanReply, ScriptedHumanGateway

"""Run the hello_dialogue example and validate output."""
print("=" * 70)
print("hello_dialogue.py End-to-End Run")
print("=" * 70)

TEMPLATE = s.DialogueTemplate(
    template_id="design-review",
    version="1.0.0",
    # Template = the reusable *pattern*: a generic title, goal, and termination that fit any design
    # review, not one task. The run-specific objective and termination are supplied per-instance
    # (see `goal=` / `termination=` in instantiate).
    title="Design review",
    goal="Converge on a proposal the designated approver signs off on.",
    termination_policy=s.TerminationPolicy(condition="the approver approves", max_turns=8),
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
    # Orchestration is part of the *template* (the pattern), not the per-run instance — unlike
    # goal/termination/brief. This template declares no `flow`, so the mode defaults to `plan`: the
    # orchestrator's model picks the next speaker each turn (emergent). The `flow` — the succession
    # structure over these roles — belongs here alongside `roles` and `orchestration.mode`, because
    # it describes how *this kind* of dialogue runs. To fix the order instead, declare it and switch
    # to `flow` mode (both on the template):
    #
    #   orchestration=s.Orchestration(mode=s.OrchestrationMode.FLOW),
    #   flow=s.Flow(entry="proposer", edges=[
    #       s.Edge(from_role="proposer", to_role="critic"),
    #       s.Edge(from_role="critic",   to_role="founder"),
    #   ]),
)


async def main() -> None:
     # Step 1: Load config
    print("\n1. Loading configuration from .env...")
    load_dotenv()
    
    # Step 2: Create server
    print("2. Creating Server...")
    server = Server(database_url="sqlite:///:memory:")
    
    # Step 3: Check provider
    print("3. Checking provider configuration...")
    info = server.server_info()
    configured = [p.provider for p in info.model_providers if p.configured]
    
    if server.config.model_provider not in configured:
        print(f"\n⚠️  ERROR: Provider {server.config.model_provider!r} not configured")
        print(f"   Available: {configured}")
        print("   Cannot continue with hello_dialogue test.")
        return False
    
    print(f"   ✓ Provider {server.config.model_provider} is configured")
    
    # --- per-agent providers (optional) ----------------------------------------------
    # By default every agent AND the orchestrator use the single provider from your .env
    # (DCP_MODEL_PROVIDER / DCP_MODEL). But DCP lets each agent run a *different* provider/model
    # via a ModelBinding — one dialogue can mix, e.g. a Claude proposer and a GPT critic. Fill this
    # in to try it (each provider's key must be in the environment; `dcp info` shows what's set):
    #
    #   AGENT_MODELS = {
    #       "proposer": s.ModelBinding(provider="anthropic", model="claude-opus-4-8"),
    #       "critic":   s.ModelBinding(provider="openai",    model="gpt-5.4"),
    #       # local open-weights via an OpenAI-compatible server (vLLM / Ollama / LM Studio):
    #       # "critic": s.ModelBinding(provider="local", model="llama3.1",
    #       #                          base_url="http://localhost:11434/v1"),
    #   }
    AGENT_MODELS: dict[str, s.ModelBinding] = {}    # empty → every agent uses the .env default

    # Step 4: Register template and participants
    print("4. Registering template and participants...")
    server.register_template(TEMPLATE)
    for pid, kind in (("proposer", s.RoleKind.AGENT), ("critic", s.RoleKind.AGENT),
                      ("founder", s.RoleKind.HUMAN)):
        server.register_participant(
            # model_binding is per-agent (D8); None → inherit the orchestrator's default provider.
            # (It is only valid on agent roles, so the human founder always gets None.)
            s.Participant(participant_id=pid, kind=kind, display_name=pid.title(),
                          model_binding=AGENT_MODELS.get(pid))
        )
    # Step 5: Instantiate
    print("5. Instantiating dialogue instance...")
    server.instantiate(
        s.TemplateRef(template_id="design-review", version="1.0.0"),
        owner="founder", instance_id="demo",
        # The generic "design-review" template, aimed at *this* run: `goal` is the concrete
        # objective (overrides the template's generic goal), `termination` sets this run's
        # completion condition and caps (overrides the template's), and `brief` the task specifics.
        # All reach the orchestrator and every agent — so the proposer names *this* product, not one
        # invented from thin air. Re-run the same template with a new goal/termination/brief later.
        goal="Agree on a product name the founder approves.",
        termination=s.TerminationPolicy(condition="the founder approves the name", max_turns=6),
        brief={
            "product": "a B2B analytics platform for fintech CFOs",
            "audience": "finance leaders at mid-market fintechs",
            "constraints": ["one or two words", "avoid the '-ly' suffix", "low trademark risk"],
        },
    )

    # Step 6: Run
    print("6. Running orchestration...")
    result = await server.run(
        "demo",
        cast={"proposer": "proposer", "critic": "critic", "founder": "founder"},
        # No scripted providers: orchestrator + agents use the configured model (plan mode).
        human_gateway=ScriptedHumanGateway(
            {"founder": HumanReply(content="Approved — ship it.", decision="approve")}
        ),
    )
    # Step 7: Validate output
    print("\n" + "=" * 70)
    print("OUTPUT:")
    print("=" * 70)
    print(f"status: {result.status.value}  (turns: {result.turn})")
    for m in result.messages:
        print(f"  {m.role_id}: {m.content}")

if __name__ == "__main__":
    asyncio.run(main())
