"""Evaluation harness (Phase 6.4) — turn DCP's log into a benchmark.

The whole platform pitch is "bring your own orchestrator / oversight." This is how you *measure*
them: define **scenarios** (reproducible dialogues) and **candidates** (a `ControlPolicy` or an
`OversightPolicy` to test), run the matrix, and compare. Metrics are read from the append-only log +
verification records — the natural ground truth (reached-goal, turns, revisions, recoveries,
escalations, oversight pass-rate), plus an optional per-scenario success `scorer`.

    scenarios  = [Scenario(name="debate", template=..., cast=..., participants=..., ...)]
    candidates = [Candidate("plan", control_policy=PlanPolicy()),
                  Candidate("round_robin", control_policy=RoundRobinPolicy())]
    results = await run_matrix(scenarios, candidates)
    print(render_report(results))

Use scripted `MockProvider`s in scenarios to keep runs deterministic and CI-friendly.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .orchestration import ControlPolicy, HumanGateway, Orchestrator, OversightPolicy
from .provider import MockProvider, ModelProvider
from .schema import (
    DialogueInstance,
    DialogueTemplate,
    EventType,
    InstanceStatus,
    Participant,
    TemplateRef,
    Visibility,
)
from .state import InstanceHeader, SqlStore


# --- metrics (read from the log) ---------------------------------------------------------
@dataclass(frozen=True)
class Metric:
    """A named measurement over a finished instance (``higher_is_better`` is advisory)."""

    name: str
    fn: Callable[[DialogueInstance], float]
    higher_is_better: bool | None = None


def _count(inst: DialogueInstance, etype: EventType) -> float:
    return float(sum(1 for e in inst.events if e.type is etype))


def _recoveries(inst: DialogueInstance) -> float:
    return float(sum(1 for e in inst.events
                     if e.type is EventType.PRE_ACTION_VERIFIED and e.payload.get("recovered")))


def _escalations(inst: DialogueInstance) -> float:
    return float(sum(1 for e in inst.events
                     if e.type is EventType.POST_ACTION_VERIFIED and e.payload.get("escalated")))


def _oversight_pass_rate(inst: DialogueInstance) -> float:
    posts = [e for e in inst.events if e.type is EventType.POST_ACTION_VERIFIED]
    if not posts:
        return 1.0
    return sum(1 for e in posts if e.payload.get("verdict") == "pass") / len(posts)


REACHED_GOAL = Metric("reached_goal",
                      lambda i: 1.0 if i.status is InstanceStatus.DONE else 0.0, True)
TURNS = Metric("turns", lambda i: float(i.turn), False)
REVISIONS = Metric("revisions", lambda i: _count(i, EventType.REVISION_REQUESTED))
RECOVERIES = Metric("recoveries", _recoveries)
ESCALATIONS = Metric("escalations", _escalations)
OVERSIGHT_PASS_RATE = Metric("oversight_pass_rate", _oversight_pass_rate, True)

#: A sensible default metric set.
DEFAULT_METRICS: tuple[Metric, ...] = (
    REACHED_GOAL, TURNS, REVISIONS, RECOVERIES, ESCALATIONS, OVERSIGHT_PASS_RATE)


# --- scenario + candidate ----------------------------------------------------------------
@dataclass
class Scenario:
    """A reproducible dialogue with everything fixed except the component under test."""

    name: str
    template: DialogueTemplate
    cast: dict[str, str]                                  # role_id -> participant_id
    participants: dict[str, Participant]                 # participant_id -> Participant
    agent_providers: dict[str, ModelProvider] = field(default_factory=dict)
    human_gateway: HumanGateway | None = None
    orchestrator_provider: ModelProvider | None = None   # for a policy's model calls (branch/plan)
    control_policy: ControlPolicy | None = None          # scenario default; candidate may override
    oversight: OversightPolicy | None = None             # scenario default; candidate may override
    scorer: Callable[[DialogueInstance], bool] | None = None   # optional success predicate

    async def run(
        self, *, control_policy: ControlPolicy | None = None,
        oversight: OversightPolicy | None = None,
    ) -> DialogueInstance:
        store = SqlStore()
        store.create_instance(InstanceHeader(
            instance_id="eval",
            template_ref=TemplateRef(template_id=self.template.template_id,
                                     version=self.template.version),
            owner="@eval", visibility=Visibility.PRIVATE, dcp_version="0.2.0",
            created_at=datetime.now(UTC)))
        orchestrator = Orchestrator(
            store=store, template=self.template, instance_id="eval",
            cast=self.cast, participants=self.participants,
            provider=self.orchestrator_provider or MockProvider(),
            agent_providers=self.agent_providers,
            control_policy=control_policy or self.control_policy,   # candidate overrides scenario
            oversight=oversight or self.oversight,
            human_gateway=self.human_gateway)
        return await orchestrator.run()


@dataclass
class Candidate:
    """A named component to evaluate — a control policy and/or an oversight policy."""

    name: str
    control_policy: ControlPolicy | None = None
    oversight: OversightPolicy | None = None


@dataclass(frozen=True)
class RunResult:
    """One (scenario, candidate) run: its terminal status, metric values, and success."""

    scenario: str
    candidate: str
    status: str
    metrics: dict[str, float]
    success: bool


async def run_matrix(
    scenarios: Sequence[Scenario],
    candidates: Sequence[Candidate],
    metrics: Sequence[Metric] = DEFAULT_METRICS,
) -> list[RunResult]:
    """Run every (candidate × scenario), collecting metrics — one RunResult each.

    A crashing run is recorded as ``status="error"`` rather than raised, so one bad candidate
    doesn't abort the matrix.
    """
    results: list[RunResult] = []
    for cand in candidates:
        for scen in scenarios:
            try:
                inst = await scen.run(control_policy=cand.control_policy, oversight=cand.oversight)
            except Exception:  # noqa: BLE001 — a bad candidate shouldn't crash the whole matrix
                results.append(RunResult(scen.name, cand.name, "error",
                                         {m.name: 0.0 for m in metrics}, False))
                continue
            values = {m.name: m.fn(inst) for m in metrics}
            success = scen.scorer(inst) if scen.scorer else inst.status is InstanceStatus.DONE
            results.append(
                RunResult(scen.name, cand.name, inst.status.value, values, bool(success)))
    return results


def aggregate(results: Sequence[RunResult]) -> dict[str, dict[str, float]]:
    """Mean of each metric per candidate across scenarios, plus a ``success_rate``."""
    by_candidate: dict[str, list[RunResult]] = defaultdict(list)
    for r in results:
        by_candidate[r.candidate].append(r)
    agg: dict[str, dict[str, float]] = {}
    for candidate, rows in by_candidate.items():
        names = list(rows[0].metrics)
        means = {n: sum(r.metrics[n] for r in rows) / len(rows) for n in names}
        means["success_rate"] = sum(1.0 if r.success else 0.0 for r in rows) / len(rows)
        agg[candidate] = means
    return agg


def render_report(results: Sequence[RunResult]) -> str:
    """A comparison table: one row per candidate, columns = success_rate + mean of each metric."""
    agg = aggregate(results)
    if not agg:
        return "(no results)"
    columns = ["success_rate", *[c for c in next(iter(agg.values())) if c != "success_rate"]]
    width = max(len(c) for c in [*columns, "candidate"]) + 2
    header = "candidate".ljust(width) + "".join(c.rjust(width) for c in columns)
    lines = [header, "-" * len(header)]
    for candidate, means in sorted(agg.items()):
        row = candidate.ljust(width) + "".join(f"{means[c]:.2f}".rjust(width) for c in columns)
        lines.append(row)
    return "\n".join(lines)


__all__ = [
    "Metric",
    "DEFAULT_METRICS",
    "REACHED_GOAL",
    "TURNS",
    "REVISIONS",
    "RECOVERIES",
    "ESCALATIONS",
    "OVERSIGHT_PASS_RATE",
    "Scenario",
    "Candidate",
    "RunResult",
    "run_matrix",
    "aggregate",
    "render_report",
]
