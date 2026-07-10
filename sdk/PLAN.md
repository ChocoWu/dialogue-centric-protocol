# Phase 4 — Python SDK: Execution Plan

> Fine-grained plan for building the `dcp` SDK against `SPEC.md` v0.2.0-draft. Read alongside
> CLAUDE.md §3 (SDK tech spec), the methodology playbook (`methodology/methodology.md` §5 items
> 7–16), and SPEC §3 (layers), §5 (conformance), §6 (acceptance criteria).
>
> **Owner decisions applied (2026-07-09 review): A1 LLM required · A2 real DBs · A3 HTTP/SSE ·
> A4 milestone cut confirmed · A5 review per logical group.** These shift DCP from a minimal
> library toward a **batteries-included server** — see "Positioning shift" below.

## Positioning shift (consequence of A1–A3)
The SDK now hard-depends on an **LLM provider**, a **real database**, and an **HTTP/SSE server**.
That is appropriate for a *server-hosted dialogue runtime* (D2) — unlike agents.json (a spec
parser), DCP legitimately needs these. The methodology principle we keep is **interfaces at every
I/O edge** (`ModelProvider`, `Store`, `Delivery`, `Authenticator`) so the semantic core stays
swappable and testable; the shipped implementations are just no longer stubs. **Determinism for
tests is preserved** via a `MockProvider` and SQLite `:memory:` — see "Testing strategy".

## Principles (non-negotiable, from CLAUDE.md + methodology)
- **Tests-first (pytest).** Every module gets failing tests against SPEC §6 / §4 *before* code.
- **Pydantic v2 = single source of truth.** Generate JSON Schema + SPEC §4 tables *from* models;
  never hand-edit generated artifacts; never a second authored schema.
- **Layered, names match SPEC.** `src/dcp/{schema,state,participation,provider,orchestration,registry,delivery}`
  map to SPEC layers (+ `provider` for the LLM edge).
- **Interfaces at every I/O edge.** `ModelProvider`, `Store`, `Delivery`, `Authenticator` are
  protocols; concrete impls (Anthropic, SQL, HTTP/SSE, token-auth) sit behind them.
- **Transport-agnostic, event-emitting, replayable.** Every state change emits an `Event`; an
  instance is reconstructable from its log (D3). LLM/DB/HTTP I/O only at the edges.
- **Async-first; `py.typed`; small curated facade.**

## Architecture decisions (owner-confirmed A1–A3)
- **A1 — LLM is REQUIRED; multi-provider behind `ModelProvider`; OpenAI default; both built.**
  (Owner-confirmed 2026-07-09.) A `ModelProvider` protocol wraps all model calls (orchestrator
  decisions, agent contributions, oversight judgments). **Two real impls ship together in M4:**
  - **`OpenAIProvider` — the default** (`DCP_MODEL_PROVIDER=openai`): OpenAI Python SDK
    (`AsyncOpenAI()`), key `OPENAI_API_KEY`, default model `DCP_MODEL` = **`[TBD-owner OpenAI model id]`**
    (I will not guess the current 2026 OpenAI flagship — owner to supply), structured output via the
    OpenAI SDK's Pydantic parse path. Written in its own module against the OpenAI SDK.
  - **`AnthropicProvider`** (`DCP_MODEL_PROVIDER=anthropic`): `anthropic` SDK (`AsyncAnthropic()`),
    key `ANTHROPIC_API_KEY`, default model **`claude-opus-4-8`**, adaptive thinking, structured
    output via `messages.parse()`. Written per the `claude-api` skill, in its own module.
  - **`MockProvider`** (`DCP_MODEL_PROVIDER=mock`): scripted deterministic responses for tests +
    key-free demo.
  Selection + config from **env** (`DCP_MODEL_PROVIDER`, `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`,
  `DCP_MODEL`). The two provider modules never mix SDKs. Running a real dialogue REQUIRES a key for
  the selected provider; a **local-model path is deferred** (later optional extra `dcp[local]`).
- **A2 — Real DB `Store`.** `Store` protocol backed by SQL via **SQLAlchemy 2.x** — **SQLite** for
  local/dev, **Postgres** for production (extras `dcp[postgres]`). The append-only log is the
  authoritative state (D3). Tests use SQLite `:memory:` (a real engine, hermetic + fast).
