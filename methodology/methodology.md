# Phase 2 — Methodology Distillation

> **What this is (per CLAUDE.md §2):** a cross-protocol synthesis of *how* the five references
> (MCP, A2A, ACP, ANP, agents.json) were **made, implemented, and shipped**, distilled into a
> concrete **DCP playbook** across four axes — (A) spec authoring, (B) schema organization,
> (C) SDK architecture, (D) docs / onboarding / release. It is **method only**: no entity,
> field, verb, or lifecycle from any reference enters DCP. Every claim traces to a cited finding
> in `research/*.md`. Where the references disagree, the disagreement itself is the lesson.

**Inputs:** `research/mcp.md`, `research/a2a.md`, `research/acp.md`, `research/anp.md`,
`research/agents-json.md` (all fetched from primary sources 2026-07-09).

**How to read this:** each axis has three parts — **① What the 5 did** (comparison), **② The
distilled principle** (what converges / what the outliers prove), **③ DCP decision** (what we
will actually do in Phases 3–5). §5 is the consolidated checklist; §6 the anti-patterns; §7 the
decisions to log.

---

## 0. The five references at a glance

| | **MCP** | **A2A** | **ACP** | **ANP** | **agents.json** |
|---|---|---|---|---|---|
| **Origin / governance** | Anthropic → open org | Google → Linux Foundation | IBM/BeeAI → LF | Single maintainer | Wildcard AI |
| **Canonical schema tech** | Hand-written **TypeScript** `schema.ts` | Hand-written **proto3** `a2a.proto` | Hand-written **OpenAPI 3.1** YAML | **None** (prose tables) | Hand-written **JSON Schema** draft-07 |
| **Source-of-truth discipline** | 1 source → generate JSON Schema | 1 source → generate JSON Schema | **2 hand-kept mirrors** (YAML + Pydantic) | **0** (site vs repo drift) | 1 source → generate Pydantic |
| **Spec form** | Numbered site pages + schema | 1 doc, 14 §, bindings last | OpenAPI file + per-op `.mdx` | Many numbered `.md` docs | Schema **is** the spec |
| **Normative language** | RFC 2119, stated once | RFC 2119, §1.4 names authority | Structural (no MUST/SHOULD prose) | **Inconsistent** across docs | RFC 2119 embedded in field descs |
| **Versioning** | **Date strings** | **Major.Minor** | SemVer (spec 0.2 vs SDK 1.0) | Doc-ver vs wire-ver split | SemVer (in-band, twice) |
| **SDK core ergonomic** | Decorator facade `@mcp.tool()` | **Subclass** `AgentExecutor` | Decorator `@server.agent()` | Decorator `@anp_agent` | Stateless pipeline `load→execute` |
| **Schema→code** | TS → Pydantic | proto → Pydantic (Buf) | hand-kept mirror | code → wire (no schema) | JSON Schema → Pydantic (codegen) |
| **Hello-world weight** | ~6 lines / ~3 concepts | ~70 lines / ~10–12 concepts | ~10 lines / ~4 concepts | ~12 lines / ~4 (+ `did:`) | ~15 lines / ~5 (no authoring) |
| **First-success feedback** | Inspector GUI | 2-terminal CLI | **`curl`** (no client) | 2-terminal CLI | Notebook cells |
| **Headline adoption lever** | Reference host (Claude Desktop) + Inspector | Multi-transport + LF backing | "It's just REST" | "HTTP of the Agentic Web" narrative | Prebuilt catalog + notebooks |
| **Key cautionary tale** | Version churn + `FastMCP`→`MCPServer` rename | 0→1 **swapped schema tech** → compat cost | **Merged into A2A** (superseded) | **No source of truth → demonstrable drift** | Heavy vendor deps + hosted-key-gated demo |

**The spine of the whole analysis:** the five span the entire "*how do you define a schema*"
spectrum — author-from-scratch (MCP/A2A/agents.json), hand-keep-two-mirrors (ACP), and
no-machine-schema (ANP). The mature, trusted protocols cluster at **one machine-readable source
of truth + generate everything else**; the two that deviate (ACP's mirrors, ANP's prose-only)
**demonstrably drift**. This single convergence is the strongest signal Phase 1 produced, and it
validates DCP's already-chosen **Pydantic-v2-as-source-of-truth** decision (CLAUDE.md §3).

