"""Flagship: a Student Research Companion built on DCP (real model).

Same MAS as ``research_companion_mock.py`` — a custom orchestrator (`ResearchWorkflowPolicy`) drives
scout → methodologist → coach → advisor over the `research_companion` preset, with grounding
oversight and a human approval gate — but the agents' contributions come from a live model.

Needs a provider key + model in the environment (or a local ``.env``):
    DCP_MODEL_PROVIDER=openai        # or anthropic
    OPENAI_API_KEY=sk-...            # (ANTHROPIC_API_KEY for anthropic)
    DCP_MODEL=gpt-5.4

Run:  python docs/examples/research_companion.py

For a zero-setup version, run ``research_companion_mock.py``.
"""

from __future__ import annotations

import asyncio

from dcp import Server, load_dotenv, presets
from dcp import schema as s
from dcp.orchestration import (
    CheckOutcome,
    DialogueContext,
    HumanReply,
    OrchestratorAction,
    RubricOversight,
    ScriptedHumanGateway,
)


class ResearchWorkflowPolicy:
    """A custom orchestrator: scout → methodologist → coach → advisor, then stop (no model)."""

    ORDER = ("scout", "methodologist", "coach", "advisor")

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        spoken = {m.role_id for m in ctx.messages}
        for role in self.ORDER:
            if role not in spoken and role not in ctx.rejected_this_turn:
                return OrchestratorAction(action="select_speaker", target_role_id=role)
        return OrchestratorAction(action="stop", status=s.TerminationStatus.DONE, reason="signed off")


async def grounding_check(
    *, role: s.Role, message: s.Message, transcript: str
) -> s.Assessment | CheckOutcome:
    """The Literature Scout must cite a source (a URL), else the turn is sent back for revision."""
    if role.role_id == "scout" and "http" not in message.content:
        return CheckOutcome(s.Assessment.WEAK, "cite a source (a URL)")
    return s.Assessment.OK


async def main() -> None:
    load_dotenv()
    server = Server(database_url="sqlite:///:memory:")

    configured = [p.provider for p in server.server_info().model_providers if p.configured]
    if server.config.model_provider not in configured:
        raise SystemExit(
            f"provider {server.config.model_provider!r} has no key configured; "
            f"set it in the environment or run research_companion_mock.py (configured: {configured})"
        )

    server.register_template(presets.research_companion())
    for pid in ("scout", "methodologist", "coach"):
        server.register_participant(
            s.Participant(participant_id=pid, kind=s.RoleKind.AGENT, display_name=pid.title()))
    for pid in ("advisor", "student"):
        server.register_participant(
            s.Participant(participant_id=pid, kind=s.RoleKind.HUMAN, display_name=pid.title()))
    server.instantiate(
        s.TemplateRef(template_id="research-companion", version="1.0.0"),
        owner="student", instance_id="proj-1",
    )

    result = await server.run(
        "proj-1",
        cast={r: r for r in ("scout", "methodologist", "coach", "advisor", "student")},
        control_policy=ResearchWorkflowPolicy(),          # custom orchestrator (no model)
        oversight=RubricOversight(grounding=grounding_check),
        # no agent_providers → each agent uses the configured model; advisor sign-off is scripted
        human_gateway=ScriptedHumanGateway(
            {"advisor": HumanReply(content="Direction approved — proceed to a pilot.",
                                   decision="approve")}),
    )

    print(f"status: {result.status.value}  (turns: {result.turn})\n")
    for m in result.messages:
        print(f"  {m.role_id}: {m.content}")


if __name__ == "__main__":
    asyncio.run(main())
