# CLAUDE.md — Project Working Guide

## 0. Project Positioning

**DCP (Dialogue-centric Protocol) is a standalone protocol for human-agent multi-agent
systems, built ground-up from `protocol_design.md`. MCP / A2A / ACP / ANP / agents-json are
studied only as *engineering references for how mature protocols are made, implemented, and
shipped* — DCP does not build on them, inherit their schemas, or aim for compatibility.**

The goal is a genuinely usable protocol plus a Python SDK that people actually want to adopt.
"Usable" is the success bar: a clear spec, a clean SDK, a working hello-world, and an
onboarding path a new user can complete in one sitting.

### The one hard rule about references
When analyzing MCP/A2A/ACP/ANP/agents-json, the question is **always** "*how did they make
it?*" — never "*what should we copy?*". We extract **methodology** (how a spec is authored,
how schemas are organized, how an SDK is structured, how docs onboard users), not **design**.
No entity, field, verb, or lifecycle from another protocol may enter `SPEC.md`. If a reference
protocol's concept seems useful, that is a signal to re-derive it independently from DCP's own
model — or reject it.

---

## 1. Directory Structure

```
Dialogue-centric-Protocol/
├── CLAUDE.md                  # This file — how we work
├── SPEC.md                    # The DCP specification (source of truth for behavior)
├── STATUS.md                  # Progress tracker, decision log, next actions
├── protocol_design.md         # Original design draft — sole content source for SPEC.md
├── figures/                   # Architecture / lifecycle SVGs referenced by the design & spec
│
├── research/                  # Phase 1 output — one file per reference protocol
│   ├── mcp.md                 # Filled from the Phase-1 template (§4)
│   ├── a2a.md
│   ├── acp.md
│   ├── anp.md
│   └── agents-json.md
│
├── methodology/               # Phase 2 output — cross-cutting distilled practices
│   └── methodology.md         # "How mature protocols are made" → our playbook
│
├── sdk/                       # Phase 4 — the Python SDK (package: `dcp`)
│   ├── pyproject.toml
│   ├── src/dcp/
│   │   ├── __init__.py
│   │   ├── schema/            # Pydantic models for every SPEC entity
│   │   ├── core/             # Dialogue, Role, Participant, Orchestrator, state store
│   │   ├── orchestration/     # Speaker selection, pre/post-action oversight
│   │   ├── delivery/          # Transport adapters (kept behind an interface)
│   │   └── errors.py
│   └── tests/                 # pytest suite mirroring SPEC.md acceptance criteria
│
├── docs/                      # Phase 5 — quickstart, guides, API reference
│   └── examples/              # Runnable examples incl. the canonical hello-world
└── examples/                  # (optional) larger end-to-end demos
```

Create directories lazily as each phase begins; do not scaffold empty trees ahead of time.

---

## 2. Phase Plan

The project runs in five sequential phases. Do not skip ahead — each phase consumes the
previous phase's output. A phase is "done" only when its exit criterion is met.

| Phase | Name | Input | Output | Exit criterion |
|-------|------|-------|--------|----------------|
| **1** | Reference Analysis | The 5 reference protocols | `analysis/*.md` | Every reference analyzed with the §4 template; each answers "how was it made?" |
| **2** | Methodology Distillation | `analysis/*.md` | `methodology/methodology.md` | A concrete playbook: how *we* will author the spec, organize schemas, structure the SDK, write the quickstart |
| **3** | Write DCP Spec | `protocol_design.md` + Phase-2 playbook | `SPEC.md` filled in | All entities/lifecycle/layers specified; open questions resolved or explicitly deferred |
| **4** | Python SDK | `SPEC.md` | `sdk/` | Hello-world runs; pytest suite passes against SPEC acceptance criteria |
| **5** | Docs & Release | SDK + spec | `docs/`, packaging | New user completes the onboarding path unaided; package installable |

**Phase 1 & 2 shape *method*; Phase 3+ produce *DCP itself*.** Keep the two firmly separated:
insights from Phase 1/2 tell us *how to build*, never *what DCP's design should be*.

---

## 3. SDK Technical Specification

- **Language / version:** Python ≥ 3.11.
- **Package name:** `dcp`. Public API surface stays small and explicit (curated `__init__`).
- **Schema / validation:** Pydantic v2. Every SPEC entity (Dialogue, Role, Participant,
  Message, Event, orchestration actions, termination status) is a typed model. Schemas are the
  contract; the SDK never accepts a shape the spec doesn't define.
- **Layered architecture mirrors SPEC §3** (Dialogue State / Participation / Orchestration /
  Delivery). The Delivery layer sits behind an interface so the semantic core never depends on
  a transport (HTTP/SSE/WebSocket/polling are pluggable adapters, per SPEC §3.4).