---

## A. Spec authoring

**① What the 5 did.** All the *mature* ones separate three things and never blur them: the
**normative contract** (a machine-readable artifact), **informative prose** (guides, examples,
rationale), and a **stated authority rule**. MCP: *"This specification defines the authoritative
protocol requirements, based on the TypeScript schema in schema.ts."* A2A goes furthest — a
numbered **§1.4 "Normative Content"** clause names `a2a.proto` as *"the single authoritative
normative definition"* and declares generated JSON non-normative, and the whole document is
ordered **abstract data model → abstract operations → concrete wire bindings last** (§3–4 before
§9–12), which is *what let one schema serve three transports*. agents.json collapses contract and
prose into one file — the JSON Schema **is** the spec, with RFC 2119 boilerplate stated once at
the top and MUST/SHOULD opening every field `description`. ANP is the counter-example: many
numbered `.md` docs, **no** machine-readable source, **inconsistent** normativity (RFC 2119 in
`03`, "Required/Optional" tables in `07`), and a **live drift** where the published site serves a
JSON-LD form of an object while repo `main` serves an incompatible plain-JSON form with the
JSON-LD section left *"To be supplemented"* — plus a field typo (`Infomations`) shipped in a
*released* normative example.

**② The distilled principle.** A spec is authored well when (1) exactly one artifact is
**named authoritative**, (2) RFC 2119 is declared **once** and used **consistently**, (3) prose
and examples are **informative and derived**, not a second source, and (4) the document is ordered
**semantic-core-first, transport-last** so bindings are appendices. ANP proves each negative:
no-named-authority → drift; inconsistent-2119 → ambiguous requirements; hand-copied examples →
typos in normative text.

**③ DCP decision.**
- `SPEC.md` stays **normative and terse**; guides/quickstart live elsewhere (Phase 5), never
  inside the normative doc.
- Add a **"Normative Content" clause** to `SPEC.md`: *the Pydantic v2 models in
  `src/dcp/schema/` are authoritative; the rendered JSON Schema and the SPEC field tables are
  generated and informative.* (Resolves the ambiguity ANP/ACP fell into; also closes SPEC open
  question **TBD-18/TBD-2**.)
