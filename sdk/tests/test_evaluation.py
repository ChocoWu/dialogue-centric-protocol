"""Phase 6.4 — the evaluation harness (scenarios × candidates → metrics)."""

from __future__ import annotations

from dcp import schema as s
from dcp.evaluation import Candidate, Scenario, aggregate, render_report, run_matrix
from dcp.orchestration import DialogueContext, OrchestratorAction, ScriptedOversight
from dcp.provider import MockProvider


def _agent(rid: str) -> s.Role:
    return s.Role(role_id=rid, name=rid, kind=s.RoleKind.AGENT,
                  response_requirement=s.ResponseRequirement.REQUIRED)


class _RoundRobin:
    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        spoken = {m.role_id for m in ctx.messages}
        for rid in ("a", "b"):
            if rid not in spoken:
                return OrchestratorAction(action="select_speaker", target_role_id=rid)
        return OrchestratorAction(action="stop", status=s.TerminationStatus.DONE)


class _Suspends:
    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        return OrchestratorAction(action="suspend", reason="lazy")


class _PicksGhost:
    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        return OrchestratorAction(action="select_speaker", target_role_id="ghost")  # unknown role


def _scenario(**kw: object) -> Scenario:
    tmpl = s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done", max_turns=6),
        roles=[_agent("a"), _agent("b")])
    return Scenario(
        name="two-agent", template=tmpl, cast={"a": "a", "b": "b"},
        participants={r: s.Participant(participant_id=r, kind=s.RoleKind.AGENT, display_name=r)
                      for r in ("a", "b")},
        agent_providers={"a": MockProvider(texts=["hello from a"]),
                         "b": MockProvider(texts=["reply from b"])},
        **kw)  # type: ignore[arg-type]


async def test_matrix_compares_control_policies() -> None:
    results = await run_matrix(
        [_scenario()],
        [Candidate("round_robin", control_policy=_RoundRobin()),
         Candidate("lazy", control_policy=_Suspends())])

    by = {(r.candidate, r.scenario): r for r in results}
    rr = by[("round_robin", "two-agent")]
    assert rr.status == "done" and rr.success is True
    assert rr.metrics["turns"] == 2.0 and rr.metrics["reached_goal"] == 1.0
    lazy = by[("lazy", "two-agent")]
    assert lazy.status == "running" and lazy.success is False   # suspended → non-terminal


async def test_aggregate_and_report() -> None:
    results = await run_matrix(
        [_scenario()],
        [Candidate("round_robin", control_policy=_RoundRobin()),
         Candidate("lazy", control_policy=_Suspends())])
    agg = aggregate(results)
    assert agg["round_robin"]["success_rate"] == 1.0
    assert agg["lazy"]["success_rate"] == 0.0

    report = render_report(results)
    assert "round_robin" in report and "lazy" in report
    assert "success_rate" in report and "oversight_pass_rate" in report


async def test_oversight_candidate_metrics() -> None:
    # fix the orchestrator (RoundRobin) in the scenario; vary the OVERSIGHT candidate
    scen = _scenario(control_policy=_RoundRobin())

    def _post(outcome: str, verdict: str = "pass") -> s.PostActionVerification:
        return s.PostActionVerification(
            verdict=verdict, relevance="ok", role_consistency="ok", completeness="ok",
            grounding="ok", safety="ok", human_input_addressed=True, outcome=outcome)

    strict = ScriptedOversight(post=[_post("request_revision", "revise"), _post("continue"),
                                     _post("continue")])
    results = await run_matrix([scen], [Candidate("strict", oversight=strict)])
    r = results[0]
    assert r.metrics["revisions"] >= 1.0            # the strict policy forced a revision
    assert r.metrics["oversight_pass_rate"] < 1.0   # not every verdict was a pass


async def test_scorer_overrides_success() -> None:
    scen = _scenario(scorer=lambda inst: any("hello" in m.content for m in inst.messages))
    results = await run_matrix([scen], [Candidate("round_robin", control_policy=_RoundRobin())])
    assert results[0].success is True               # scorer matched ("hello from a")


async def test_a_crashing_candidate_is_recorded_not_raised() -> None:
    results = await run_matrix([_scenario()], [Candidate("broken", control_policy=_PicksGhost())])
    assert results[0].status == "error" and results[0].success is False