- **A3 — HTTP + SSE Delivery.** `Delivery` protocol with a real **HTTP API + SSE** binding built on
  **Starlette + uvicorn** (generic web infra, not protocol-design borrowing). SSE streams the event
  log to clients; the join/restore path (D3) replays history then tails live. An in-process delivery
  remains for unit tests.

## Testing strategy (how tests-first survives A1–A3)
- **LLM:** `MockProvider` returns scripted, deterministic responses keyed by call type
  (select-speaker, contribute, verify). No network, no key. Real `AnthropicProvider` is exercised by
  a small, opt-in, key-gated integration test (skipped in CI without `ANTHROPIC_API_KEY`).
- **DB:** SQLite `:memory:` per test; same `Store` code path as Postgres.
- **HTTP/SSE:** Starlette's `TestClient` / ASGI transport; assert event order over SSE.

---

## Milestones (ordered; each tests-first, ends green: pytest + ruff + mypy)

### M0 — Scaffolding & tooling
- `sdk/pyproject.toml` (PEP 621): pkg `dcp`, `requires-python>=3.11`; **core deps** `pydantic>=2`,
  `openai`, `anthropic`, `sqlalchemy>=2`, `starlette`, `uvicorn`, `sse-starlette` (or hand-rolled
  SSE); dev extras `pytest`,`pytest-asyncio`,`ruff`,`mypy`,`httpx`; optional extras `dcp[postgres]`,
  `dcp[local]` (stub).
- `src/dcp/__init__.py`, `py.typed`, `errors.py` (`DCPError` + `SchemaError`/`AccessError`/
  `AuthError`/`RegistryError`/`OrchestrationError`/`ProviderError`/`TerminationError`).
- Config module — env loading with these names (locked):
  `DCP_MODEL_PROVIDER` (default **`openai`**; `anthropic`|`mock`), `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `DCP_MODEL` (per-provider model override), `DCP_DATABASE_URL`
  (default `sqlite:///./dcp.db`).
- `scripts/check`: `ruff check && mypy && pytest`.
**Tests:** import smoke test. **DoD:** ruff+mypy+pytest clean.

### M1 — Schema layer (`src/dcp/schema/`) — source of truth
- **Enums:** `InstanceStatus`, `RoleKind`, `ResponseRequirement`, `AccessTier`, `Visibility`,
  `OrchestrationMode`, `OnTimeout`, `EventType`, `TerminationStatus`.
- **Value objects:** `TerminationPolicy`, `Flow`+`Edge`, `HumanPolicy`, `Budget`, `Binding`,
  `Gate`, `PendingInput`, `AccessGrant`, **`ModelBinding{provider, model}`** 〔D8〕 (no key field).
  `Participant` gains `model_binding?` (agent-only); the Orchestrator config carries one too.
- **Entities:** `Role`, `Participant`, `DialogueTemplate`, `DialogueInstance`, `Message`, `Event`.
- **Records:** `PreActionVerification`, `PostActionVerification`, `TerminationRecord`, `RolesCast`.
- **Extension points:** `metadata` maps; reject unknown top-level fields.
- **Pin TBD-18:** field constraints (id patterns, semver, ranges) per SPEC §4 — closes the deferred TBD.
- `scripts/gen_schema.py` (JSON Schema from models), `scripts/gen_spec_tables.py` (SPEC §4 tables).
**Tests (→ §6):** per-model validation; enum coverage; **round-trip every SPEC example** (item 11).
**DoD:** models complete, tests green, JSON Schema emitted, SPEC examples validate.

### M2 — State layer + real DB `Store` (`src/dcp/state/`)  〔A2〕
- `EventLog` (append-only messages[]+events[]); `emit()` on every mutation.
- `InstanceState` reducer: event → next status/turn/roster/gates/pending/budget.
- `restore(log) -> InstanceState`: **full replay** (D3/TBD-28); same path feeds late joiners.
- **`Store` protocol + `SqlStore`** (SQLAlchemy 2.x; SQLite dev / Postgres prod). Schema: instances,
  messages, events, grants. `:memory:` for tests.
**Tests (→ §6):** replay determinism; restore returns all N in order; append-only invariants;
Store round-trip on SQLite `:memory:`. **DoD:** instance round-trips log→DB→restore identically.

