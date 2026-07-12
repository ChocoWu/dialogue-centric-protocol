# DCP documentation

A learning path from zero to building your own dialogue-centric multi-agent system. 
Read top to bottom the first time; jump by task after that.

## 1 · Start here (≈15 min)

1. **[01-quickstart.md](01-quickstart.md)** — install → a key-free hello-world → the same dialogue on a real model → serve it over HTTP → the `dcp` CLI. The fastest path to something running.
2. **[02-concepts.md](02-concepts.md)** — the mental model behind the SDK: templates vs. instances, roles vs. participants, the five layers, the replayable event log, and the orchestrator's *control + oversight* loop. Read this once and the rest clicks.

## 2 · Build — pick a task

| I want to… | Guide |
|------------|-------|
| Start from a **preset template** and adapt it | [03-templates.md](03-templates.md) |
| **Host a multi-user server** — registration, joining, access tiers, auth, HTTP+SSE | [04-hosting.md](04-hosting.md) |
| Write a **custom orchestrator / oversight policy / agent** | [05-extending.md](05-extending.md) |
| **Benchmark & compare** orchestrators or oversight policies | [06-evaluation.md](06-evaluation.md) |
| **Share** what I built as a `pip`-installable plugin (quick, in-process) | [07-sharing.md](07-sharing.md) |
| Package a **portable component** — local *or remote*, with model checkpoints & lockfiles | [08-components.md](08-components.md) |

## 3 · Learn by example

- **[09-research-companion.md](09-research-companion.md)** — a complete flagship MAS (a Student Research Companion), built end to end: custom orchestrator + grounding oversight + a human gate.
- **[examples/](examples/)** — runnable, key-free scripts:
  `hello_dialogue_mock.py` · `research_companion_mock.py` · `component/` (one component, run **local** *and* **remote**).

## 4 · Reference

- **[10-api-reference.md](10-api-reference.md)** — the curated public API surface.
- **[../SPEC.md](../SPEC.md)** — the normative behavioral specification.
- **[../bindings/](../bindings/)** — the remote-component wire protocol (transport-independent core +
  the HTTP/SSE mapping).
- **[../CHANGELOG.md](../CHANGELOG.md)** — what's new.

---

### "Sharing" vs. "components" — which guide?

Two ways to distribute what you build; they **coexist**:

- **[07-sharing.md](07-sharing.md)** — the quick in-process path: declare a Python **entry point**, `pip install`, resolve by name. Best for a policy/template you and your team use.
- **[08-components.md](08-components.md)** — the portable path: a machine-readable **manifest** with pinned references, model checkpoints, dependency locking, and **remote** delivery. Best for publishing an open-weights orchestrator, or hosting an agent others connect to.

An installed entry point is simply *one delivery mode* of a component — start with sharing, reach for components when you need checkpoints or remote hosting.
