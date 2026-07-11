"""Flagship: a Student Research Companion built on DCP (key-free).

A small multi-agent system that helps a student advance a research question, showing how DCP's
pieces compose into a real application:

- a **preset template** (`research_companion`) driven by a **custom orchestrator** (a `ControlPolicy`
  you write — here a fixed research workflow, using no model at all);
- **grounding oversight** — the Literature Scout must cite a source, or the orchestrator sends the
  turn back for a revision (a `RubricOversight` with one check);
- a **human approval gate** — the Advisor signs off before the dialogue completes;
- **durability / replay (D3)** — nothing lives in memory; the whole dialogue is reconstructed from
  the append-only event log at the end.

Run:  python docs/examples/research_companion_mock.py     (no API key)

The real-model version is ``research_companion.py``.
"""

from __future__ import annotations

import asyncio

from dcp import Server, presets
from dcp import schema as s
from dcp.orchestration import (
    CheckOutcome,
    DialogueContext,
    HumanReply,
    OrchestratorAction,
    RubricOversight,
    ScriptedHumanGateway,
)
from dcp.provider import MockProvider


# --- 1. a custom orchestrator: the research workflow -------------------------------------
class ResearchWorkflowPolicy:
    """Drive scout → methodologist → coach → advisor, then stop. A pure function of the transcript.

    This is a *custom ControlPolicy* — your own orchestrator. It needs no model: the next speaker is
    decided from the read-only DialogueContext. The DCP runtime still applies oversight, the human
    gate, and replay around whatever this decides.
    """

    ORDER = ("scout", "methodologist", "coach", "advisor")

    def __init__(self, suspend_before: str | None = None) -> None:
        # if set, pause the dialogue (suspend) when this role would be next — e.g. the advisor is
        # away today; we resume tomorrow. Demonstrates cross-session resume (SPEC §2.9).
        self._suspend_before = suspend_before

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        spoken = {m.role_id for m in ctx.messages}
        for role in self.ORDER:
            if role not in spoken and role not in ctx.rejected_this_turn:
                if role == self._suspend_before:
                    return OrchestratorAction(action="suspend", reason=f"waiting for {role}")
                return OrchestratorAction(action="select_speaker", target_role_id=role)
        return OrchestratorAction(action="stop", status=s.TerminationStatus.DONE, reason="signed off")


# --- 2. grounding oversight: the scout must cite a source --------------------------------
async def grounding_check(
    *, role: s.Role, message: s.Message, transcript: str
) -> s.Assessment | CheckOutcome:
    if role.role_id == "scout" and "http" not in message.content:
        return CheckOutcome(s.Assessment.WEAK, "cite a source (a URL)")
    return s.Assessment.OK


async def run_demo() -> s.DialogueInstance:
    server = Server(database_url="sqlite:///:memory:")

    # register the template (a preset) and the participants
    server.register_template(presets.research_companion())
    agents = ("scout", "methodologist", "coach")
    humans = ("advisor", "student")
    for pid in agents:
        server.register_participant(
            s.Participant(participant_id=pid, kind=s.RoleKind.AGENT, display_name=pid.title()))
    for pid in humans:
        server.register_participant(
            s.Participant(participant_id=pid, kind=s.RoleKind.HUMAN, display_name=pid.title()))

    server.instantiate(
        s.TemplateRef(template_id="research-companion", version="1.0.0"),
        owner="student", instance_id="proj-1",
    )

    result = await server.run(
        "proj-1",
        cast={r: r for r in (*agents, *humans)},
        control_policy=ResearchWorkflowPolicy(),          # <-- our custom orchestrator
        orchestrator_provider=MockProvider(),             # key-free: the policy needs no model
        oversight=RubricOversight(grounding=grounding_check),
        agent_providers={
            # the scout's first draft has no citation → oversight forces a grounded revision
            "scout": MockProvider(texts=[
                "Prior work uses transformer retrievers.",
                "Prior work uses transformer retrievers, e.g. http://arxiv.org/abs/2401.00001",
            ]),
            "methodologist": MockProvider(texts=["Add a baseline and an ablation to isolate the gain."]),
            "coach": MockProvider(texts=["Sharpen the contribution to one crisp sentence."]),
        },
        human_gateway=ScriptedHumanGateway(
            {"advisor": HumanReply(content="Direction approved — proceed to a pilot.",
                                   decision="approve")}),
    )
    return result


async def run_across_sessions() -> tuple[s.DialogueInstance, s.DialogueInstance]:
    """Session 1 pauses before the advisor (away today); session 2 resumes and finishes (SPEC §2.9)."""
    server = Server(database_url="sqlite:///:memory:")
    server.register_template(presets.research_companion())
    for pid in ("scout", "methodologist", "coach"):
        server.register_participant(
            s.Participant(participant_id=pid, kind=s.RoleKind.AGENT, display_name=pid.title()))
    for pid in ("advisor", "student"):
        server.register_participant(
            s.Participant(participant_id=pid, kind=s.RoleKind.HUMAN, display_name=pid.title()))
    server.instantiate(s.TemplateRef(template_id="research-companion", version="1.0.0"),
                       owner="student", instance_id="proj-2")

    cast = {r: r for r in ("scout", "methodologist", "coach", "advisor", "student")}
    oversight = RubricOversight(grounding=grounding_check)
    agents = {"scout": MockProvider(texts=["Prior work: retrievers.",
                                           "Prior work: retrievers, http://arxiv.org/abs/2401.1"]),
              "methodologist": MockProvider(texts=["Add a baseline."]),
              "coach": MockProvider(texts=["Sharpen the claim."])}
    gateway = ScriptedHumanGateway(
        {"advisor": HumanReply(content="Approved — proceed.", decision="approve")})

    # day 1 — the advisor is away; the workflow pauses before them (suspend → non-terminal)
    day1 = await server.run("proj-2", cast=cast, control_policy=ResearchWorkflowPolicy("advisor"),
                            orchestrator_provider=MockProvider(), oversight=oversight,
                            agent_providers=agents, human_gateway=gateway)
    # day 2 — the advisor is back; a fresh run() resumes the same instance and finishes
    day2 = await server.run("proj-2", cast=cast, control_policy=ResearchWorkflowPolicy(),
                            orchestrator_provider=MockProvider(), oversight=oversight,
                            human_gateway=gateway)
    return day1, day2


async def main() -> None:
    result = await run_demo()

    print(f"status: {result.status.value}  (turns: {result.turn})\n")
    for m in result.messages:
        print(f"  {m.role_id}: {m.content}")

    # D3: `result` is itself a full replay of the append-only log — nothing lived only in memory.
    # `restore(store, instance_id)` reconstructs the same object in any later session or process.
    print(f"\nreplayed from the log: {len(result.messages)} messages, {len(result.events)} events")

    # resume across sessions (SPEC §2.9): pause with the advisor away, continue the next day
    day1, day2 = await run_across_sessions()
    print(f"\nday 1: {day1.status.value} ({len(day1.messages)} msgs, paused before the advisor)")
    print(f"day 2: {day2.status.value} ({len(day2.messages)} msgs, resumed to sign-off)")


if __name__ == "__main__":
    asyncio.run(main())
