# Guide: Evaluating orchestrators & oversight

DCP is a place to *compare* dialogue-control and verification approaches, not just run them. Because
every decision is recorded in the append-only log, the log **is** the ground truth — so you can score
and rank a `ControlPolicy` or an `OversightPolicy` across a set of scenarios. That's what
`dcp.evaluation` is for.

## The shape

- A **`Scenario`** is a reproducible dialogue with everything fixed *except* the component under test
  (template, cast, participants, scripted agent providers, optional human gateway, optional success
  `scorer`).
- A **`Candidate`** is a named thing to evaluate — a `control_policy` and/or an `oversight` policy.
- **`run_matrix`** runs every (candidate × scenario) and reads **metrics** from each finished
  instance; **`render_report`** prints a comparison.

Use scripted `MockProvider`s so runs are deterministic and CI-friendly.

```python
from dcp.evaluation import Scenario, Candidate, run_matrix, render_report
from dcp.orchestration import PlanPolicy
from dcp.provider import MockProvider
from dcp import schema as s

scenario = Scenario(
    name="two-agent",
    template=my_template, cast={"a": "a", "b": "b"},
    participants={r: s.Participant(participant_id=r, kind=s.RoleKind.AGENT, display_name=r)
                  for r in ("a", "b")},
    agent_providers={"a": MockProvider(texts=["…"]), "b": MockProvider(texts=["…"])},
    scorer=lambda inst: any("cite" in m.content for m in inst.messages),   # optional
)

results = await run_matrix(
    [scenario],
    [Candidate("round_robin", control_policy=RoundRobinPolicy()),
     Candidate("my_planner",  control_policy=MyPolicy())],
)
print(render_report(results))
```

```
candidate            success_rate   reached_goal      turns   revisions  …  oversight_pass_rate
round_robin                 1.00           1.00        2.00        0.00              1.00
my_planner                  1.00           1.00        3.00        1.00              0.67
```

## Metrics

Built-in (`DEFAULT_METRICS`), all read from the log:

| Metric | Meaning |
|--------|---------|
| `reached_goal` | 1 if the instance ended `done` |
| `turns` | contributions to termination (lower is leaner) |
| `revisions` | `revision_requested` events (oversight rework) |
| `recoveries` | pre-action recoveries (a candidate was found not-ready and switched) |
| `escalations` | post-action gate escalations |
| `oversight_pass_rate` | fraction of post-action verdicts that were `pass` |

Plus a per-run **`success`** — your `Scenario.scorer(inst)` if provided, else "reached `done`". Add
your own metric with `Metric(name, fn=lambda inst: ...)` and pass a custom list to `run_matrix`.

## Evaluating oversight (not just orchestrators)

Fix the orchestrator on the scenario and vary the oversight candidate:

```python
scenario = Scenario(..., control_policy=RoundRobinPolicy())     # fixed
results = await run_matrix(scenario_list, [
    Candidate("lenient", oversight=DefaultOversight()),
    Candidate("grounding", oversight=RubricOversight(grounding=my_check)),
])
```

`revisions` and `oversight_pass_rate` then tell you how much rework each verification regime induced.

## Why this matters

A researcher building a "powerful orchestrator" can now *measure* it against baselines on shared
scenarios, deterministically — DCP as a benchmark, not just a runtime. A crashing candidate is
recorded as `status="error"` rather than aborting the matrix, so a whole panel runs to completion.

See [guide-extending.md](guide-extending.md) to write the policies you evaluate here.