### M3 — Participation layer (`src/dcp/participation/`)
- `cast_roles(...)` precedence: explicit → id-match → capability → persona; emits `roles_cast`.
- Access tiers (`own⊃speak⊃observe`), `assign_tier`/`revoke`/transfer-ownership.
- `ParticipantRegistry` (persisted via `Store`); `discoverable` filter.
**Tests (→ §6):** casting precedence; `observe` MUST NOT cast into `speak`; tier implication;
discoverability filter. **DoD:** casting + access tests green.

### M4 — Model Provider layer (`src/dcp/provider/`)  〔A1 — NEW; multi-provider〕
- **`ModelProvider` protocol:** async methods for the model-backed decisions the orchestrator and
  participants need (e.g. `decide(...)`, `contribute(...)`, `verify(...)`), each with a
  Pydantic-typed structured return. Provider-neutral interface (not Anthropic- or OpenAI-shaped).
- **`OpenAIProvider` (default):** OpenAI Python SDK `AsyncOpenAI()`; default model from `DCP_MODEL`
  (owner-supplied OpenAI model id); structured output via the SDK's Pydantic parse path; env key
  `OPENAI_API_KEY`; typed-error mapping → `ProviderError`. Own module; OpenAI SDK only.
- **`AnthropicProvider`:** `AsyncAnthropic()`; default `claude-opus-4-8`; adaptive thinking
  (`thinking={"type":"adaptive"}`, `output_config={"effort":"high"}`); structured output via
  `messages.parse(output_format=<PydanticModel>)`; env key `ANTHROPIC_API_KEY`. Own module; Anthropic SDK only.
