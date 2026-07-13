# DCP documentation

A guided path from zero to building your own dialogue-centric multi-agent system. Read the numbered
docs in order the first time; jump by task after that.

## 1 · Understand & use

The core reading path — finish these five and you can build a system.

| # | Doc | What you get |
|---|-----|--------------|
| 1 | **[Quick Start](01-quickstart.md)** | Install, then run three examples — key-free mock, real model, HTTP server. The fastest path to something running. |
| 2 | **[Design Overview](02-design-overview.md)** | The whole map: entities, the five layers, the runtime flow, and the *content-vs-structure* split. Read once and the rest clicks. |
| 3 | **[Templates & Instances](03-dialogue-template.md)** | The reusable *pattern* (template) vs. *this run* (instance): every field, the per-run `goal`/`termination`/`brief` overrides, how to create/use, lifecycle & replay. |
| 4 | **[Orchestrator](04-orchestrator.md)** | How a dialogue is *driven and overseen*: the turn loop, control policies (plan/flow/custom), and oversight policies. |
| 5 | **[Participant](05-participant.md)** | Who takes part: humans (join/gate/optional) and agents (the provider taxonomy, per-agent model binding, bring-your-own agent). |

## 2 · Deploy & extend

| # | Doc | What you get |
|---|-----|--------------|
| 6 | **[Hosting & Delivery](06-hosting-delivery.md)** | Turn it into a multi-user server: registry, access tiers, auth, HTTP+SSE routes, the `dcp` CLI, and deployment (SQLite/Postgres). |
| 7 | **[Extending & Sharing](07-extending-sharing.md)** | Package what you build — a custom policy/oversight/provider/template — as a pip plugin or a portable **local / remote component**. |

## 3 · Evaluate & reference

| # | Doc | What you get |
|---|-----|--------------|
| 8 | **[Evaluation](08-evaluation.md)** | *Measure* a system: targets, dimensions (completion/quality/safety/efficiency/determinism), and how to write & compare harnesses. |
| 9 | **[API Reference](09-api-reference.md)** | The curated public API — core classes, methods, schema, config, the `dcp` CLI, and the HTTP endpoint table. |

## 4 · When you're stuck

| # | Doc | What you get |
|---|-----|--------------|
| 10 | **[Troubleshooting / FAQ](10-troubleshooting.md)** | The common "why doesn't this work?" answers — each a symptom → cause → one-line fix. |

## Worked example & deep dives (off the main path)

- **[Walkthrough: a Student Research Companion](walkthrough-research-companion.md)** — a complete flagship MAS built end to end (custom orchestrator + grounding oversight + a human gate).
- **[Components reference](components-reference.md)** — the full manifest / checkpoint / remote-delivery reference behind [Extending & Sharing](07-extending-sharing.md).
- **[examples/](examples/)** — runnable, key-free scripts: `hello_dialogue_mock.py` · `research_companion_mock.py` · `component/` (one component, run **local** *and* **remote**).

## Normative & release

- **[../SPEC.md](../SPEC.md)** — the normative behavioral specification (the source of truth for behavior).
- **[../bindings/](../bindings/)** — the remote-component wire protocol (transport-independent core + the HTTP/SSE mapping).
- **[../CHANGELOG.md](../CHANGELOG.md)** — what's new.
