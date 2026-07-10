# STATUS.md — Project Progress Tracker

**Read this first every session** (per CLAUDE.md §5). It is the single source of truth for
where the project stands.

- **Current phase:** **Phase 5 — Docs & Release (docs + packaging pass) COMPLETE & green; awaiting
  owner review.** Onboarding docs written (`README.md`, `docs/{quickstart,concepts,guide-hosting,
  api-reference}.md`, `CHANGELOG.md`) with every snippet grounded in the real API; pyproject metadata
  filled and **editable install verified**. Deferred per owner: license choice, DB hardening (Alembic
  + Postgres CI), PyPI publish. Gate green (174 passed, 2 live-skipped). Phase 4 (M0–M9 + M5.1) stands.
  Earlier context ↓.
- **Prior — Phase 4 M5.1 Oversight & Control** (owner review of the SDK found a real gap; now fixed). The orchestrator now genuinely realizes its **control + oversight**
  mandate (D11): verification records **drive** the loop rather than decorate it. **Pre → recovery**
  (`inject_context` retry / `choose_alternative` re-decide / `request_human` / `wait_gate` /
  `stop`→provisional; bounded by `max_recovery_attempts`). **Post → routing** (`request_revision`
  bounded by `max_revisions`, `request_verification`→verifier role, `escalate_gate`→human gate,
  `stop`, `continue`). Records tightened from loose `str` to **enums** + added `verdict`/`escalated`
  (post) and `recovered` (pre). New `ScriptedOversight` for deterministic branch tests. Prior Phase-4
  work (M0–M9: schema/state/participation/providers/registry/delivery/facade/hello-world/conformance)
  stands. All 5 recovery actions + all 5 routing outcomes are now genuinely wired (incl. deepened
  `request_human`/`wait_gate`). ruff + mypy(strict, 36 files) + pytest (**174 passed, 2 live-skipped**)
  green; hello-world still runs to `done`. Next: **Phase 5** (docs/release) + Phase-3 closeout (figures).
- **Last updated:** 2026-07-09
- **Overall goal:** A genuinely usable standalone protocol (DCP) + Python SDK. Reference
  protocols inform *method only*, never design.

---

## Phase Checklists

### Phase 0 — Bootstrap
- [x] `CLAUDE.md` working guide created
- [x] `SPEC.md` skeleton created from `protocol_design.md` (20 open questions logged)
- [x] `STATUS.md` created
- [ ] Owner review of the three bootstrap files ← **awaiting review, do not proceed past this**

### Phase 1 — Reference Analysis (`research/*.md`)
Focus: *how each protocol was made* (spec authoring, schema definition, SDK architecture,
hello-world, onboarding). Use the CLAUDE.md §4 template.
- [x] `research/mcp.md` — done 2026-07-09, from primary sources (spec site, schema.ts, python-sdk)
- [x] `research/a2a.md` — done 2026-07-09 (proto3 canonical schema, LF governance, 0.x→1.0 redesign)
- [x] `research/acp.md` — done 2026-07-09 (OpenAPI-authored, REST-first; **note: ACP merged into A2A**)
- [x] `research/anp.md` — done 2026-07-09 (DID/JSON-LD, multi-doc spec; **live JSON-LD-vs-JSON drift**)
- [x] `research/agents-json.md` — done 2026-07-09 (built ON OpenAPI; **agent-json.com is a different project**)

### Phase 2 — Methodology Distillation (`methodology/methodology.md`) — done 2026-07-09
- [x] Cross-protocol synthesis of spec-authoring practices (§A)
- [x] Cross-protocol synthesis of schema-organization practices (§B)
- [x] Cross-protocol synthesis of SDK-architecture practices (§C)
- [x] Cross-protocol synthesis of docs/onboarding/release practices (§D)
- [x] DCP playbook: 23-item consolidated checklist (§5) + anti-patterns (§6) + decisions (§7)

### Phase 3 — Write DCP Spec (`SPEC.md`) — first full draft 2026-07-09
- [x] Restructure §1 around D1 (DialogueTemplate + DialogueInstance) + fold in D3/D4/D5/D6
- [x] Add Registry & Hosting layer → 5 layers (§3.4); Normative Content clause + RFC 2119 + SemVer
- [x] Resolve/defer each open question TBD-1 … TBD-29 (28 resolved, TBD-18 deferred to Phase 4)
- [x] §4 interim normative field tables for all entities (full Pydantic in Phase 4)
- [x] §5 conformance criteria; §6 acceptance criteria (feeds Phase 4 tests)
- [ ] **Owner confirms the 4 〔derived〕 resolutions** (TBD-3, TBD-5, TBD-9, TBD-25)
- [ ] Revise figures/ to match D1–D6 + 5-layer model (currently pre-decision)
- [ ] Pin TBD-18 field-level constraints during Phase-4 Pydantic authoring
- [ ] All examples validated against schemas (CI round-trip — Phase 4)

### Phase 4 — Python SDK (`sdk/`) — detailed plan in `sdk/PLAN.md` (revised per A1–A5)
Ten tests-first milestones M0–M9 (each ends green on ruff+mypy+pytest); **owner reviews per group**:
- [x] **M0** Scaffolding & tooling — pyproject, `src/dcp` layout, `errors.py`, `config.py`, `.env.example`,
  ruff/mypy(strict)/pytest wired; venv on Python 3.13. Done 2026-07-09.
