#!/usr/bin/env python3
"""Build your own orchestrator = write its BRAIN (a custom ControlPolicy), not a new runtime.

You never subclass the Orchestrator: the runtime (turn serialization, oversight, recovery,
termination, replay) is fixed and correctness-critical. You compose your orchestrator from a custom
`ControlPolicy` — who speaks / when to stop — and, optionally, a custom `OversightPolicy`. Your
`decide(ctx)` reads the rich, read-only DialogueContext to make its call.

This demo builds a moderated-debate brain: alternate two debaters for N rounds each, then let a judge
close, then stop — reading `ctx.messages` / `ctx.last_speaker` and respecting the turn cap, no model
needed. (A model-backed brain just calls `ctx.provider.structured(...)` inside `decide` — see the
commented variant.)

Run:  python docs/examples/orchestrator_build_own.py
"""
from __future__ import annotations

import asyncio
from collections import Counter

from dcp import Server, render_timeline
from dcp import schema as s
from dcp.orchestration import DialogueContext, OrchestratorAction
from dcp.provider import MockProvider


class ModeratedDebatePolicy:
    """A custom orchestrator brain. It reads the DialogueContext to decide each turn:

    - ``ctx.roles``                — the seats (here: two debaters + a judge)
    - ``ctx.messages``             — the transcript so far (to count who has spoken)
    - ``ctx.last_speaker``         — to alternate away from whoever just spoke
    - ``ctx.goal`` / ``ctx.brief`` — the run's intent (most useful for a model-backed brain)
    - ``ctx.over_turn_cap()``      — respect the turn budget

    Rule: each debater speaks ``rounds`` times (alternating), then the judge closes, then stop.
    """

    def __init__(self, *, debaters: tuple[str, str], judge: str, rounds: int = 2) -> None:
        self._debaters, self._judge, self._rounds = debaters, judge, rounds

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        counts = Counter(m.role_id for m in ctx.messages)
        # A debater still owes a round? Pick the one who has spoken least, avoiding the last speaker.
        owed = [d for d in self._debaters if counts[d] < self._rounds]
        if owed:
            nxt = min(owed, key=lambda d: (counts[d], d == ctx.last_speaker))
            return OrchestratorAction(action="select_speaker", target_role_id=nxt)
        if counts[self._judge] == 0:                       # both debaters done -> the judge closes
            return OrchestratorAction(action="select_speaker", target_role_id=self._judge)
        return OrchestratorAction(action="stop", status=s.TerminationStatus.DONE)

    # A model-backed brain would instead ask the orchestrator's model, e.g.:
    #   async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
    #       return await ctx.provider.structured(
    #           instructions=f"Goal: {ctx.goal}. Pick the next role to speak, or stop.",
    #           content=ctx.transcript(), schema=OrchestratorAction)


def _agent(rid: str, name: str) -> s.Role:
    return s.Role(role_id=rid, name=name, kind=s.RoleKind.AGENT,
                  response_requirement=s.ResponseRequirement.REQUIRED)


TEMPLATE = s.DialogueTemplate(
    template_id="debate", version="1.0.0", title="Moderated debate",
    goal="Weigh a proposal from both sides, then decide.",
    termination_policy=s.TerminationPolicy(condition="judge decides", max_turns=8),
    roles=[_agent("optimist", "Optimist"), _agent("skeptic", "Skeptic"), _agent("judge", "Judge")],
)


async def main() -> None:
    server = Server(database_url="sqlite:///:memory:")
    server.register_template(TEMPLATE)
    for pid in ("optimist", "skeptic", "judge"):
        server.register_participant(
            s.Participant(participant_id=pid, kind=s.RoleKind.AGENT, display_name=pid.title()))
    server.instantiate(s.TemplateRef(template_id="debate", version="1.0.0"),
                       owner="judge", instance_id="demo",
                       brief={"proposal": "ship the beta next week"})

    # Compose YOUR orchestrator: your custom brain + the fixed runtime. (Pass oversight=… too for a
    # custom verification brain — see 04-orchestrator.md §5 and orchestrator_oversight.py.)
    inst = await server.run(
        "demo", cast={"optimist": "optimist", "skeptic": "skeptic", "judge": "judge"},
        orchestrator_provider=MockProvider(),      # unused: this brain needs no model
        agent_providers={
            "optimist": MockProvider(texts=["Ship it — momentum matters.", "Users are waiting."]),
            "skeptic": MockProvider(texts=["The beta is fragile.", "One more week de-risks it."]),
            "judge": MockProvider(texts=["Ship a limited pilot next week."]),
        },
        control_policy=ModeratedDebatePolicy(debaters=("optimist", "skeptic"), judge="judge"))

    print(f"status={inst.status.value} turns={inst.turn}")
    for m in inst.messages:
        print(f"  {m.role_id}: {m.content}")
    print("\n--- the decisions your brain made (render_timeline) ---")
    print(render_timeline(server.store, "demo"))


if __name__ == "__main__":
    asyncio.run(main())
