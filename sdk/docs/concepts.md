# Concepts

This is the mental model behind the SDK. The normative source is [`../SPEC.md`](../SPEC.md); this
guide is the readable companion. Section references (§) point into the spec.

## The core idea

A DCP dialogue is a **single serialized transcript** that many participants — agents *and* humans —
contribute to one turn at a time, under the control of an **orchestrator** that is *not* a
participant. The orchestrator does two jobs at once (§1.7):

- **Control** — decide who speaks next, inject context, route for revision/verification, open gates,
  and stop.
- **Oversight** — verify each turn *before* it happens (is this speaker ready?) and *after* (is the
  output good?), and act on the result.

Everything that happens is recorded as an append-only log; the dialogue's state is a deterministic
replay of that log.

## Entities

| Entity | What it is | Lifetime |
|--------|-----------|----------|
| **DialogueTemplate** (§1.2) | A reusable, registerable dialogue definition: roles, termination policy, orchestration mode, flow, human-policy defaults. Immutable per `(template_id, version)`. | Registered once, reused |
| **DialogueInstance** (§1.3) | A running occurrence created from a template. Carries all runtime state — `status`, `turn`, `roster`, `messages`, `events`, `open_gates`, `pending_inputs`, `budget`. | Per run |
| **Role** (§1.4) | A dialogue-local seat: `kind` (`agent`/`human`), persona, and `response_requirement` (`required`/`optional`/`gate`). | Defined in a template |
| **Participant** (§1.5) | A server-registered identity (agent or human) with a profile, a `discoverable` flag, and — for agents — an optional `model_binding`. | Registered on the server |
| **Orchestrator** (§1.7) | Drives + oversees one instance. Holds no state that isn't in the log, so it can attach to / resume any instance. | Per run |
| **Message** (§1.8) | A finalized contribution to the transcript. Append-only, immutable. | — |
| **Event** (§1.9) | A record that *something happened* (a control decision, a state transition, a participation signal). | — |

**Template vs Instance** is the key split (decision D1): you author and register a *template*, then
create many *instances* from it. **Role vs Participant** is the other: a role is a seat in the
script; a participant is a real registered identity **cast into** a role for one instance.

## The five layers (§3)

DCP is defined abstract-model-first, transport-last. Each layer maps to a Python subpackage:

| Layer | Responsibility | Package |
|-------|----------------|---------|
| **1. Dialogue State** (§3.1) | The authoritative, replayable event log | `dcp.state` |
| **2. Participation** (§3.2) | Registered participants, role casting, access tiers & visibility | `dcp.participation` |
| **3. Orchestration** (§3.3) | Control actions + pre/post oversight + termination | `dcp.orchestration` |
| **4. Registry & Hosting** (§3.4) | Template/participant catalogs, instantiate/join/restore, auth | `dcp.registry` |
| **5. Delivery** (§3.5) | How records reach clients (HTTP/SSE here) — pluggable, non-semantic | `dcp.delivery` |

Plus `dcp.provider` (the model edge) and `dcp.authoring` (template auto-generation). The semantic
core never imports a transport; delivery is an adapter.

## The event log is the source of truth (D3)

An instance holds **no authoritative state that isn't reconstructable from its log.** `restore()`
replays the ordered `messages + events` into a `DialogueInstance` — deriving `status`, `turn`,
`roster`, open gates, pending inputs, and budget. The same replay path serves three needs:

- the orchestrator **rehydrating** to resume a dialogue (§2.9),
- a **late joiner** catching up on the full history (§2.5),
- **audit / evaluation** after the fact.

An instance is **resumable** iff its status is non-terminal; `Orchestrator.run()` restores first and
continues without re-emitting the bootstrap events.

## Lifecycle (§2)

```
author template → register → (optional auto-generate) → instantiate → cast roles
→ join / leave → turn orchestration → contribution → human intervention → restore/replay → terminate
```

Each turn (§2.6) is serialized: at most one contribution. Asynchronous human inputs (optional
enrichment, open-mic, gate replies) queue into `pending_inputs`; joins/leaves apply between turns.

## Human participation (§2.8)

Humans are first-class. A role's `response_requirement` selects the mode:

| Mode | `response_requirement` | Waits? | Config |
|------|------------------------|--------|--------|
| Optional enrichment | `optional` | no | `on_timeout: continue` |
| Required input | `required` (human) | yes | `wait_window_seconds`, `on_timeout` |
| Approval gate | `gate` | yes | `wait_window_seconds`, `on_timeout` |
| Open mic | any `observe`-tier participant, if `template.allow_open_mic` | — | pending until addressed |

A waited human that times out resolves per `on_timeout` (default `finalize_provisional`), so an
unresponsive human never hangs the instance.

## The orchestrator's oversight loop (§1.7, D11)

This is what makes a dialogue *controlled* rather than a free-for-all. Verification records are not
audit decoration — the orchestrator **acts on them**:

**Pre-action (speaker readiness).** Before a candidate speaks, a `PreActionVerification` scores
`readiness`, `availability`, `capability_match`, `role_state`, `context_sufficiency`,
`execution_feasibility` and yields a `recommended_action`. If it isn't `select_speaker`, the
orchestrator performs the recovery (bounded by `max_recovery_attempts`):

- `inject_context` → add the missing context, retry the candidate
- `request_human` → solicit a human, inject the reply as context, retry
- `wait_gate` → block on the open gate(s) until resolved, retry
- `choose_alternative` → re-select a different candidate
- `stop` → terminate `provisional`

**Post-action (output verification).** After a contribution, a `PostActionVerification` gives a
`verdict` (`pass`/`revise`/`escalate`/`reject`), quality dimensions (`relevance`, `role_consistency`,
`completeness`, `grounding`, `safety`), and an `outcome` the orchestrator routes on:

- `continue` → next turn
- `request_revision` → same role revises as a new turn (bounded by `max_revisions`)
- `request_verification` → route a turn to a verifier role
- `escalate_gate` → open a human approval gate
- `stop` → terminate `done`

Oversight is pluggable (`OversightPolicy`): `DefaultOversight` passes everything (the key-free happy
path), `LlmOversight` asks the orchestrator's model for the records, and `ScriptedOversight` drives
specific branches in tests.

## Orchestration modes (§2.6)

- **`plan`** — the orchestrator selects the next speaker freely (emergent). In the SDK it asks its
  provider for a structured `OrchestratorAction`.
- **`flow`** — the orchestrator follows the template's declared `flow` graph (`entry` + `edges`),
  deterministic.

## Termination (§2.10)

Checked every turn in strict priority order:

```
error > budget > stopped > provisional > done
```

`done` requires the termination condition satisfied **and** no open gate. Every terminal status
carries a reason and is emitted as `instance_terminated`.

## Access & identity (§1.6, D5/D6)

Each instance has one **owner** and per-participant **tiers**: `own` ⊃ `speak` ⊃ `observe`.
**Visibility** is `public` / `unlisted` / `private` (default private). **Auth** resolves a bearer
token to one `participant_id` via a pluggable `Authenticator`; an anonymous dev mode keeps the local
hello-world key-free. Auth answers *who you are*; tiers answer *what you may do*. See
[guide-hosting.md](guide-hosting.md).

## Extension (§1.10)

Extension is explicit and typed — never tolerate-unknown. Every entity has an open `metadata` map;
new protocol surface ships under a MINOR version bump. Unknown top-level fields are rejected
(`extra="forbid"` on every model); unknown `metadata` keys are preserved.
