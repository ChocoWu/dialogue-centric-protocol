#!/usr/bin/env python3
"""Oversight governs control: the orchestrator ACTS on each verification record, it doesn't just
log it (pre-action -> recovery, post-action -> routing). Three oversight policies, plus the full
per-turn workflow made visible in the event log.

- DefaultOversight  — all-pass (the key-free happy path).
- RubricOversight   — one check per dimension; here a grounding check triggers a revision.
- ScriptedOversight — drive the recovery/revision branches deterministically, no model.

(LlmOversight asks the orchestrator's model for the same records — same shape, needs a provider.)

The workflow each turn: select speaker -> pre-verify (-> recovery) -> contribute -> post-verify
(-> revision / verification / escalate / stop). Deterministic, key-free.

Run:  python docs/examples/orchestrator_oversight.py
"""
from __future__ import annotations

import asyncio

from dcp import Server, render_timeline
from dcp import schema as s
from dcp.orchestration import CheckOutcome, DefaultOversight, RubricOversight, ScriptedOversight
from dcp.provider import MockProvider

TEMPLATE = s.DialogueTemplate(
    template_id="oversight-demo", version="1.0.0", title="Oversight demo",
    goal="Produce one grounded line.",
    termination_policy=s.TerminationPolicy(condition="done", max_turns=4),
    roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                  response_requirement=s.ResponseRequirement.REQUIRED)],
)
REF = s.TemplateRef(template_id="oversight-demo", version="1.0.0")


def _plan() -> MockProvider:
    return MockProvider(structured_queue=[
        {"action": "select_speaker", "target_role_id": "a"},
        {"action": "stop", "status": "done"}])


def _pre(readiness: str, action: str, *, issue: str = "") -> s.PreActionVerification:
    return s.PreActionVerification(
        readiness=readiness, availability="available", capability_match="high",
        role_state="needed", context_sufficiency="sufficient",
        execution_feasibility="feasible", recommended_action=action,
        issues=[s.Issue(type="gap", description=issue)] if issue else [])


def _post(outcome: str, *, verdict: str = "pass") -> s.PostActionVerification:
    return s.PostActionVerification(
        verdict=verdict, relevance="ok", role_consistency="ok", completeness="ok",
        grounding="ok", safety="ok", human_input_addressed=True, outcome=outcome)


def _server() -> Server:
    srv = Server(database_url="sqlite:///:memory:")
    srv.register_template(TEMPLATE)
    srv.register_participant(s.Participant(participant_id="a", kind=s.RoleKind.AGENT,
                                           display_name="A"))
    return srv


async def main() -> None:
    # 1) DefaultOversight — all pass, one clean turn.
    srv = _server()
    srv.instantiate(REF, owner="a", instance_id="default")
    d = await srv.run("default", cast={"a": "a"}, orchestrator_provider=_plan(),
                      agent_providers={"a": MockProvider(texts=["A grounded line [1]"])},
                      oversight=DefaultOversight())
    print("DefaultOversight  ->", d.status.value, [m.content for m in d.messages])

    # 2) RubricOversight — one check per dimension; a failing grounding check -> a revision.
    async def grounding(*, role: s.Role, message: s.Message, transcript: str) -> CheckOutcome:
        if "[" in message.content:                       # crude "has a citation"
            return CheckOutcome(s.Assessment.OK)
        return CheckOutcome(s.Assessment.WEAK, "no source cited")

    srv = _server()
    srv.instantiate(REF, owner="a", instance_id="rubric")
    r = await srv.run("rubric", cast={"a": "a"}, orchestrator_provider=_plan(),
                      agent_providers={"a": MockProvider(texts=["ungrounded claim",
                                                                 "grounded claim [1]"])},
                      oversight=RubricOversight(grounding=grounding))
    print("RubricOversight   ->", r.status.value, [m.content for m in r.messages],
          "(the first line was revised because it had no citation)")

    # 3) ScriptedOversight — drive the whole workflow deterministically:
    #    select -> pre(not_ready->inject_context->retry) -> contribute -> post(revise) -> contribute
    #    -> post(continue) -> stop.
    srv = _server()
    srv.instantiate(REF, owner="a", instance_id="workflow")
    w = await srv.run("workflow", cast={"a": "a"}, orchestrator_provider=_plan(),
                      agent_providers={"a": MockProvider(texts=["draft", "revised"])},
                      oversight=ScriptedOversight(
                          pre=[_pre("not_ready", "inject_context", issue="needs constraints"),
                               _pre("ready", "select_speaker")],
                          post=[_post("request_revision", verdict="revise"), _post("continue")]))
    print("ScriptedOversight ->", w.status.value, [m.content for m in w.messages])
    print("\n--- the full turn workflow, from the event log (render_timeline) ---")
    print(render_timeline(srv.store, "workflow"))


if __name__ == "__main__":
    asyncio.run(main())
