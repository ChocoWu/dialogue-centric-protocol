# Changelog

All notable changes to the `dcp` package. This project follows [Semantic Versioning](https://semver.org):
the package version and the wire **protocol version** (`dcp.PROTOCOL_VERSION`) move together before 1.0.

## [Unreleased]

### Added — Phase 5 (docs & release)
- Front-door `README.md`, `docs/quickstart.md`, `docs/concepts.md`, `docs/guide-hosting.md`,
  `docs/api-reference.md`.
- Packaging metadata: keywords, classifiers, typed marker (`py.typed`). Editable install verified.

### Deferred
- License selection (metadata placeholder; no `LICENSE` committed yet).
- DB hardening for public release: Alembic migrations (replacing `create_all`) and a Postgres CI job.

## [0.2.0.dev0] — Phase 4 (SDK)

First end-to-end SDK against `SPEC.md` v0.2.0-draft. Ten tests-first milestones (M0–M9) plus an
oversight/control deepening (M5.1). Single CI gate: `ruff` + `mypy --strict` + `pytest`.

### Schema (source of truth)
- Pydantic v2 models for every SPEC entity; JSON Schemas generated from the models
  (`scripts/gen_schema.py`). All models reject unknown fields (`extra="forbid"`); `Message`/`Event`
  are frozen. Verification records use enums.

### State
- Append-only event log as the authoritative state (D3); `SqlStore` on SQLAlchemy 2.x (SQLite dev,
  Postgres via `dcp[postgres]`); deterministic `replay` reducer; full-replay `restore`.

### Participation
- `cast_roles` (4-step precedence); access tiers (`own ⊃ speak ⊃ observe`); `ParticipantRegistry`
  with a discoverability filter.

### Model providers
- Provider-neutral `ModelProvider` interface; `OpenAIProvider` (default), `AnthropicProvider`,
  `MockProvider`; per-binding `build_provider` factory (D8) — one dialogue may mix providers.

### Orchestration
- `Orchestrator` runs (and **resumes**) a serialized transcript; plan/flow decisions.
- **Oversight governs control (D11):** pre-action recovery (`inject_context`, `request_human`,
  `wait_gate`, `choose_alternative`, `stop`) and post-action routing (`request_revision`,
  `request_verification`, `escalate_gate`, `stop`, `continue`), both bounded. Pluggable
  `OversightPolicy` (`DefaultOversight`, `LlmOversight`, `ScriptedOversight`).
- Human intervention via `HumanGateway` (required/optional/gate + timeout → provisional); open-mic
  gated by `template.allow_open_mic`. Termination priority `error > budget > stopped > provisional > done`.

### Registry & Hosting
- `Registry`: template/participant catalogs, `instantiate`/`grant_access`/`join`/`leave`/`restore`,
  `list_instances`, `server_info` (§1.11); template immutability per `(id, version)`.
- Access control (owner + tiers + visibility, D5); bearer + anonymous auth (D6).
- Standalone `TemplateGenerator` for query → draft template auto-generation (D10).

### Delivery
- `HttpSseDelivery` / `build_app` on Starlette: REST endpoints + SSE (replay-then-tail). The semantic
  core imports no transport.

### Facade & conformance
- `Server` facade; key-free and real-model hello-worlds in `docs/examples/`.
- Conformance suite mapping every SPEC §6 acceptance criterion to a MUST vector.