- Declare **RFC 2119 once**, in one convention, applied uniformly — settles **TBD-2**.
- **Order `SPEC.md`** as *dialogue/state model → participation → orchestration operations →
  delivery bindings*, keeping Delivery (SPEC §3.4) an appendix-level adapter interface (mirrors
  A2A's Layer-1/2/3 ordering; already the shape of our SPEC §1–3).
- Give **every entity/layer a stable section ID and a per-section status** (ANP's sparse-numbering
  cataloguing method), so sections evolve and are cited independently even though SPEC is one file.
- Fix the **versioning scheme before v1** (see §D) — do not defer.

---

## B. Schema organization

**① What the 5 did.** The direction of generation varies; the *invariant* does not.
- **MCP**: hand-write `schema.ts` (TypeScript), **generate** `schema.json`. Inline JSDoc per
  field; `@category` tags route types to wire methods. One file per version, grouped by banner
  comments — **not** one-file-per-entity.
- **A2A**: hand-write `a2a.proto` (proto3), **generate** JSON Schema (uncommitted, non-normative)
  via **Buf + Google API-linter**; requiredness is an annotation
  (`[(google.api.field_behavior) = REQUIRED]`), every field carries a `//` doc comment, lifecycle
  is a first-class `enum TaskState` whose comments classify each state (terminal/interrupted).
- **agents.json**: hand-write JSON Schema draft-07, **generate** Pydantic via `datamodel-codegen`
  (proven by the `# generated by datamodel-codegen` header). RFC 2119 embedded in descriptions;
  `additionalProperties: true` for open objects, `false` where wire-precision matters; extends a
  borrowed standard (OpenAPI) via an `overrides` **patch list** rather than forking it.
- **ACP**: **two hand-kept mirrors** — `openapi.yaml` *and* Pydantic models in `acp_sdk/models/` —
  which is exactly why the spec is `0.2.0` while the SDK is `1.0.3`. Extensibility via open
  `metadata`; no capability handshake.
- **ANP**: **no machine-readable schema** at all; objects are prose field-tables + example JSON,
  semantics deferred to borrowed JSON-LD/schema.org vocabulary. This is the structural cause of
  its drift.

**② The distilled principle.** **One authored schema + generate every other representation** is
the near-universal practice (4 of 5); the direction (TS→JSON, proto→JSON, JSON→Pydantic) is a
free choice, but **two hand-authored mirrors (ACP) or zero (ANP) both drift**. Secondary
convergences: **document every field inline at the schema layer** (MCP JSDoc, A2A `//` comments,
agents.json descriptions) so the schema *is* the field reference; **make extension explicit** —
open maps (`metadata`/`_meta`), typed capability/extension objects, or patch lists — never
implicit; and **reuse neutral standards for neutral primitives** (agents.json reuses OpenAPI
`operationId`; several reuse JSON Schema for payloads, RFC 3339 for time) while confining novelty
to the domain layer.

**③ DCP decision.**
- **Pydantic v2 models are the single source of truth** (CLAUDE.md §3). **Generate** JSON Schema
  *from* the models; **generate** SPEC.md field tables *from* the model field docstrings. **Never
  hand-edit generated artifacts** — carry a `generated, do not edit` banner (agents.json's
  regeneration-clobber lesson).
- **Never keep two authored schemas.** ACP's mirror trap and its `0.2.0`-vs-`1.0.3` mismatch are
  the explicit thing we are avoiding.
- **Docstring every field with MUST/SHOULD-worded normativity**; those docstrings render into
  SPEC.md, so validation and prose cannot disagree (MCP + agents.json, two independent examples).
- Organize models **by SPEC layer, not one mega-file** — `schema/` sub-models grouped to match
  Dialogue-State / Participation / Orchestration / Delivery (banner-comment grouping like MCP/A2A).
- **Make lifecycle a first-class typed value** with the terminal/interrupted taxonomy documented in
  the model itself (A2A's `enum`-with-classifying-comments method — *method*, not its states);
  directly informs SPEC **TBD-3/TBD-16** (termination states) and **TBD-5** (response modes).
- **Explicit extension points only** — a documented, typed extension/`metadata` field where we
  want openness (informs **TBD-1**), never silent tolerate-unknown everywhere.
- **Round-trip every SPEC example through the schema in CI** (parse → validate → re-serialize); a
  failing example fails the build. This is the concrete guard against ANP's `Infomations`-typo and
  "To be supplemented" failure mode, and it operationalizes CLAUDE.md §6's "examples valid against
  schemas."

---

## C. SDK architecture

**① What the 5 did.**
- **Package layout mirrors the spec** everywhere: client/server/shared/models splits (MCP, ACP
  `acp_sdk/`, A2A `src/a2a/`) or **one module per spec section** (ANP `anp/` = auth/wns/proof/
  crawler/meta_protocol…, a literal table of contents). All ship **`py.typed`**.
- **Core ergonomic splits two ways.** *Decorator/registration facade* — MCP `@mcp.tool()`, ACP
  `@server.agent()` (an async generator that `yield`s), ANP `@anp_agent`/`@interface` — keeps
  hello-world short **because type hints auto-derive the schema/manifest** and the docstring/
  function-name derive identity (ACP: function name→agent name, docstring→description). *Subclass
  an interface* — A2A's `AgentExecutor.execute(context, event_queue)` with a manually driven
  `TaskUpdater` state machine — exposes the machinery and costs ~10–12 concepts and ~70 lines
  before first run.
- **Types are derived from the canonical schema**, not independently authored (MCP TS→Pydantic,
  A2A proto→Pydantic via Buf, agents.json JSON-Schema→Pydantic codegen). ACP's hand-kept mirror is
  the exception that drifts.
- **I/O is isolated at the edges** in every one: MCP pluggable transports (stdio/HTTP/SSE); A2A
  route factories (`create_jsonrpc_routes`/gRPC/REST) mounted on any ASGI app; ACP hides FastAPI
  behind `Server` and puts persistence behind a **pluggable `Store`** (memory/redis/postgres);
  agents.json is a **stateless pipeline** with no server at all.
- **Public surface: small curated facade over a fuller low-level API.** agents.json exports **5
  names**, ACP's server exports **~4** first-touch names; A2A is broader (~10 symbols) and pushes
  convenience into a `helpers/` module.

**② The distilled principle.** The SDK that gets used pairs **(a) a tiny decorator/registration
facade** where **Python types + function introspection drive the schema/descriptor** (so
hello-world is short and the developer writes *intent*, not plumbing), over **(b) a
transport-agnostic core whose types are generated from the canonical schema**, with **(c) all I/O
— transport and persistence — behind pluggable interfaces at the edges**, and **(d) a small
curated `__init__`** hiding a fuller low-level API. A2A's subclass-a-state-machine model is the
measured adoption tax to avoid; ACP's hand-kept types are the drift to avoid.

**③ DCP decision.**
- **`src/dcp/` module names match SPEC layers 1:1** — `schema/`, `core/`, `orchestration/`,
  `delivery/` (already in CLAUDE.md §1) — so the package reads as the spec's table of contents
  (ANP's legibility method, MCP/ACP's spec-mirroring split).
- **Thin decorator/registration facade** for authoring roles/participants where **Python type
  hints drive validation** and **function introspection (name, signature, docstring) derives the
  descriptor** (MCP + ACP + ANP mechanism). Budget hello-world at **MCP-low, not A2A-high** (see
  §D metric).
- **Hide the orchestration state machine** behind the facade — the newcomer must *not* hand-drive
  pre/post-action oversight (contrast A2A's manual `TaskUpdater`). This is where DCP's value lives
  (SPEC §1.4/§3.3); we manage it, the user doesn't.
- **Types generated from the Pydantic source of truth**; core is **transport-agnostic and
  event-emitting** (CLAUDE.md §3), with **Delivery adapters** (SPEC §3.4) and a **pluggable state
  Store** (ACP's memory/redis/postgres pattern) behind interfaces. Every state change emits an
  `Event`; the dialogue is replayable from its event log (SPEC §1.6).
- **Small curated `__init__`** (target a handful of verbs, agents.json/ACP scale) over a fuller
  low-level API for advanced users. Ship **`py.typed`**.
- **Async-first** for orchestration and participant invocation (all references' choice), sync
  convenience wrapper only where it clearly helps.

---

## D. Docs, onboarding & release

**① What the 5 did.**
- **Three/four-surface docs** everywhere mature: **quickstart ≠ conceptual guide ≠ normative
  reference ≠ SDK reference** (MCP's site split, A2A's Home/Documentation/Specification/Resources,
  ACP's `introduction/`→`core-concepts/`→`spec/`→`sdks/`). A newcomer reaches a running demo
  **without** reading the normative prose.
- **First-success friction is measurable and it drove adoption.** Lowest: **ACP `curl`** (no
  client SDK, GUI, or host needed) and **agents.json notebooks** (zero schema authoring — point at
  a pre-written file). **MCP**: ~6 lines + an **Inspector GUI** and a **reference host (Claude
  Desktop)** so success is *visual and instant*. Highest: **A2A** (~10 concepts, two files,
  two-terminal loop, no inspector) and **ANP** (a `did:` identifier is mandatory just to run —
  a hello-world→production cliff).
- **Docs-that-can't-drift-from-code:** A2A's tutorial **transcludes exact line-ranges** from the
  runnable `helloworld` sample via `--8<--` markers, so quickstart and working code cannot silently
  diverge.
- **Prebuilt catalog lowers "who authors the file?":** agents.json ships ~10 ready-made specs + a
  registry + notebooks so the hard authoring step is pre-done; MCP ships reference servers.
- **Release/governance:** all distribute via **PyPI**; MCP uses **date revisions**, A2A/ACP/
  agents.json **SemVer**. A2A **materializes governance in-repo** — `GOVERNANCE.md`,
  `MAINTAINERS.md`, an **`adrs/` decision-record trail**, `CHANGELOG`, and a `whats-new` migration
  guide — which *built adopter trust across a major redesign*. Cautionary: **ACP was absorbed into
  A2A** (positioning not settled → adopters stranded); **ANP is single-maintainer** (bus factor);
  agents.json's **best demo is gated on a hosted `api.wild-card.ai` key** and its core package
  **hard-deps on heavy vendor SDKs** (stripe/tweepy/google/…).

**② The distilled principle.** Adoption is won by **minimizing pieces-to-first-success** (fewest
concepts, no mandatory companion infra, ideally a visual or one-command result), **separating the
four doc surfaces**, **transcluding real sample code into the quickstart** so it never rots,
**shipping a catalog** so users run before they author, and **materializing governance +
versioning in-repo from the start**. The cautionary cluster: don't gate the best experience on a
hosted service, don't drag heavy deps into core, don't require foundational machinery (identity,
DB) for hello-world, and settle positioning/versioning *before* promoting adoption.

**③ DCP decision.**
- **Four doc surfaces** (Phase 5 `docs/`): quickstart · concepts · generated normative reference ·
  SDK reference. First success needs **only** `pip install` + run + one command to *watch a
  dialogue run* — no mandatory companion tool, no API key, no `did:`-style prerequisite.
- **Adopt an explicit "concepts-to-first-success" budget** and hold hello-world to MCP-low; treat
  regressions in that count as adoption bugs. (Directly from the A2A-vs-MCP contrast.)
- **Ship a reference orchestrator + a replay/inspector viewer** so the first result is *visual*
  (MCP's Inspector + reference-host lever), replaying the event log (SPEC §1.6) — not just stdout.
- **Transclude the canonical hello-world** into the quickstart via snippet markers (A2A's `--8<--`
  method), so docs track the SDK automatically.
- **Ship a small catalog of ready-made dialogue presets** (roles/orchestration configs) so users
  *run* before they *author* a topology (agents.json's catalog method) — a user should never have
  to hand-write a valid spec file as step one.
- **Keep the core package dependency-light** (schema + orchestration only); transport/persistence/
  model-provider integrations go in **optional extras behind interfaces** (agents.json's
  heavy-core anti-pattern; ANP's `[api]` extra as the good pattern). The **fully-local path is the
  headline demo** — never gate it on a hosted endpoint.
- **Materialize governance/versioning in-repo now:** the **STATUS.md Decision Log is our ADR
  trail**; keep a `CHANGELOG`; **fix one version scheme spanning spec and SDK before v1** (avoid
  ACP's `0.2.0`/`1.0.3` split) and **echo a protocol-version string on the wire** (MCP/A2A). Write
  migration notes for any breaking change; treat public SDK identifier renames as breaking
  (MCP's `FastMCP`→`MCPServer` lesson).

---

## 5. Consolidated DCP playbook (the checklist we will actually follow)

**Spec (Phase 3):**
1. `SPEC.md` normative + terse; guides live outside it.
2. A **"Normative Content"** clause: Pydantic models authoritative, JSON Schema + field tables
   generated/informative.
3. RFC 2119 declared once, applied uniformly.
4. Ordered semantic-core-first, delivery-bindings-last; Delivery is an adapter appendix.
5. Stable per-section IDs + status headers.
6. One fixed version scheme (spec+SDK), protocol-version echoed on the wire.

**Schema (Phase 3→4):**
7. **Pydantic v2 = single source of truth**; generate JSON Schema + SPEC tables from it; never
   hand-edit generated files; never a second authored mirror.
8. Docstring every field with MUST/SHOULD normativity → renders into SPEC.
9. Group models by SPEC layer; lifecycle/status as first-class typed enums with classifying
   comments.
10. Explicit, typed extension points only.
11. **CI round-trips every SPEC example through the schema.**

**SDK (Phase 4):**
12. `src/dcp/` modules name-match SPEC layers 1:1.
13. Thin decorator/registration facade; type hints + function introspection derive schema &
    descriptors; hide the orchestration state machine.
14. Types generated from the source of truth; transport-agnostic, event-emitting core; replayable
    from the event log.
15. Delivery adapters + pluggable state Store behind interfaces; I/O only at the edges.
16. Small curated `__init__` over a fuller low-level API; ship `py.typed`; async-first.

**Docs & release (Phase 5):**
17. Four doc surfaces; first success = install + run + one command, no mandatory companion/infra/key.
18. Explicit concepts-to-first-success budget (MCP-low).
19. Reference orchestrator + replay viewer for visual first success.
20. Transclude the canonical hello-world into the quickstart.
21. Ship a preset catalog so users run before they author.
22. Dependency-light core; integrations as optional extras; local path is the headline demo.
23. In-repo governance: Decision Log as ADR trail, CHANGELOG, migration notes, breaking-rename
    discipline.

---

## 6. Anti-patterns to avoid (each from a real cautionary tale)

- **Two hand-authored schema mirrors** → drift + version mismatch. *(ACP: `openapi.yaml` +
  Pydantic; spec `0.2.0` vs SDK `1.0.3`.)*
- **No machine-readable source of truth** → site/repo divergence, typos in normative examples,
  inconsistent normativity. *(ANP: JSON-LD-vs-plain-JSON split, `Infomations`, "To be
  supplemented".)*
- **Changing the source-of-truth schema technology after 1.0** → compat module + migration tax.
  *(A2A 0→1 swapped JSON-Schema-era artifacts for proto-normative.)*
- **Heavy hello-world / mandatory foundational machinery** → adoption friction. *(A2A's manual task
  state machine; ANP's required `did:`.)*
- **Core package hard-depends on heavy vendor SDKs** → coupling for a nominal spec parser.
  *(agents.json core deps on stripe/tweepy/google/hubspot/slack.)*
- **Best demo gated on a hosted service / vendor key** → lock-in. *(agents.json's dynamic-selection
  needs `api.wild-card.ai`.)*
- **Overlapping in-house standards without settled positioning** → adopters stranded by
  consolidation. *(ACP merged into A2A.)*
- **Single-maintainer, informal governance** → bus factor, slow formal versioning. *(ANP.)*
- **Public SDK identifier renames treated as non-breaking.** *(MCP's `FastMCP`→`MCPServer`.)*

---

## 7. Decisions to record (feeds STATUS.md Decision Log + SPEC.md open questions)

1. **Build-on vs author-your-own schema — DCP authors its own.** agents.json's build-on-OpenAPI is
   a legitimate fork, but **no mature host standard exists for *dialogue* semantics** (roles,
   participation, orchestration oversight, human gates), so authoring our own Pydantic-first schema
   is the defensible choice. **However:** reuse neutral standards for neutral primitives — JSON
   Schema for message *payloads*, RFC 3339 for timestamps, standard MIME types — and confine
   novelty to the dialogue layer. *(Log as a decision; relevant to SPEC TBD-1/TBD-18.)*
2. **Pydantic v2 is the single source of truth; generation is one-directional (models → JSON
   Schema → doc tables).** Confirms CLAUDE.md §3 against 4/5 references; explicitly rejects ACP's
   two-mirror pattern and ANP's no-schema pattern.
3. **One version scheme spanning spec + SDK, fixed before v1, with a wire protocol-version field.**
   Resolves the ACP split and the A2A-schema-swap risk pre-emptively. *(New; feeds a SPEC
   versioning section and closes part of TBD-2.)*
4. **Several Phase-1 findings pre-answer SPEC open questions** and should be triaged in Phase 3:
   lifecycle-as-typed-enum method → **TBD-3, TBD-16**; explicit typed extension points → **TBD-1**;
   named-authority + uniform RFC 2119 → **TBD-2, TBD-18**; response-mode enumeration via first-class
   enums → **TBD-5**. *(Method only — the DCP values themselves are still derived from
   `protocol_design.md`, never borrowed.)*

---

## 8. What the references could NOT teach us (gaps DCP must solve alone)

All five are **agent-centric or tool-centric**; none is **dialogue-centric with humans as
first-class, required/optional/supervisory/spontaneous participants** (SPEC §3.2). So the
references give us **method** for authoring/schematizing/shipping, but **no methodology precedent**
for: the role↔participant distinction, orchestrator *oversight* (pre/post-action verification),
human-intervention modes (gate/optional/open-mic), and multi-party turn orchestration. These are
DCP's novel surface and must be specified from `protocol_design.md` in Phase 3 — the references
tell us *how to write and ship a protocol well*, not *what our protocol says*.