- **`MockProvider`:** deterministic scripted responses for tests + key-free demo.
- **Provider selection:** a **`build_provider(binding: ModelBinding) -> ModelProvider`** factory
  〔D8〕 — called **per binding**, not a global singleton. The **orchestrator** gets a provider from
  its instance-default binding (env `DCP_MODEL_PROVIDER`/`DCP_MODEL`); **each agent participant** gets
  a provider from its own `model_binding` (falling back to the orchestrator default). Keys resolve
  from env by provider (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`). One dialogue MAY mix providers.
- **(Deferred)** `LocalProvider` stub behind `dcp[local]`; multi-tenant key management (TBD-30).
**Tests:** `MockProvider` returns typed structured values; both real providers unit-tested with a
stubbed client; two opt-in key-gated integration tests (skipped without the respective key).
**DoD:** protocol + OpenAI + Anthropic + Mock impls green; factory selects by env; no network in the
default suite.

### M5 — Orchestration layer (`src/dcp/orchestration/`)  〔uses M4〕
- `Orchestrator` driving the control actions (select_speaker/inject_context/request_human/
  request_revision/request_verification/resolve_gate/stop) via the `ModelProvider`; each emits an Event.
- **Pre/post-action oversight** → `PreActionVerification`/`PostActionVerification` (model-backed).
- **Turn loop** (async): serialized transcript (TBD-25); async human inputs queued to
  `pending_inputs`; joins/leaves between turns.
- **Human intervention:** optional/required-human/gate/open-mic; `human_policy` timeouts.
- **Modes:** `plan` vs `flow` (flow advisory under plan).
- **Termination** each turn, priority `error>budget>stopped>provisional>done`.
- Tests inject `MockProvider` for determinism.
**Tests (→ §6):** termination priority; open-mic pending; gate/required-human timeout → provisional;
serialized-transcript invariant; scripted multi-role dialogue runs to a terminal status.
**DoD:** deterministic dialogue completes with oversight records + events emitted.

### M6 — Registry & Hosting + Access/Auth (`src/dcp/registry/`)  〔D5/D6〕
- `TemplateCatalog` (register/list/get) with **immutability per (id,version)**; `ParticipantCatalog`;
  unified `Registry` surface (TBD-29), persisted via `Store`.
- `instantiate` → `created`; `join`/`leave` (visibility+tier gated; join triggers restore); `restore`.
- **Auth (D6):** `Authenticator` protocol; `SimpleTokenAuthenticator` + **`AnonymousAuthenticator`
  (dev mode)**; bearer token → one `participant_id`.
**Tests (→ §6):** template immutability; instantiation ownership + `created`→`running`; visibility/join;
bearer resolves to one participant; anon dev mode. **DoD:** registry + auth + multi-user join(restore) green.

### M7 — Delivery: HTTP API + SSE (`src/dcp/delivery/`)  〔A3〕
- `Delivery` protocol; **`HttpSseDelivery`** on Starlette + uvicorn: REST endpoints for
  register/instantiate/join/leave/contribute; **SSE** stream of the event log (replay-then-tail for
  joiners, D3). In-process delivery kept for unit tests. Semantic core has no Starlette import.
**Tests (→ §6):** SSE subscriber receives all events in order (Starlette `TestClient`); join replays
history; core stays transport-agnostic. **DoD:** HTTP/SSE binding works (satisfies SPEC §5.3).

### M8 — Facade + canonical hello-world (`src/dcp/__init__.py`, `docs/examples/`)
- Thin registration facade (function-introspection derives participant descriptors); curated
  `__init__` (≤ ~8 names); hides the orchestration state machine.
- `docs/examples/hello_dialogue.py`: 2 agent roles + 1 human gate, **real `AnthropicProvider`**
  (needs `ANTHROPIC_API_KEY`), SQLite store, HTTP/SSE delivery — runs locally.
- `docs/examples/hello_dialogue_mock.py`: same, `MockProvider` — **key-free** smoke/demo path.
- Record concepts-to-first-success (item 18).
**Tests (→ §6):** mock hello-world runs end-to-end to a terminal status; facade smoke test.
**DoD:** `python docs/examples/hello_dialogue_mock.py` prints a completed transcript with no key.

### M9 — Conformance suite + gates
- `tests/conformance/` covering every SPEC §6 criterion; add missing (replay determinism,
  auth/identity, visibility/join).
- CI: `ruff` + `mypy --strict` + `pytest` + SPEC-example round-trip; key-gated integration test
  skipped without a key.
- Map SPEC §5 conformance items → tests.
**DoD:** full suite green; §5 conformance met for a single-node deployment.

---

## Dependency order & review groups (A5: review per group)
`M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9`. **Pause for owner review at each group boundary:**
- **Group A — Foundation:** M0–M1 (scaffold + schema/source-of-truth).
- **Group B — State & participants:** M2–M3 (DB-backed log/replay + casting/access).
- **Group C — Engine:** M4–M5 (model provider + orchestration loop).
- **Group D — Hosting & transport:** M6–M7 (registry/auth + HTTP/SSE).
- **Group E — Usable:** M8–M9 (facade/hello-world + conformance).

## Explicitly NOT Phase 4 (→ Phase 5)
Docs site & quickstart prose, **replay-viewer UI** (item 19), **preset catalog** (item 21),
**local-model provider** (`dcp[local]`), Postgres deployment hardening, PyPI release & versioning
polish. Phase 4 delivers the **library + HTTP/SSE server + DB persistence + Anthropic provider +
key-free mock hello-world + green conformance suite**.

## Locked (owner-confirmed 2026-07-09)
- **Providers:** multi-provider behind `ModelProvider`; **default `openai`**; both `OpenAIProvider`
  and `AnthropicProvider` built in M4; `MockProvider` for tests.
- **Env var names:** `DCP_MODEL_PROVIDER` (default `openai`), `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
  `DCP_MODEL`, `DCP_DATABASE_URL` (default `sqlite:///./dcp.db`).
- **Anthropic default model:** `claude-opus-4-8`.

## Locked additions (owner-confirmed 2026-07-09)
- **D8 — model binding is per-consumer:** orchestrator binding (env default) is **separate** from
  each agent participant's `model_binding` (set at registration/init; inherits orchestrator default
  if omitted). `build_provider(binding)` factory; mixed-provider dialogues supported. Credentials
  from env by provider (`TBD-30` for multi-tenant key mgmt).
- **OpenAI model id via `.env`** — owner supplies `DCP_MODEL` (+ `DCP_MODEL_PROVIDER`) at runtime;
  no hardcoded OpenAI id in the SDK.

## Still open (not blocking M0)
- **SQLite-dev / Postgres-prod** split — confirm at Group B.