- [x] **M1** Schema layer — Pydantic v2 per SPEC §4 (enums/values/entities/records, `ModelBinding`
  D8); pins TBD-18 (interim); `gen_schema.py` emits 12 JSON Schemas; 40 tests green. Done 2026-07-09.
- [x] **M2** State layer + **real DB `Store`** (SQLAlchemy `SqlStore`; SQLite dev/`:memory:` tests,
  Postgres extra); append-only log, deterministic `replay` reducer, full-replay `restore` (D3/TBD-28).
  Done 2026-07-09.
- [x] **M3** Participation — `cast_roles` (4-step precedence), access tiers (`own⊃speak⊃observe`,
  observe-can't-cast), `ParticipantRegistry` (Store-backed, discoverable filter). Done 2026-07-09.
- [x] **M4** **Model Provider** — `ModelProvider` protocol + `OpenAIProvider` (default, `gpt-5.4`) +
  `AnthropicProvider` + `MockProvider`; `build_provider(binding)` per-binding factory (D7/D8);
  stubbed-client unit tests + key-gated live tests (skip w/o key). Done 2026-07-09.
- [x] **M5** Orchestration — `Orchestrator` loop (plan/flow decisions, pre/post oversight records,
  serialized transcript TBD-25, human gateway w/ gate/timeout→provisional, termination priority,
  open-mic); appends to log, returns full-replay instance (D3). Done 2026-07-09.
- [x] **M6** Registry & Hosting + Access/Auth (D5/D6) — `Registry` (two catalogs + hosting ops),
  template immutability per `(id,version)`, `instantiate`→`created`+owner grant, `grant_access`
  (own-only), visibility-gated `join`(→full replay)/`leave`, `restore`; `Authenticator` +
  `SimpleTokenAuthenticator` + anonymous dev mode. Store gained templates/grants tables. Done 2026-07-09.
- [x] **M7** Delivery — `HttpSseDelivery`/`build_app` on Starlette: REST (templates/participants/
  instances/join/leave) + **SSE** event stream (replay-then-tail, D3); `Delivery` protocol keeps core
  transport-agnostic (no Starlette import outside `dcp.delivery`). Done 2026-07-09.
- [x] **Group-D completion pass** (owner design review, 2026-07-10) — discovery/introspection
  (`server_info`/§1.11 **D9**, `list_instances`/`get_instance`, participant + template-version read
  endpoints, `resumable` hint), **orchestrator-resume defect fixed** (D3/§2.9), and standalone
  **`TemplateGenerator`** auto-generation (**D10**, `POST /templates/generate`). New modules
  `dcp.authoring`; `dcp.provider.available_providers`.
- [x] **M8** Facade + hello-world — `dcp.Server` (store+registry+providers, `run`/resume);
  `docs/examples/hello_dialogue_mock.py` (key-free, runs to `done`) + `hello_dialogue.py` (real model
  via `.env`). Facade + example-runs tests. Done 2026-07-10.
- [x] **M9** Conformance suite — `tests/conformance/test_acceptance.py`, one MUST vector per SPEC §6
  (+ resume, discovery); surfaced+fixed the `allow_open_mic` gate (§2.8/§6). `scripts/check`
  (ruff+mypy+pytest) is the CI gate. Done 2026-07-10.
Review groups (A5): A=M0–M1 · B=M2–M3 · C=M4–M5 · D=M6–M7 · E=M8–M9.

### Phase 5 — Docs & Release (`sdk/docs/`, `sdk/README.md`)
- [x] Quickstart (`docs/quickstart.md`: install → mock hello-world → real model → HTTP server). Done 2026-07-10.
- [x] API reference + guides (`docs/api-reference.md`, `docs/concepts.md`, `docs/guide-hosting.md`);
  front-door `README.md` rewritten; `CHANGELOG.md`. All snippets exercised against the real API. Done 2026-07-10.
- [x] Runnable examples (`docs/examples/hello_dialogue_mock.py` + `hello_dialogue.py`, from M8).
- [~] Packaging / distribution — pyproject metadata done (keywords, classifiers, `py.typed`, description);
  **editable install verified** (`pip install -e .`, imports from anywhere). **Not yet on PyPI**; license
  deferred (owner). Done-except-publish 2026-07-10.
- [~] New-user onboarding path — docs cover install → hello-world → next step; installability + every
  snippet verified. Not yet validated by an actual unaided new user (owner check).
- [ ] **DB hardening for public release (deferred, owner-confirmed):** Alembic migrations (replace
  `create_all`); Postgres CI job.
- [ ] **License selection (deferred, owner):** metadata placeholder `LicenseRef-UNLICENSED`; no `LICENSE` file yet.

---

## Decision Log

Append newest at top. Format: `YYYY-MM-DD — decision — why — alternatives rejected`.

- **2026-07-09 — Pre-Phase-3 design review: core-concept coverage check against the draft.**
  Owner asked whether 4 core points are covered. Verdict: human participation (✅) and orchestrator
  = control+oversight (✅) are solid; **dialogue registration/reuse by others (❌ missing — only
  undefined terms)** and **high-usability custom/auto build (⚠️ partial, mostly TBD)**. Surfaced 7
  structural problems (A–G): template/instance conflation, no registry entity, no access model, no
  identity model, single-threaded orchestrator vs multi-user, flow-vs-orchestrator dual control,
  hosting-vs-transport-agnostic tension. — Alt rejected: proceeding to Phase 3 on an incomplete
  concept model.
- **2026-07-09 — DECISION D1: Template and Instance are two first-class entities.** A
  **DialogueTemplate** (reusable definition) is what gets registered; a **DialogueInstance** is
  created from it and carries runtime state. Splits the monolithic `Dialogue`. — Resolves problem
  A; enables reuse (point 2) and save/edit (point 4). — Alt rejected: keeping one `Dialogue` entity.
  Residual: field partition + template versioning = SPEC TBD-21.
- **2026-07-09 — DECISION D2: DCP is a server-hosted model.** A DCP server hosts dialogues;
  templates are registered, instances are addressable & joinable by other users; register/discover/
  instantiate/join/leave are **semantic** operations, independent of transport (not the Delivery
  layer). — Realizes point 2; matches the ACP-style server model (method reference only). — Alt
  rejected: stateless client-side library (agents.json-style) — can't host/share dialogues.
  Residual: registry ops = TBD-22, layer placement = TBD-27.
- **2026-07-09 — DECISION D3: Restore (history-derived monitoring).** An instance persists its full
  history (messages + events); the **orchestrator can restore/rehydrate its oversight state from that
  log at any time**, with no authoritative state that isn't reconstructable from history. Also the
  substrate for late joiners (D2). — Owner idea; makes monitoring resumable in the server-hosted,
  long-lived, joinable model. — Alt rejected: orchestrator holding hidden in-memory-only state.
- **2026-07-09 — TBD-28 RESOLVED (D3 contract): restore = full replay; same path serves late
  joiners.** Restore is a **full replay** of the persisted log (not snapshot+delta), and the **same
  restore mechanism serves late-joining participants/observers** catching up — one path for both.
  — Owner decision; simplest correct model, and unifies orchestrator-restore with joiner-catchup.
  — Alt rejected: snapshot+delta (added complexity for no v1 benefit); separate paths for restore
  vs. join.
- **2026-07-09 — DECISION D4: Humans are registered participants, like agents.** Real users, like
  agents, are **registered to the server** with **auth + profile/description + a discoverability
  flag** — a server-level persistent identity, distinct from the dialogue-local Role they're cast
  into. — Owner idea; **gives the identity model (formerly TBD-24 "owner-undecided") its shape** and
  unifies the participant registry (TBD-6). — Alt rejected: ad-hoc handles with no registration.
  Residuals: auth mechanism = TBD-24; one-vs-two registries = TBD-29; "profile" vs `Role`
  terminology to disambiguate in Phase 3.
- **2026-07-10 — Phase 5 (docs & release) — docs + packaging pass.** Owner chose "docs + packaging
  now; defer DB hardening" and "decide license later". Wrote the onboarding path: rewrote the
  front-door `sdk/README.md` (what DCP is + install + a 30-line key-free hello-world + feature list +
  doc links), `docs/quickstart.md` (install → mock → real model → HTTP/SSE server), `docs/concepts.md`
  (entities, five layers, event-log-as-truth, lifecycle, human modes, the D11 oversight/control loop,
  access/identity, extension), `docs/guide-hosting.md` (Registry, immutability, access tiers +
  visibility, bearer/anon auth, `server_info`, auto-generation, the full HTTP+SSE endpoint table), and
  `docs/api-reference.md` (curated public surface with signatures). Added `CHANGELOG.md`. **Every code
  snippet is grounded in the real API** — the hello-world is the tested example; the HTTP/auth/
  server_info/generate snippets were executed against the package. **Packaging:** filled pyproject
  metadata (description, keywords, classifiers, `py.typed`); **verified installability** —
  `pip install -e .` builds a wheel and `import dcp` works from an arbitrary cwd (no PYTHONPATH). Gate
  stays green (174 passed, 2 live-skipped). — Deferred per owner: **license** (metadata placeholder
  `LicenseRef-UNLICENSED`, no `LICENSE` file), **DB hardening** (Alembic + Postgres CI), **PyPI
  publish**. — Alt rejected: committing Apache-2.0 prematurely (owner will choose); wiring a doc
  generator (mkdocstrings/pdoc) now (a curated hand-written reference is accurate and dependency-free
  for this stage).
- **2026-07-10 — M5.1 Oversight & Control (owner review of Phase-4 SDK found a real gap).** Owner
  flagged that oversight was a stub: the orchestrator *emitted* pre/post verification records but never
  *acted* on them, its control repertoire was only `select_speaker|stop` (2 of the 7 §1.7 actions), and
  `DefaultOversight` returned hardcoded "ready/continue". Confirmed via [orchestrator.py] (pre result
  ignored; post only handled `outcome==stop`) and [actions.py] (2-verb `OrchestratorAction`). This was
  the central functional gap — the orchestrator's "control + oversight" mandate was half-wired. Fixed
  (spec-first): **DECISION D11 — oversight governs control.** SPEC §1.7 now mandates that the loop act
  on the records: **pre → recovery** (`inject_context` [emit `context_injected`, retry same candidate]
  / `choose_alternative` [re-decide] / `request_human` / `wait_gate` / `stop`→provisional), bounded by
  `max_recovery_attempts` (default 3); **post → routing** (`request_revision` re-invokes the same role
  as a new turn, bounded by `max_revisions` default 2, emit `revision_requested`; `request_verification`
  routes a turn to a verifier role, emit `verification_requested`; `escalate_gate` opens a human gate;
  `stop`; `continue`). Records tightened to **enums** (10 new: `Readiness`, `Availability`,
  `CapabilityMatch`, `RoleState`, `ContextSufficiency`, `ExecutionFeasibility`, `RecommendedAction`,
  `Verdict`, `Assessment`, `PostOutcome`) — closes the oversight part of TBD-18 — plus new fields
  `PreActionVerification.recovered` and `PostActionVerification.{verdict, escalated}` (SPEC §4.7/§4.8
  updated). Orchestrator refactored: `_contribute` returns a terminal signal instead of self-
  terminating; per-turn `_ensure_ready` (recovery) + `_verify_and_route` (routing); unique message ids
  via a counter (survive revisions); a step budget guards recovery/re-decide loops. Added
  `ScriptedOversight` (FIFO records) so every branch is tested without a model. **+9 tests → 171 passed,
  2 live-skipped**; ruff + mypy strict (36 files) clean; schemas regenerated; hello-world still runs to
  `done`. — Alt rejected: leaving oversight as audit-only (misrepresents DCP's core claim); making
  revision a second message in the same turn (would break the one-contribution-per-turn invariant — each
  revision/verification is its own turn instead).
- **2026-07-10 — M5.1 follow-up: deepened `request_human` + `wait_gate` pre-recovery (owner).** The two
  paths previously fell through to `redecide`; now they do real work. `request_human` solicits a cast
  human via the gateway (`human_input_pending` → `human_input_addressed`), injects the reply as context,
  and retries the candidate (leaves the request pending on timeout / no gateway → `redecide`).
  `wait_gate` restores the instance, blocks on each open gate via the gateway, emits `gate_resolved`,
  then retries (nothing open / no gateway → `redecide`). Added a dedicated aux-id counter; SPEC §1.7
  pre→recovery bullet updated to document both. +3 tests (request_human inject+retry, no-gateway→redecide,
  wait_gate resolve+retry) → **174 passed, 2 live-skipped**; ruff + mypy strict clean.
- **2026-07-10 — Phase 4 Group E (M8–M9) built and green; Phase 4 complete.** **M8 facade:**
  `dcp.Server` assembles `SqlStore` + `Registry` + model providers behind one object — catalog/hosting
  calls delegate to the Registry; `Server.run(instance_id, cast=…)` builds an `Orchestrator` (each
  agent's provider from its `model_binding`, else the orchestrator default from env) and runs **or
  resumes** to a terminal status. Two canonical hello-worlds: `docs/examples/hello_dialogue_mock.py`
  (key-free `MockProvider`, deterministic — prints a completed 3-role design-review transcript to
  `done`) and `hello_dialogue.py` (real provider via `.env`; orchestrator+agents on the configured
  model in plan mode, scripted human approval). **M9 conformance:** `tests/conformance/test_acceptance.py`
  maps each SPEC §6 criterion to a MUST vector (immutability, ownership, created→running, observe-not-
  castable, open-mic-enable, visibility/join, full-replay order, termination priority, gate-timeout→
  provisional, bearer/anon auth, replay determinism, resume, server_info). `scripts/check`
  (ruff + mypy --strict + pytest) is the single CI gate. **Gap found+fixed while writing conformance:**
  open-mic was accepted unconditionally though §6 requires it be rejected unless the template enables
  it — added normative `DialogueTemplate.allow_open_mic` (default false), enforced in
  `Orchestrator.submit_open_mic` (raises `OrchestrationError`), SPEC §2.8 updated to name the field.
  **+17 tests → 162 passed, 2 live-skipped**; ruff + mypy strict (36 files) clean; regenerated JSON
  Schemas. — Alt rejected: a metadata flag for open-mic (a first-class typed field per §1.10 is
  clearer); auto-deriving cast inside `Server.run` (kept cast explicit for a readable hello-world;
  `cast_roles` remains available for auto-casting).
- **2026-07-10 — Group-D completion pass (owner design review): discovery surface, resume fix,
  auto-generation.** Owner flagged that delivery was too thin (no way to see available model
  providers, registered participants, instance history, or resume) and asked whether the orchestrator
  can author a template from a question then instantiate. Outcomes:
  **(1) DECISION D9 — ServerInfo/capabilities (SPEC §1.11, concretizes §1.10):** a server advertises
  `{dcp_version, capabilities{auto_generate,verifier_routing}, model_providers[{provider,configured}]}`;
  credentials never appear (only the `configured` boolean). Added `dcp.provider.available_providers`,
  `Registry.server_info`, `GET /`. DCP-native (derived from §1.10), not a borrowed handshake.
  **(2) DECISION D10 — auto-generation is a standalone generator, NOT an orchestrator action (SPEC
  §2.2):** `dcp.authoring.TemplateGenerator` reuses `ModelProvider.structured` with `DialogueTemplate`
  as the schema to turn a query into a **draft** (unregistered) template; `query→draft→(edit)→register→
  instantiate→run`. Rationale: the orchestrator (§1.7) controls a *running* instance and holds no state
  outside a log (D3); authoring is upstream/instance-less — folding it in would overload the control
  loop. Wired to `Registry.generate_template` + `POST /templates/generate` (capability error/501 when
  no generator). **(3) Fixed an orchestrator-resume defect (D3/§2.9 MUST):** M5 `Orchestrator.run()`
  always re-emitted `instance_started`/`roles_cast`/joins and restarted at turn 0 with an empty
  transcript — so it could *read* a restored instance but not *continue* one. Now `run()` restores
  first, returns immediately if terminal (read-only), else `_hydrate`s turn/messages/last-speaker and
  `_bootstrap`s only the missing start/cast/join events → genuine resume. Clarified SPEC §2.9 (resume =
  restore + continue; MUST NOT re-bootstrap; resumable ⇔ non-terminal) + added `is_resumable` helper
  and a `resumable` hint on the HTTP instance view. **(4) Delivery completion:** surfaced the
  already-specced read ops over HTTP — `GET /participants`(+`?discoverable`), `GET /participants/{id}`,
  `GET /templates/{id}/versions/{v}`, `GET /instances` (visibility-filtered via `Registry.list_instances`),
  plus the `resumable` field on instance responses. **+19 tests → 145 passed, 2 live-skipped**; ruff +
  mypy strict (35 files) clean; 13 JSON Schemas emitted (added `ServerInfo`). SPEC edited first (§1.11,
  §2.2 D10, §2.9 resume, §3.4 ops list). — Alt rejected: `resumable` as a Pydantic computed field
  (would break `extra="forbid"` round-trips — kept it a delivery-view/helper concern); one-shot
  question→running-instance orchestrator action (owner chose the reviewable-draft generator).
- **2026-07-09 — Phase 4 Group D (M6–M7) built and green.** **M6 Registry & Hosting** (`dcp.registry`):
  one `Registry` surface over two catalogs (TBD-29) — templates + participants — plus hosting ops
  `instantiate`/`grant_access`/`join`/`leave`/`restore`. **Template immutability** enforced in the
  Store: re-registering `(id,version)` with different content raises `RegistryError`, identical
  re-register is idempotent, new version succeeds (SPEC §2.1/§6). `instantiate` sets caller as owner,
  status `created`, seats the owner at `own` tier (grant + `participant_joined`). **Access control
  (D5):** `grant_access` requires the grantor to hold `own`; `join` is visibility-gated — `public`→
  auto `observe`, `unlisted`/`private`→requires a grant (else `AccessError`) — and returns a **full
  replay** so the joiner catches up (D3, one path). **Auth (D6):** `Authenticator` protocol +
  `SimpleTokenAuthenticator` (token→one participant_id) + `AnonymousAuthenticator` (key-free dev mode,
  `@local`). Store extended with `templates`/`grants` tables + template/grant methods. **M7 Delivery**
  (`dcp.delivery`): `Delivery` protocol (transport-agnostic seam, no transport import) + `HttpSseDelivery`/
  `build_app` on **Starlette** — REST endpoints (register template/participant, instantiate, get
  instance, join, leave) and an **SSE** event stream with **replay-then-tail** (`?tail=false` gives a
  finite stream for deterministic tests); DCP errors mapped to HTTP (409 immutability, 403 access, 404
  unknown, 422 bad body). **126 tests** (100 prior + 18 registry: auth/immutability/hosting + 8
  delivery: REST + SSE order/late-join via Starlette `TestClient`), 2 live-skipped; ruff + mypy strict
  (33 files) clean. Impl fix: switched in-memory SQLite to `StaticPool` so the ASGI worker thread
  shares the schema (SingletonThreadPool gave the TestClient thread an empty DB). Installed
  starlette/uvicorn/sse-starlette/httpx into the venv (already declared in `pyproject`). — Alt
  rejected: registry-level events into a synthetic server log (no instance context; skipped for v1);
  push-based SSE bus coupling the core to delivery (kept Store-poll tail to preserve the seam).
- **2026-07-09 — Phase 4 Group C (M4–M5) built and green.** **M4 provider layer** (`dcp.provider`):
  provider-neutral `ModelProvider` (async `text`/`structured`) with three impls in separate modules —
  `OpenAIProvider` (default; `chat.completions.create`/`.parse`, verified in openai 2.45),
  `AnthropicProvider` (`messages.create`/`.parse`, anthropic 0.116), `MockProvider` (scripted, no
  network); `build_provider(binding)` per-binding factory + `orchestrator_binding(config)` (D7/D8;
  requires `DCP_MODEL` for real providers, never guessed — owner's `.env` sets `gpt-5.4`). Real
  providers use lazy client construction + typed-error→`ProviderError` mapping; verified via
  stubbed-client unit tests (adapter mapping) + key-gated live tests (skip w/o key, so CI stays
  green). **M5 orchestration** (`dcp.orchestration`): `Orchestrator.run()` drives a serialized
  transcript (≤1 contribution/turn, TBD-25) — decides via structured `OrchestratorAction` (plan) or
  the template `flow` graph; emits pre/post `*_ACTION_VERIFIED` records (pluggable `OversightPolicy`;
  `DefaultOversight` deterministic, `LlmOversight` model-backed); handles human roles via a
  `HumanGateway` (`ScriptedHumanGateway` for tests) with gate/required timeout→provisional; termination
  by `resolve_termination` priority error>budget>stopped>provisional>done; append-only to the store,
  returns full-replay instance (D3). **100 tests** (69 prior + provider mock/factory/stubbed +
  termination priority + 8 end-to-end orchestration runs), 2 live-skipped; ruff + mypy strict clean.
  — Alt rejected: LLM-driven oversight as the only path (kept a deterministic default so tests/demo
  need no model).
- **2026-07-09 — Phase 4 Group B (M2–M3) built and green.** **M2 state layer:** `dcp.state` with an
  append-only log where the **event log is authoritative** (D3) — `SqlStore` (SQLAlchemy 2.x; SQLite
  dev, `:memory:` tests, Postgres via `dcp[postgres]`) persists instances/log/participants; a
  deterministic `replay` reducer folds `messages+events` into status/turn/roster/gates/pending/budget;
  `restore(store, id)` = full replay (D3/TBD-28), the same path for orchestrator-rehydrate and
  late-joiner-catchup. **M3 participation:** `cast_roles` implements the SPEC §2.4 4-step precedence
  (explicit binding → id-match → capability overlap → persona fallback) with kind + tier enforcement;
  tier logic (`own⊃speak⊃observe`, `assert_castable` rejects observe per §6); `ParticipantRegistry`
  over the Store with discoverability filter (D4). **69 tests** total (store round-trip/append-only,
  reducer determinism, restore order, tiers, casting precedence, registry); ruff + mypy strict clean.
  Impl notes: SQLite drops tz on native DateTime → instance `created_at` stored as ISO string;
  installed `sqlalchemy>=2` into the venv. — Alt rejected: in-memory-only store (owner chose real DB).
- **2026-07-09 — DB: SQLite dev / Postgres prod (owner-confirmed, keep current).** Store is
  SQLAlchemy-URL-driven; default `sqlite:///./dcp.db` (tests `:memory:`), Postgres in production via
  `dcp[postgres]` (just change `DCP_DATABASE_URL`). Chosen over Postgres-only because production
  capability is identical (Postgres either way) while local dev/tests stay zero-friction — important
  for opening DCP to public/contributor use. **Follow-ups before public release (→ Phase 5):**
  (a) replace `create_all` with **Alembic migrations**; (b) add a **Postgres CI job** alongside the
  fast SQLite suite; keep code Postgres-compatible (already avoiding SQLite-specific behavior, e.g.
  ISO-string timestamps). — Alt rejected: Postgres-only (friction for devs/CI, no prod upside).
- **2026-07-09 — Phase 4 Group A (M0–M1) built and green.** Scaffolded `sdk/` (pyproject, `errors.py`,
  env-driven `config.py` with locked names, `.env.example`, `.gitignore`, ruff+mypy(strict)+pytest,
  `scripts/check`), and authored the M1 schema layer as the single source of truth: `enums.py`
  (first-class StrEnums per confirmed value spaces), `values.py` (incl. `ModelBinding` D8, no key
  field), `entities.py` (Role/Participant/DialogueTemplate/DialogueInstance/Message/Event; Message &
  Event frozen; `model_binding` agent-only validator), `records.py` (pre/post oversight, termination,
  roles_cast). `scripts/gen_schema.py` generates 12 JSON Schemas from the models (methodology item 7).
  **40 pytest tests** (M0 smoke + enum spaces + value validation + entity invariants + JSON round-trip
  for every top-level type, item 11); ruff clean; mypy strict clean. Env: Python 3.13 venv (system
  py was 3.9; used conda's 3.13). Two interim notes: TBD-18 constraints are basic (semver regex,
  non-empty strings) pending full pinning; oversight categorical fields typed `str`. — Alt rejected:
  editable-install for tests (used pytest `pythonpath=src` to keep M0–M1 dep-light).
- **2026-07-09 — DECISION D8: model binding is per-consumer (orchestrator vs per-agent), separated.**
  A `ModelBinding{provider, model}` (no key field) attaches to **(a)** the **Orchestrator** (§1.7,
  instance/server default from env) for control+oversight, and **(b)** each **agent Participant**
  (§1.5, set at registration/init; inherits orchestrator default if omitted) for that agent's
  contributions. `build_provider(binding)` is a **per-binding factory**, not a global — so one
  dialogue MAY mix providers/models (e.g. a GPT critic vs a Claude strategist). Keys resolve from
  env by provider. Added SPEC `ModelBinding` (§4.5b), `Participant.model_binding?`,
  `Orchestrator.model_binding`, and **TBD-30** (multi-tenant key mgmt, deferred). OpenAI model id
  supplied via `.env` (`DCP_MODEL`), not hardcoded. — Owner's per-agent-at-init instinct; single
  global provider would kill mixed-model dialogues. — Alt rejected: single global provider;
  separate-but-inherit-only (deferred per-agent override).
- **2026-07-09 — DECISION D7: multi-provider model layer; OpenAI default; both providers built.**
  Owner has both `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`. `ModelProvider` is provider-neutral;
  M4 ships **`OpenAIProvider` (default)** + **`AnthropicProvider`** + **`MockProvider`**, selected by
  `DCP_MODEL_PROVIDER` (default `openai`). **Locked env vars:** `DCP_MODEL_PROVIDER`, `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `DCP_MODEL`, `DCP_DATABASE_URL` (default `sqlite:///./dcp.db`). Anthropic
  default model `claude-opus-4-8`; **OpenAI default model id owner-supplied** (not guessed — needed
  before M4, not M0). Provider modules never mix SDKs. — Building both real impls now validates the
  abstraction isn't single-provider-shaped. — Alt rejected: Anthropic default / Anthropic-first-only.
- **2026-07-09 — Phase-4 architecture decided (A1–A5); plan revised to 10 milestones.**
  **A1: LLM is REQUIRED** (not pluggable-optional). A `ModelProvider` interface wraps all model
  calls; default impl **`AnthropicProvider`** (Anthropic SDK, `AsyncAnthropic`, default model
  `claude-opus-4-8`, adaptive thinking, `messages.parse` structured output, env-configured via
  `ANTHROPIC_API_KEY`); **local-model path deferred** (`dcp[local]`); **`MockProvider`** for
  deterministic tests + key-free demo. **A2: real DB** — `Store` on SQLAlchemy 2.x (SQLite dev /
  Postgres prod; tests use SQLite `:memory:`). **A3: HTTP+SSE** delivery on Starlette/uvicorn (SSE
  replay-then-tail for joiners). **A4** cut confirmed; **A5** review per logical group (A=M0–M1,
  B=M2–M3, C=M4–M5, D=M6–M7, E=M8–M9). — This is a deliberate shift from "dependency-light library"
  to "batteries-included server," justified because DCP is a server-hosted runtime (D2), not a spec
  parser; interfaces at every I/O edge preserve testability/swappability. Loaded the `claude-api`
  skill to ground the provider on current Anthropic SDK facts. — Alt rejected: LLM-pluggable-not-core
  / in-memory-store / in-process-only delivery (all overridden by owner).
- **2026-07-09 — Owner confirmed all 4 〔derived〕 resolutions: TBD-3, TBD-9, TBD-25, TBD-5.** Status
  enum, Event taxonomy, serialized-transcript concurrency locked as drafted.
- **2026-07-09 — TBD-5 resolved: `response_mode` → renamed `response_requirement`; 3-value enum kept;
  required-human timeout fix.** Owner questioned the concept's purpose; after explanation (it's the
  orchestrator's per-role wait/mandate policy — the mechanism that makes human-in-the-loop usable),
  owner chose to **keep the concept, rename to `response_requirement`**, and **keep the single
  3-value enum** (`required|optional|gate`) for v1. `gate` documented as "required + approval-decision
  semantics"; splitting `gate` into a separate `approval_gate` flag is a deferred, **non-breaking**
  future change. **Correctness fix applied** (surfaced during the soundness review): `human_policy`
  (wait window + `on_timeout`) now applies to **any waited human role — `required` as well as
  `gate`** — previously only gates had a timeout, so an unresponsive `required` human could hang the
  instance forever. — Alt rejected: 2-value enum with gate-as-runtime-only (diverges from the draft's
  founder example); splitting gate now (YAGNI for v1).
- **2026-07-09 — Phase 3 first full spec draft written (`SPEC.md` v0.2.0-draft).** Restructured
  around D1–D6: DialogueTemplate + DialogueInstance split; registered Participants; added a fifth
  **Registry & Hosting layer**; folded in access tiers, bearer auth, and restore. Added Normative
  Content clause (Pydantic authoritative), RFC 2119, and SemVer with a wire `dcp_version`. **Resolved
  28 of 29 TBDs** (TBD-18 field-constraints deferred to Phase-4 Pydantic authoring). Several
  resolutions are *derivations* from the draft + D1–D6, explicitly tagged 〔derived〕 and flagged for
  owner veto: **TBD-3** (instance status enum: created/running/awaiting + terminals), **TBD-5**
  (response_mode required/optional/gate semantics), **TBD-9** (Event type taxonomy), **TBD-25**
  (multi-user concurrency = serialized transcript + queued async inputs). Notable design calls made
  in-draft: `orchestration.mode ∈ {plan,flow}` with `flow` advisory-under-plan/binding-under-flow
  (TBD-11/12/26); termination priority error>budget>stopped>provisional>done (TBD-16); one Registry
  surface with two catalogs (TBD-29). — Design sourced only from `protocol_design.md` + D1–D6; no
  reference-protocol design imported. — Alt rejected: leaving TBDs open / silently deciding the
  derived ones without flagging.
- **2026-07-09 — DECISION D5 (TBD-23 resolved): access control = owner + 3 tiers + visibility.**
  Per-instance **owner**; tiers **`own` / `speak` / `observe`**; instance **visibility**
  `public`/`unlisted`/`private` (default private); own/invite holders admit & assign tiers. D4
  discoverability = findability; tier = permitted actions. — Owner chose the recommended option; it
  formalizes the draft's own owner/observer/open-mic/invited-users vocabulary and keeps a
  non-breaking path to fine-grained capabilities. — Alt rejected: fine-grained capabilities (overkill
  v1), role-gated-only (conflates permission with dialogue role).
- **2026-07-09 — DECISION D6 (TBD-24 resolved): auth = bearer token + pluggable verifier.**
  `Authorization: Bearer <token>`; pluggable `Authenticator`; built-in simple verifier + **anonymous
  dev mode** for key-free local hello-world; production IdP pluggable. Auth (proving) separate from
  D4 identity record. — Owner chose recommended; matches references' mainstream *method*, keeps core
  dependency-light and the local demo key-free, grows into multi-scheme non-breaking. — Alt rejected:
  multi-scheme-from-v1 (unused surface), delegate-to-deployment (no batteries-included hello-world).
- **2026-07-09 — SPEC open questions expanded 20 → 27 → 29** (TBD-21…27 mapping problems A–G;
  TBD-28/29 from D3/D4 residuals). — Keeps every surfaced gap tracked before spec-writing. — Alt
  rejected: leaving decisions/gaps only in chat.
- **2026-07-09 — Phase 2 methodology distilled into `methodology/methodology.md`.** — Synthesized
  the 5 analyses across 4 axes into a 23-item DCP playbook, an anti-pattern list, and 4 decisions.
  Central finding: the 5 span the full "how to define a schema" spectrum, and the mature/trusted
  ones converge on **one machine-readable source of truth + generate the rest**; the deviants
  (ACP two mirrors, ANP no schema) demonstrably drift — this validates DCP's Pydantic-source-of-
  truth choice. Also flagged §8: the references teach *method* but give **no precedent** for DCP's
  novel dialogue-centric surface (role↔participant, orchestrator oversight, human modes) — that
  must come from `protocol_design.md` in Phase 3. — Alt rejected: jumping to SPEC without a
  written playbook.
- **2026-07-09 — New decision (methodology §7.1): DCP authors its own schema, but reuses neutral
  standards for neutral primitives** (JSON Schema for payloads, RFC 3339 for time, MIME types),
  confining novelty to the dialogue layer. — No mature host standard exists for dialogue semantics,
  so "build-on" (agents.json's path) doesn't apply; but reinventing neutral primitives is wasteful.
  — Alt rejected: authoring everything from scratch, incl. primitives.
- **2026-07-09 — New decision (methodology §7.3): one version scheme spanning spec + SDK, fixed
  before v1, with a wire protocol-version field.** — Pre-empts ACP's spec-0.2-vs-SDK-1.0 split and
  A2A's post-1.0 schema-tech swap. — Alt rejected: deferring versioning to Phase 5.
- **2026-07-09 — Remaining 4 reference analyses (A2A/ACP/ANP/agents-json) done via 4 parallel
  subagents, each from freshly-fetched primary sources.** — Independent, non-conflicting files;
  parallel fan-out was faster and each agent verified current state rather than trusting memory.
  Verified surprises now on record: **ACP has been merged into A2A** (superseded); **ANP ships
  conflicting JSON-LD vs plain-JSON agent-description forms** on site vs `main`; **`agent-json.com`
  is an unrelated project**, in-scope reference is Wildcard AI's agents.json. — Alt rejected:
  analyzing them serially myself (slower, no quality gain).
- **2026-07-09 — Cross-reference schema-strategy spectrum captured for Phase 2.** — The 5 refs
  now span the full "how to define a schema" space: author-from-scratch TS (MCP), proto3 (A2A),
  OpenAPI-authored (ACP), prose-only/no-machine-schema (ANP), build-on-OpenAPI (agents-json).
  This is the raw material for the Phase-2 methodology playbook. — Alt rejected: none.
- **2026-07-09 — Phase-1 analysis dir renamed `analysis/` → `research/`.** — Owner referred to it
  as `research/mcp.md`; standardized on `research/` and updated CLAUDE.md structure + template to
  match. — Alt rejected: keeping `analysis/` and overriding the owner's path.
- **2026-07-09 — MCP analysis written strictly from freshly-fetched primary sources** (spec site
  2025-06-18/2025-11-25, `schema.ts`, `python-sdk` README + tree), not from memory. — Verified a
  surprising finding directly: the SDK's high-level class is being renamed `FastMCP`→`MCPServer`
  in the v2.0 beta while v1.x (FastMCP) stays the stable line. — Alt rejected: reporting
  remembered `FastMCP` code without checking current `main`.
- **2026-07-09 — Bootstrap files generated (CLAUDE.md, SPEC.md, STATUS.md).** — Establishes the
  working method before any analysis or implementation. — Alt rejected: jumping straight to
  Phase 1 analysis without a written phase plan.
- **2026-07-09 — SDK test framework = pytest (owner-confirmed).** — Project brief cited Vitest as
  the rule *template*, but the SDK is Python; pytest is the equivalent. — Alt rejected: Vitest (JS
  tooling, wrong ecosystem).
- **2026-07-09 — Docs are English-first (owner-confirmed).** — Matches `protocol_design.md` and
  protocol-audience convention. — Alt rejected: Chinese-first.
- **2026-07-09 — SPEC.md built strictly from `protocol_design.md`; 20 gaps logged as TBD open
  questions rather than filled with assumptions.** — Preserves "no design from other protocols"
  and keeps the owner in control of design decisions. — Alt rejected: inventing values for
  under-specified fields.

---

## Next Actions

1. **Owner reviews the Phase-5 docs pass** — read `sdk/README.md` and `sdk/docs/{quickstart,concepts,
   guide-hosting,api-reference}.md` as a new user would; run `python docs/examples/hello_dialogue_mock.py`
   (key-free) and `pip install -e ".[dev]"` then `import dcp`. `cd sdk && ./scripts/check` reproduces
   green (174 tests, 2 live-skipped). Then **make the three deferred calls:** (a) pick a **license**
   (Apache-2.0 / MIT) → add `LICENSE` + fix pyproject; (b) approve **DB hardening** (Alembic + Postgres
   CI) as the next Phase-5 chunk; (c) decide on **PyPI publish** (name `dcp` may be taken — check/rename).
2. On approval: **Phase 5 — Docs & Release.** Quickstart (install → hello-world → next step), API
   reference + guides, packaging/PyPI + versioning/release notes, and the **DB hardening** items
   already logged (Alembic migrations replacing `create_all`; Postgres CI job). Validate the new-user
   onboarding path unaided.
3. Phase-3 closeout (non-blocking): revise `figures/` to match D1–D10 + the 5-layer model (I can spec
   what each figure should depict; SVG authoring itself is better done by you/a design tool).
4. Minor debts to clear in Phase 5: Starlette `TestClient` deprecation warning (→ `httpx2`) when
   pinning delivery deps; open-mic **tier** enforcement (observe-only) is not yet checked — only the
   `allow_open_mic` template gate is (note in §2.8). Reminder (playbook items 7, 11): M1 Pydantic
   models are the single source of truth; SPEC examples round-trip in CI.

---

## Open Questions Snapshot
**30 tracked** (TBD-1 … TBD-30). Resolved/confirmed: all except **2 deferred** — TBD-18 (field
constraints → Phase-4 M1) and TBD-30 (multi-tenant key management → post-v1). The four 〔derived〕
items (TBD-3/5/9/25) are owner-confirmed. Design sourced from `protocol_design.md` + owner decisions
D1–D8; method from Phase 1/2; never borrowed from reference protocols.