- **Core is transport-agnostic and side-effect-light:** state transitions are pure and
  event-emitting; I/O lives at the edges.
- **Async-first** for orchestration and participant invocation (`async def`), with a sync
  convenience wrapper only where it clearly helps.
- **Determinism & audit:** every state change emits an `Event`; a dialogue must be replayable
  from its event log (supports the audit/replay/recovery goals in SPEC §1.6).
- **Errors:** typed exception hierarchy in `errors.py`; terminal dialogue statuses
  (`done/provisional/stopped/budget/error`) map to explicit outcomes, not raised exceptions.
- **Tooling:** `ruff` (lint+format), `mypy` (strict on `src/dcp`), `pytest` (+`pytest-asyncio`),
  packaging via `pyproject.toml` (PEP 621).
- **No hidden coupling to reference protocols:** no MCP/A2A/etc. dependency, import, or wire
  format. Interop, if ever pursued, is a separate adapter package — never core.

---

## 4. Phase 1 Analysis Template

Fill `research/<protocol>.md` for each reference. **Focus exclusively on *how it was made*,
not on what it does.** For every heading, cite where in the reference's own repo/docs you
found the evidence (file path or URL + section).

```markdown
# Reference Analysis: <Protocol Name>

## Snapshot
- Maintainer / governance model, license, maturity, current version.
- In one paragraph: what problem it solves. (Context only — not our focus.)

## A. How the spec is authored
- Where does the normative spec live (repo path / site)? One doc or many?
- How is it structured (sections, ordering, normative vs. informative split)?
- What conventions signal requirements (MUST/SHOULD, versioning, changelog)?
- How are examples embedded alongside normative text?

## B. How schemas are defined
- What schema technology (JSON Schema, Protobuf, OpenAPI, TS types, Pydantic…)?
- Where do schemas live and how are they organized (per-entity? one file?)?
- How are they versioned and validated? Codegen from schema, or hand-written?
- How is extensibility expressed (open fields, capabilities, negotiation)?

## C. How the SDK is architected
- Package layout: top-level modules and their responsibilities.
- What are the core public types/classes a user touches first?
- Sync vs async; transport handling; where I/O is isolated.
- How schema ↔ code stays in sync (generated? shared source of truth?).
- Public API surface size — minimal or broad? Naming conventions.

## D. What hello-world looks like
- Paste the smallest complete working example from their docs.
- How many lines / concepts before something runs?
- What must be installed/configured first?

## E. New-user onboarding path
- The literal sequence: install → first success → next step.
- Where does the quickstart live; how long to first working result?
- What examples/tutorials exist; how are docs organized (reference vs guide)?
- How is it released/distributed (PyPI/npm, versioning, release notes)?

## Methodology takeaways (for Phase 2)
- 3–6 bullets: concrete practices worth adopting *for how we build DCP*.
- Explicitly: what to avoid / what added friction for their users.
```

---

## 5. Session Working Rules

Follow these every session, in order:

1. **Start by reading `STATUS.md`.** It is the single source of truth for where the project
   is. Identify the current phase and the top item under "Next Actions" before doing anything.
2. **Read `SPEC.md` before any module work** so implementation follows the contract, not
   memory or the design draft directly.
3. **Tests first (pytest).** For any SDK module, write `pytest` tests against the relevant
   acceptance criteria in `SPEC.md` *before* implementation. Red → green → refactor. No module
   code lands without a failing test that motivated it.
4. **Record every non-trivial decision in the Decision Log** (`STATUS.md`): what was decided,
   why, alternatives rejected, date. Especially: anything where a reference protocol tempted us
   toward a design choice — note that we re-derived or rejected it independently.
5. **Never import another protocol's design into `SPEC.md`.** References inform *method*, not
   *content*. If unsure, treat it as out of scope and log an open question.
6. **End the session by updating `STATUS.md`:** tick completed checklist items, append decisions
   to the Decision Log, and rewrite "Next Actions" so the next session can start cold.
7. **Keep `SPEC.md` the behavioral source of truth.** If implementation reveals a spec gap,
   fix the spec first (or file an open question), then the code.

---

## 6. Definition of Done (per artifact)

- **Analysis file:** every §4 heading answered with evidence; methodology takeaways listed.
- **SPEC section:** entities/fields/transitions specified; examples valid against schemas;
  no `[TBD]` left unnumbered.
- **SDK module:** pytest green, mypy clean, mirrors a SPEC section, no reference-protocol leakage.
- **Docs:** a new user can go install → hello-world → next step without external help.
