# DCP — Dialogue-centric Protocol Specification

**Status:** Working draft (Phase 3) · **Spec version:** 0.2.0-draft · **Wire protocol version:** `0.2.0`

**Source of design:** `protocol_design.md` **plus the owner decisions D1–D6 in §0.1.** Both are
DCP-internal. No design element from any other protocol (MCP / A2A / ACP / ANP / agents.json)
appears here; those informed *method only* (see `methodology/methodology.md`).

### Normative Content
The **Pydantic v2 models in `src/dcp/schema/` are the authoritative definition** of every entity,
once they exist (Phase 4). Until then, the **§4 field tables in this document are the working
normative contract**, and the Phase-4 models MUST be generated to match them; thereafter the field
tables and any JSON Schema are **generated and informative**, and the models win on any conflict.
JSON examples in this document are **informative**.

### Requirement Language
The key words **MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT, RECOMMENDED, MAY,
OPTIONAL** are to be interpreted as in RFC 2119 / RFC 8174, and only when in all capitals.

### Versioning
DCP uses **Semantic Versioning `MAJOR.MINOR.PATCH`** for the spec and the SDK under **one shared
scheme**. Every instance and every wire envelope carries a **`dcp_version`** string (the protocol
version it conforms to). MAJOR increments are breaking; MINOR adds backward-compatible surface;
PATCH is editorial/clarifying. Extension without a version bump is only via the declared extension
points (§1.10).

### This draft's resolutions
This draft **resolves TBD-1 … TBD-29** except where §7 marks an item **DEFERRED**. Resolutions
that are *derived* (a principled extrapolation from the draft + D1–D6, not stated verbatim in
`protocol_design.md`) are tagged **〔derived〕** so the owner can veto them; everything else is
taken directly from the draft or D1–D6.

---

## 0. Scope & Classification

DCP is a **dialogue-centric**, **server-hosted** protocol for human-agent multi-agent systems.

- **Counterparty:** hybrid — human-agent / agent-agent / orchestrator-agent.
- **Payload:** hybrid — message + control action + state/event + human signal + artifact/context.
- **Interaction state:** stateful (a running instance has authoritative, replayable state).
- **Discovery:** centralized / platform-mediated (a DCP **server** hosts a registry — §3.4).
- **Schema flexibility:** multiple predefined schemas plus declared extension points (§1.10).

---

## 0.1 Foundational Decisions (owner-set — 2026-07-09 review)

Firm DCP design decisions. Not borrowed from any reference protocol.

- **D1 — Template and Instance are two first-class entities.** A **DialogueTemplate** is the
  reusable, registerable *definition*; a **DialogueInstance** is a running occurrence *created
  from* a template, carrying live state. Lifecycle: *author or auto-generate a template → register
  it → instantiate → run → (others may join)*.
- **D2 — DCP is a server-hosted model.** A DCP **server** hosts dialogues: templates are
  **registered**, instances are **addressable and joinable** by other users. **register / discover
  / instantiate / join / leave** are *semantic* operations, defined independently of transport
  (not the Delivery layer).
- **D3 — Restore.** An instance persists its full history (messages + events). The **orchestrator
  can restore/rehydrate its monitoring state from that log at any time**; all authoritative
  oversight state MUST be reconstructable from the log. Restore is **full replay** of the log, and
  the **same path serves late-joining participants/observers**.
- **D4 — Humans are registered participants, like agents.** Real users, like agents, are
  **registered to the server** with **auth**, a **profile/description**, and a **discoverability**
  flag — a server-level persistent identity, distinct from the dialogue-local Role they are *cast*
  into.
- **D5 — Access control: owner + three tiers + visibility.** Each instance has an **owner**.
  A participant holds one tier per instance: **`own`** / **`speak`** / **`observe`**. Instance
  **visibility**: `public` / `unlisted` / `private` (default `private`). `own`/invite holders admit
  participants and assign tiers. D4 discoverability = *findability*; tier = *permitted actions*.
- **D6 — Auth: bearer token + pluggable verifier.** A registered participant authenticates with a
  **bearer token**; verification is behind a pluggable **`Authenticator`** (built-in simple
  verifier + **anonymous dev mode** for local hello-world; production IdP pluggable). Auth is
  *proving* identity, separate from the D4 identity record.

---

## 1. Entity Model

### 1.1 Overview
DCP defines these entities. **Server-level** entities are persistent and registered;
**instance-level** entities live within one running dialogue; the **Orchestrator** is a control
entity, not a participant.

```
Server-level:   Participant (registered)   DialogueTemplate (registered)
Instance-level: DialogueInstance ── Role ── (cast to) ── Participant
                     │  Message   Event   AccessGrant   HumanInterventionPolicy
                     └─ monitored by → Orchestrator (control + oversight)
```

Overview figure: `figures/protocol_entity_overview.svg` *(predates D1–D6; to be revised)*.

### 1.2 DialogueTemplate  〔D1〕
The reusable, registerable **definition** of a dialogue. Immutable once registered under a given
`(template_id, version)`; a change is a new version (§2.1). Fields (§4.1): `template_id`,
`version`, `title`, `topic`, `goal`, `termination_policy`, `roles[]`, `flow`, `orchestration`,
`human_policy_defaults`, `default_visibility`, `metadata`.

### 1.3 DialogueInstance  〔D1〕
A running occurrence created from a template, carrying **all runtime state**. Fields (§4.2):
`instance_id`, `template_ref` (`template_id` + `version`), `owner` (participant id), `visibility`,
`dcp_version`, `status`, `turn`, `roster[]` (cast + joined participants with tiers), `messages[]`,
`events[]`, `open_gates[]`, `pending_inputs[]`, `budget` (consumed vs. limits), `metadata`.

- **`status`** 〔derived from draft + D2/D5〕 is a first-class enum:
  `created` → `running` → `awaiting` (blocked on a gate or required human input) ⇄ `running`,
  and the terminal states of §2.10 (`done`, `provisional`, `stopped`, `budget`, `error`).
  `created` = instantiated, not yet started; `awaiting` = at least one open gate / pending
  required input. *(Resolves TBD-3.)*

### 1.4 Role
A **dialogue-local identity** defined by a template and filled at runtime by casting (§2.4).
Fields (§4.3): `role_id`, `name`, `kind`, `persona`, `response_requirement`, `binding`, `human_policy`.

- **`kind`** ∈ `{agent, human}`. Tool-backed agents are an `agent` whose `binding` names a
  tool-backed participant; observers are **not** a role kind — they are the `observe` access tier
  (D5). *(Resolves TBD-4.)*
- **`response_requirement`** ∈ `{required, optional, gate}` (renamed from draft `response_mode`) —
  the orchestrator's per-role **wait / mandate policy**:
  - `required` — when selected, the participant MUST contribute; the orchestrator **waits**. For a
    **human** `required` role the orchestrator waits within the role's `human_policy` window and
    applies `on_timeout` (§2.8) — a required human MUST have a timeout so it cannot hang the
    instance.
  - `optional` — MAY contribute; the orchestrator does **not** wait (Optional Enrichment, §2.8).
  - `gate` — a human **approval gate**: `required` **plus** approval-decision semantics (the
    contribution is an approve/reject/revise `decision`); the orchestrator waits within the role's
    `human_policy` window. **Modeling note:** `gate` fuses two axes (wait-policy + decision
    semantics) into one value for authoring simplicity; if combinations are later needed (e.g. a
    required agent that also gates), split `gate` into a separate `approval_gate` flag — a
    **non-breaking** MINOR change. *(Resolves TBD-5 + TBD-15.)*
- **`binding`** names the intended participant: `{participant_id}` (explicit/reserved binding) or
  is empty (cast by capability/persona, §2.4).

### 1.5 Participant (registered)  〔D4〕
A **server-level persistent identity**, human or agent, registered to the server. Fields (§4.4):
`participant_id`, `kind` (`agent | human`), `display_name`, `profile` (self-description /
capabilities / persona; **distinct** from a dialogue-local Role), `auth` (credential reference,
§1.6), `discoverable` (bool), `model_binding?` (agent-kind only, §4.5b), `metadata`.

- `[DECIDED D8]` An **`agent`-kind** participant MAY declare a **`model_binding`** `{provider, model}`
  set **at registration / agent initialization**. It is the model that produces *this agent's*
  contributions, and is **independent** of the orchestrator's binding (§1.7) — so different agents in
  one dialogue MAY run on different providers/models. If omitted, the agent inherits the
  orchestrator's default binding. `human`-kind participants have no `model_binding`. Credentials
  resolve by provider from the environment. `[TBD-30]`
- A Participant is **cast into** a Role in an instance (§2.4); the same participant MAY fill
  different roles across instances. `discoverable` governs whether others can find it to invite
  it. *(Resolves TBD-6; the registry that holds Participants is §3.4 / TBD-29.)*

### 1.6 Access & Identity  〔D5, D6〕
- **Owner:** the participant that instantiated the dialogue (D5). Exactly one per instance; MAY
  transfer ownership (an `own`-tier action).
- **Access tiers** (per instance, per participant): `own` ⊃ `speak` ⊃ `observe`.
  - `own` — manage access & visibility, invite, assign/revoke tiers, terminate, rebind roles,
    transfer ownership. Implies `speak`.
  - `speak` — MAY be cast into a role and contribute Messages. Implies `observe`.
  - `observe` — read-only transcript access; MAY open-mic only if the template enables it (§2.8).
- **AccessGrant** (§4.5): `{instance_id, participant_id, tier, granted_by, granted_at}`.
- **Visibility:** `public` (listed + open-join as `observe`), `unlisted` (join by id/link, not
  listed), `private` (invite-only). Default `private`.
- **Auth (D6):** requests carry a **bearer token**; the server resolves it to a `participant_id`
  via a pluggable **`Authenticator`**. A built-in verifier and an **anonymous dev mode** (token
  optional; a single synthetic local participant) MUST be provided for local development. Auth is
  orthogonal to tiers: auth answers *who you are*, tiers answer *what you may do*.
  *(Resolves TBD-23, TBD-24.)*

### 1.7 Orchestrator
Responsible for **dialogue control** and **dialogue oversight**; **not a participant** and
contributes no content. Oversight applies before and after each participant action.
Figure: `figures/orchestrator_oversight_loop.svg`.

- **Restorable (D3):** the orchestrator holds **no authoritative state not reconstructable from
  the log**; it MAY attach to a running or resumed instance and rehydrate by full replay (§2.9).
- `[DECIDED D8]` The orchestrator carries its own **`model_binding`** `{provider, model}` (§4.5b)
  for control + oversight decisions — an **instance/server-level default** from env
  (`DCP_MODEL_PROVIDER`/`DCP_MODEL`). This is **separate** from each agent participant's binding
  (§1.5): the orchestrator's model runs the control loop; each agent's model runs that agent's
  contributions, so one dialogue MAY mix providers/models. Credentials are resolved by provider
  from the environment, never stored in the binding. `[TBD-30]`

| Action | Payload | Meaning |
|--------|---------|---------|
| `select_speaker` | `{target_role_id, reason, pre_action_verification}` | Advance the turn to a role. |
| `inject_context` | `{target_role_id?, content, reason}` | Add missing context before/without a turn. |
| `request_human` | `{target_role_id, prompt, policy}` | Solicit human input (optional or gate). |
| `request_revision` | `{message_id, reason, issues[]}` | Send a contribution back for revision. |
| `request_verification` | `{message_id, verifier_role_id?, reason}` | Route a contribution to a verifier. |
| `resolve_gate` | `{gate_id, decision}` | Close an open human gate. |
| `suspend` | `{reason}` | Pause **without** terminating — leaves the instance non-terminal for later resume (§2.9). |
| `stop` | `{status, reason}` | Terminate the instance (§2.10). |

**Pre-action Oversight (speaker-readiness verification).** Before `select_speaker`, verify the
candidate. Structured record (§4.7 `PreActionVerification`), all categorical fields are **enums**:
`readiness` (`ready|not_ready|uncertain`), `availability` (`available|unavailable|waiting|timeout`),
`capability_match` (`high|medium|low`), `role_state` (`needed|already_satisfied|overused|blocked`),
`context_sufficiency` (`sufficient|insufficient`), `execution_feasibility`
(`feasible|infeasible|uncertain`), `issues[]`, `recommended_action`
(`select_speaker|inject_context|choose_alternative|request_human|wait_gate|stop`), and `recovered`
(bool — set true when the orchestrator actually performed a recovery action off this record).
Sub-steps: candidate generation → availability → capability → role-state → context sufficiency →
execution feasibility.

**Post-action Oversight (output verification).** After a contribution, verify it. Structured
record (§4.8 `PostActionVerification` — resolves TBD-8), enums: `verdict`
(`pass|revise|escalate|reject` — the overall judgment), the quality dimensions `relevance`,
`role_consistency`, `completeness`, `grounding`, `safety` (each `ok|weak|fail`),
`human_input_addressed` (bool), `issues[]`, `outcome`
(`continue|request_revision|request_verification|escalate_gate|stop` — the routed control action),
and `escalated` (bool — set true when the outcome escalated to a human gate).

**Oversight governs control 〔D11〕.** The verification records are not merely audit — the
orchestrator MUST act on them:
- **Pre → recovery.** If `recommended_action != select_speaker` (or `readiness != ready`), the
  orchestrator MUST perform the recommended recovery instead of proceeding to the contribution:
  `inject_context` (add missing context, emit `context_injected`, retry the candidate);
  `request_human` (solicit a cast human via the gateway, emit `human_input_pending` →
  `human_input_addressed`, inject the reply as context, retry — or leave the request pending on
  timeout); `wait_gate` (block on the instance's open gate(s) until they resolve — emit
  `gate_resolved` — then retry); `choose_alternative` (re-select a different candidate); or `stop`
  (terminate `provisional`). Recovery is **bounded** (`max_recovery_attempts`, default 3) per turn;
  exhausting it terminates the instance `provisional`.
- **Post → routing.** The orchestrator MUST route on `outcome`: `continue`; `request_revision`
  (send the message back to the same role, bounded by `max_revisions`, default 2, then escalate or
  continue); `request_verification` (route to a verifier role); `escalate_gate` (open a human
  gate); `stop` (terminate). Each control action emits its Event (`context_injected`,
  `revision_requested`, `verification_requested`, `gate_opened`/`gate_resolved`).

Reference control loop (informative):
```
assess needs → generate candidates → verify readiness (pre)
→ if ready: select_speaker → (contribution) → verify output (post) → route on outcome
→ else: perform recommended recovery (bounded) ; check_termination each turn
```

### 1.8 Message
A **finalized semantic contribution** to the transcript. Fields (§4.9): `message_id`,
`instance_id`, `turn_id`, `role_id`, `participant_id`, `speaker_kind`, `content`, `created_at`,
`metadata`. A Message is append-only and immutable once recorded.

### 1.9 Event
A protocol-level record that **something happened** (state transitions, control decisions,
participation signals, delivery updates). Fields (§4.10): `event_id`, `instance_id`, `type`,
`payload`, `created_at`. Uses: audit, replay, restore (D3), recovery, evaluation, delivery sync.

- **Message vs Event:** a Message is a finalized contribution; an Event is a process record.
  The persisted `messages[] + events[]` are the authoritative, replayable log (D3).
- **`type` taxonomy** 〔derived — extensible via §1.10; resolves TBD-9〕, grouped:
  - *Registry:* `template_registered`, `participant_registered`, `template_deprecated`.
  - *Instance lifecycle:* `instance_created`, `instance_started`, `turn_assigned`,
    `contribution_recorded`, `instance_suspended`, `instance_terminated`.
  - *Participation:* `roles_cast`, `participant_joined`, `participant_left`, `tier_changed`,
    `human_input_pending`, `human_input_addressed`, `gate_opened`, `gate_resolved`.
  - *Oversight:* `pre_action_verified`, `post_action_verified`, `revision_requested`,
    `verification_requested`, `context_injected`.

### 1.10 Extension Points  〔methodology; resolves TBD-1〕
Extension is **explicit and typed**, never implicit tolerate-unknown. Two mechanisms:
1. A reserved open **`metadata: object`** map on Template, Instance, Participant, Message, Event.
2. Named, versioned **capabilities** advertised by a server/template (e.g. auto-generation,
   verifier roles). Unknown top-level fields MUST be rejected; unknown `metadata` keys MUST be
   preserved. New protocol surface ships under a MINOR version bump.

### 1.11 ServerInfo & Capabilities  〔D9 — concretizes §1.10 capability advertisement〕
A DCP server advertises what it can do through a **ServerInfo** descriptor (§4.12), so a client can
discover, before acting, the protocol version, enabled capabilities, and available model providers.
Fields: `dcp_version`, `capabilities` (`{auto_generate, verifier_routing, …}` — a typed, extensible
map of the §1.10 named capabilities), and `model_providers[]` — each `{provider, configured}` where
`configured` is `true` iff the server holds a credential for that provider. **Credentials MUST NOT
appear in ServerInfo** — only the boolean. This is DCP-native (derived from §1.10), not a
handshake borrowed from any reference protocol. *(Resolves the "what providers/agents/instances
exist" discovery gap.)*

---

## 2. Lifecycle

Stages: **Template Authoring/Registration → (optional) Auto-generation → Instantiation → Role
Casting → Joining/Leaving → Turn Orchestration → Participant Contribution → Human Intervention →
Restore/Replay → Termination.** Overview figure: `figures/dialogue_lifecycle_overview.svg`
*(predates D1–D6)*.

### 2.1 Template Authoring & Registration  〔D1, D2〕
A DialogueTemplate is authored (by hand or auto-generated, §2.2) and **registered** to the server
via `register_template`. Registration assigns/pins `(template_id, version)`; a registered
`(template_id, version)` is **immutable** — re-registering the same id with changes MUST use a new
`version`. Emits `template_registered`. *(Resolves TBD-21 registration half, TBD-22.)*

### 2.2 Template Auto-generation (optional server capability)  〔point 4; resolves TBD-10〕
Auto-generation is an **OPTIONAL** server capability, advertised per §1.10/§1.11 (`auto_generate`).
Its **contract** is normative even though its algorithm is out of scope: **input** =
`{query, constraints?}`; **output** = a **valid DialogueTemplate** (§4.1) the user MAY then edit and
register. A server without this capability MUST reject an auto-generate request with a capability
error. This gives both paths of the usability goal: *auto-create then edit*, or *author directly*.

- `[DECIDED D10]` Auto-generation is a **standalone generator**, **not** an Orchestrator action.
  The Orchestrator (§1.7) controls and oversees a *running instance* and holds no state outside an
  instance log (D3); template authoring is an upstream, instance-less step. The generator MAY reuse
  the same model layer (a `ModelProvider`, §4.5b) but is a separate component. Output is a **draft
  template** (unregistered); registration (§2.1) and instantiation (§2.3) remain explicit, so
  *query → draft → (edit) → register → instantiate → run* is the pipeline. A convenience one-shot
  MAY chain these, but the reviewable draft is the default.

### 2.3 Instantiation  〔D1, D2〕
`instantiate(template_ref, {owner, visibility?, overrides?})` creates a **DialogueInstance** in
status `created`, sets the caller as **owner** (D5), applies `visibility` (default from template,
else `private`), and emits `instance_created`. `instance_started` transitions to `running` on the
first orchestration action.

### 2.4 Role Casting
Binds each template Role to a registered Participant. Precedence (from draft):
```
explicit binding (reserved) → role_id matches a registered participant id
→ capability overlap → persona-based fallback
```
Casting MUST be recorded (`roles_cast`, §4.6) for auditability. A participant cast into a
`speak`-capable role MUST hold ≥ `speak` tier (D5). *(Resolves TBD-17 "reserved bindings" =
explicit binding.)*

### 2.5 Joining & Leaving (multi-user)  〔D2, D5; resolves TBD-17 "cross-user spawn"〕
Other participants may `join` an instance subject to visibility + tier (D5): `public` → auto
`observe`; `unlisted`/`private` → requires an invite/grant from an `own`/`invite` holder. `join`
emits `participant_joined` and triggers a **restore/replay** so the joiner receives the full log
to date (D3). `leave` emits `participant_left`. Joins/leaves take effect **between turns** (§2.6);
they never mutate a turn in flight.

### 2.6 Turn Orchestration
Each turn the orchestrator emits one control action (§1.7), preceded by pre-action oversight and
(after a contribution) followed by post-action oversight, then a termination check (§2.10).

- **Concurrency model** 〔derived; resolves TBD-25〕. The **transcript is a single serialized
  sequence** even with many participants: the orchestrator is the serialization point and admits
  at most one contribution per turn. Asynchronous human inputs (optional enrichment, open-mic,
  gate responses) are **queued into `pending_inputs[]`** and surfaced to the orchestrator, which
  decides when to admit/address them. Participant joins/leaves and tier changes are applied
  between turns. This keeps a coherent, replayable transcript under multi-user async participation.

- **`orchestration.mode`** 〔resolves TBD-12〕 ∈ `{plan, flow}`:
  - `plan` — the orchestrator selects the next speaker freely (emergent).
  - `flow` — the orchestrator's succession is **guided** by the template's declared `flow` graph.

- **`flow`** 〔resolves TBD-11, TBD-26〕 is the **initial/default succession**, and MAY be
  **non-linear** (branches, loops). `flow = {entry, edges[]}`; an
  `edge = {from_role, to_role, condition?}` declares an allowed transition. Its strength depends on
  mode:
  - Under **`mode:plan`** it is **advisory** — a hint the orchestrator MAY follow or deviate from.
  - Under **`mode:flow`** it is **guiding** — succession is **constrained** to the outgoing edges of
    the last speaker: exactly one edge ⇒ deterministic; several ⇒ the orchestrator chooses among
    **only those allowed roles** (`condition` is free-text guidance, not machine-evaluated); none ⇒
    the flow ends.
  - In **either** mode the **oversight loop may adapt** the realized path — e.g. pre-action
    verification finding a candidate unavailable triggers recovery that switches to an alternative
    (§1.7). So `flow` seeds the structure; it is not a rigid script.

### 2.7 Participant Contribution
The selected participant contributes; the finalized contribution becomes a **Message** and the act
of recording it is an **Event** (`contribution_recorded`). Agent metadata MAY include `{model,…}`;
human metadata MAY include `{mode, decision}`.

### 2.8 Human Intervention
Three modes (figure: `figures/human_intervention_three_modes.svg`), reconciled with `response_requirement`
(§1.4) and `human_policy`:

| Mode | Waits? | Bound to | Config |
|------|--------|----------|--------|
| **Optional Enrichment** | No | role `response_requirement:optional` | `{on_timeout: continue}` |
| **Required Input** | Yes | role `response_requirement:required` + human | `{wait_window_seconds, on_timeout}` |
| **Approval Gate** | Yes | role `response_requirement:gate` | `{wait_window_seconds, on_timeout}` |
| **Open Mic** | — | `observe`-tier participant (D5), if `template.allow_open_mic` | `{addressed: false}` until addressed |

- **`human_policy`** 〔resolves TBD-13〕 lives at **role level**; a template MAY set
  `human_policy_defaults` inherited by roles that omit it. It applies to **any human role the
  orchestrator waits on** — both `required` and `gate` (correctness fix: without a timeout on a
  `required` human, an unresponsive human would hang the instance forever). `optional` humans are
  not waited on and need no window.
- **`on_timeout`** 〔resolves TBD-14〕 ∈ `{continue, finalize_provisional}` (optional →
  `continue`; a waited `required`/`gate` human that times out → per policy, default
  `finalize_provisional`, yielding a `provisional` termination if it blocks the goal — §2.10).
- Open-mic input MUST be marked `pending` (in `pending_inputs[]`) until a participant addresses it;
  resolution emits `human_input_addressed {input_id, addressed_by}`. Open-mic MUST be **rejected**
  unless `template.allow_open_mic` is set (default `false`); it is the template's opt-in to
  unsolicited observer interjections (§6).

### 2.9 Restore & Replay  〔D3; resolves TBD-28〕
`restore(instance_id)` returns the **full replayed log** (`messages[] + events[]` in order), from
which the orchestrator rehydrates oversight state and a joiner catches up — **one mechanism for
both**. Restore is full replay, **not** snapshot+delta. An implementation MAY cache a snapshot as
an optimization but the log remains authoritative.

- **Resume** (D3, MUST) = `restore` **then continue** to a terminal status. An orchestrator
  attaching to a non-terminal instance MUST rehydrate `turn`, transcript, roster, and last speaker
  from the log and **MUST NOT** re-emit the instance's bootstrap events (`instance_created`,
  `instance_started`, initial `roles_cast`/`participant_joined`) — those already exist in the log.
  An instance is **resumable** iff its `status` is non-terminal (`created`/`running`/`awaiting`);
  terminal instances (`done`/`provisional`/`stopped`/`budget`/`error`) are read-only via `restore`.
- **Suspend** (§1.7 `suspend`) is how a run pauses on purpose: the orchestrator stops appending and
  emits `instance_suspended` **without** a terminal event, leaving the instance non-terminal. A later
  `run()` (this or another orchestrator) resumes it by the rule above. This makes long-running,
  cross-session dialogues (e.g. awaiting a human who returns tomorrow) first-class.

### 2.10 Termination
Terminal statuses, each with a `reason` (§4.11 `TerminationRecord`):

| Status | Meaning |
|--------|---------|
| `done` | `termination_policy.condition` satisfied and no gate open |
| `provisional` | provisional result (e.g. a human gate timed out) |
| `stopped` | turn cap (`max_turns`) reached |
| `budget` | token/compute budget reached |
| `error` | runtime error (e.g. a participant could not be invoked) |

- **Evaluation** 〔resolves TBD-16〕: the orchestrator runs a termination check **each turn, after
  post-action oversight**, in **priority order**: `error` > `budget` > `stopped` > `provisional` >
  `done`. `done` requires the orchestrator to judge `termination_policy.condition` satisfied **and**
  `open_gates == []`. Emits `instance_terminated`.

---

## 3. Protocol Layers

**Five layers** 〔D2/D4/D5 add a Registry & Hosting layer — resolves TBD-27〕, ordered
abstract-model-first, transport-last (methodology). Figure `figures/four_layer_protocol_stack.svg`
*(shows the pre-D2 four-layer model; to be revised to five)*.

### 3.1 Dialogue State Layer
The authoritative state of a running instance: `instance_id`, `template_ref`, `goal`, `topic`,
`termination_policy`, `status`, `turn`, `messages[]`, `events[]`, `open_gates[]`,
`pending_inputs[]`, `budget`. Defines *what a dialogue is and where it stands*; fully replayable
(D3).

### 3.2 Participation Layer
Who participates and how: registered participants (D4), role casting, access tiers & visibility
(D5), required/optional/supervisory/spontaneous humans, approval gates, open mic, observers. The
primary differentiator from agent-to-agent protocols: participants are not assumed to be
autonomous agents.

### 3.3 Orchestration Layer
How a dialogue evolves: the control actions of §1.7, pre/post-action oversight, context injection,
gate resolution, open-mic addressing, termination checking. Makes the dialogue **controllable**
rather than purely emergent.

### 3.4 Registry & Hosting Layer  〔NEW — D2/D4/D5〕
The server-level surface that hosts dialogues:
- **Registries** 〔resolves TBD-29〕: **one Registry surface with two catalogs** — a
  **TemplateCatalog** and a **ParticipantCatalog**. Operations: `register_template`,
  `list_templates`, `get_template`, `register_participant`, `list_participants`, `get_participant`,
  `instantiate`, `list_instances`, `get_instance`, `join`, `leave`, `restore`, `resume` (§2.9),
  `server_info` (§1.11), and `generate_template` (§2.2, if `auto_generate`). Discovery MAY span both
  catalogs but exposes only `discoverable` participants and non-`private` templates/instances;
  `list_instances` likewise returns only instances the caller owns/has a grant on or that are
  non-`private`.
- **Access & auth** (D5/D6): admission, tier assignment, visibility, bearer-token authentication
  via the pluggable `Authenticator`.
- These are **semantic** operations, **independent of transport** (they are not §3.5).

### 3.5 Delivery Layer
How records reach clients: HTTP API, SSE, WebSocket, polling, batch replay, frontend rendering,
token-level streaming. **Implementation-specific — the semantic protocol MUST NOT depend on any
particular delivery mechanism.** (SSE token streaming is a valid choice, not a requirement.)

---

## 4. Data Schemas (normative field tables)

Interim normative contract per §Normative-Content; Phase 4 authors these as Pydantic v2 models and
regenerates these tables. Types are indicative; `?` = optional. `[TBD-18]` remains only for the
exhaustive per-field constraints (patterns, ranges) to be pinned during Pydantic authoring.

### 4.1 DialogueTemplate
| field | type | req | notes |
|-------|------|-----|-------|
| `template_id` | string | ✓ | stable id |
| `version` | semver string | ✓ | immutable per id |
| `title` `topic` `goal` | string | ✓ | |
| `termination_policy` | object | ✓ | `{condition, max_turns?, token_budget?}` |
| `roles` | Role[] | ✓ | §4.3 |
| `flow` | object? | | `{entry, edges[]}` (§2.6) |
| `orchestration` | object | ✓ | `{mode: plan\|flow}` |
| `human_policy_defaults` | object? | | inherited by roles (§2.8) |
| `default_visibility` | enum? | | `public\|unlisted\|private` |
| `metadata` | object? | | extension point |

### 4.2 DialogueInstance
| field | type | req | notes |
|-------|------|-----|-------|
| `instance_id` | string | ✓ | |
| `template_ref` | object | ✓ | `{template_id, version}` |
| `owner` | participant_id | ✓ | D5 |
| `visibility` | enum | ✓ | default `private` |
| `dcp_version` | semver string | ✓ | conformance version |
| `status` | enum | ✓ | §1.3 |
| `turn` | int | ✓ | |
| `roster` | AccessGrant[]+cast | ✓ | participants & tiers & roles |
| `messages` | Message[] | ✓ | append-only |
| `events` | Event[] | ✓ | append-only |
| `open_gates` | Gate[] | ✓ | |
| `pending_inputs` | Input[] | ✓ | async human inputs (§2.6) |
| `budget` | object | ✓ | `{turns_used, tokens_used, limits}` |
| `metadata` | object? | | |

### 4.3 Role · 4.4 Participant · 4.5 AccessGrant · 4.5b ModelBinding
- **Role:** `role_id, name, kind(agent|human), persona, response_requirement(required|optional|gate), binding{participant_id?}, human_policy?`.
- **Participant:** `participant_id, kind(agent|human), display_name, profile, auth(ref), discoverable(bool), model_binding?(agent-only), metadata?`.
- **AccessGrant:** `instance_id, participant_id, tier(own|speak|observe), granted_by, granted_at`.
- **ModelBinding** 〔D8〕**:** `{provider: "openai"|"anthropic"|"mock"|…, model: string}`. No
  credential field — the API key is resolved from the environment by `provider`. Attached to the
  Orchestrator (§1.7, instance default) and, optionally, to each agent Participant (§1.5).

### 4.6–4.11 Records
- **`roles_cast`:** `{instance_id, roles:[{role_id, participant_id}]}`.
- **`PreActionVerification`:** `{readiness, availability, capability_match, role_state, context_sufficiency, execution_feasibility, issues[], recommended_action, recovered}` (§1.7; all categorical fields enums, `recovered` bool).
- **`PostActionVerification`:** `{verdict, relevance, role_consistency, completeness, grounding, safety, human_input_addressed, issues[], outcome, escalated}` (§1.7; `verdict`/quality dims/`outcome` enums, `escalated` bool).
- **Message:** `{message_id, instance_id, turn_id, role_id, participant_id, speaker_kind, content, created_at, metadata?}`.
- **Event:** `{event_id, instance_id, type, payload, created_at}`.
- **TerminationRecord:** `{status(done|provisional|stopped|budget|error), reason}`.

---

## 5. Conformance  〔resolves TBD-19〕

An implementation claims DCP conformance at version `X.Y.Z` if it:
1. Implements the **Dialogue State, Participation, and Orchestration layers** (§3.1–3.3) — **MUST**.
2. Implements the **Registry & Hosting layer** (§3.4) for any **multi-user** deployment — **MUST**;
   a single-user/local deployment MAY omit remote registry/discovery but MUST still expose
   `instantiate` and `restore`.
3. Provides **at least one Delivery binding** (§3.5) — **MUST** — but no specific binding is
   required.
4. Emits the **append-only `messages[] + events[]` log** and supports **full-replay `restore`**
   (D3) — **MUST**.
5. Enforces **access tiers and bearer auth** (D5/D6), providing the **anonymous dev mode** — **MUST**.
6. Auto-generation (§2.2) and verifier routing are **OPTIONAL** capabilities, advertised per §1.10.
Conformance test vectors are the §6 acceptance criteria.

---

## 6. Acceptance Criteria (feed the Phase-4 pytest suite)  〔resolves TBD-20〕

Representative, testable criteria (each becomes ≥1 pytest). Not exhaustive; grows with §4.

- **Template immutability:** re-registering `(template_id, version)` with different content MUST
  fail; a new `version` MUST succeed. (§2.1)
- **Instantiation ownership:** `instantiate` MUST set the caller as `owner` and status `created`;
  first control action MUST transition to `running`. (§2.3)
- **Access tiers:** an `observe`-tier participant MUST NOT be castable into a `speak` role;
  open-mic MUST be rejected unless the template enables it. (§1.6, §2.8)
- **Visibility/join:** a `private` instance MUST reject a join without a grant; a `public` instance
  MUST admit a join as `observe`. (§2.5)
- **Restore = full replay:** `restore` after N events MUST return all N in order; a joiner MUST
  receive the same log. (§2.9)
- **Open-mic pending:** an open-mic input MUST remain `pending` until a `human_input_addressed`
  event names it. (§2.8)
- **Gate timeout:** a `gate` role whose window elapses MUST yield status `provisional` with reason.
  (§2.8, §2.10)
- **Termination priority:** with both a budget breach and a satisfied `done` condition, status MUST
  be `budget`, not `done`. (§2.10)
- **Auth/identity:** a bearer token MUST resolve to exactly one `participant_id`; anonymous dev
  mode MUST resolve to the synthetic local participant. (§1.6)
- **Replay determinism:** rebuilding an instance from its log MUST reproduce `status`, `turn`, and
  roster. (D3)

---

## 7. Open Questions — status

| # | Status | Note |
|---|--------|------|
| TBD-1 | ✅ resolved | Extension points + SemVer (§1.10, Versioning). |
| TBD-2 | ✅ resolved | RFC 2119 (front matter). |
| TBD-3 | ✅ confirmed | Instance status enum created/running/awaiting + terminals (§1.3). |
| TBD-4 | ✅ resolved | `Role.kind ∈ {agent,human}` (§1.4). |
| TBD-5 | ✅ confirmed | Renamed `response_mode`→`response_requirement`; 3-value enum kept for v1 (`gate` split deferred, non-breaking); required-human timeout fix (§1.4, §2.8). |
| TBD-6 | ✅ resolved | Participant registry = §3.4 catalog. |
| TBD-7 | ✅ resolved | Canonical action set (§1.7). |
| TBD-8 | ✅ resolved | `PostActionVerification` (§1.7/§4). |
| TBD-9 | ✅ confirmed | Event taxonomy (§1.9), living/extensible. |
| TBD-10 | ✅ resolved | Auto-gen optional, I/O contract (§2.2). |
| TBD-11 | ✅ resolved | `flow` advisory/binding by mode (§2.6). |
| TBD-12 | ✅ resolved | `mode ∈ {plan,flow}` (§2.6). |
| TBD-13 | ✅ resolved | `human_policy` at role level (§2.8). |
| TBD-14 | ✅ resolved | `on_timeout ∈ {continue,finalize_provisional}`; `human_policy` now applies to any waited human (required or gate) (§2.8). |
| TBD-15 | ✅ resolved | `response_requirement` ↔ intervention (§1.4/§2.8). |
| TBD-16 | ✅ resolved | Termination priority order (§2.10). |
| TBD-17 | ✅ resolved | reserved binding = explicit binding; cross-user spawn = §2.5. |
| TBD-18 | ⏳ deferred | Exhaustive per-field constraints — pinned during Pydantic authoring (Phase 4). |
| TBD-19 | ✅ resolved | Conformance (§5). |
| TBD-20 | ✅ resolved | Acceptance criteria (§6), non-exhaustive. |
| TBD-21 | ✅ resolved | Template/Instance field partition (§4.1/4.2); template immutable per version. |
| TBD-22 | ✅ resolved | Registry ops (§3.4). |
| TBD-23 | ✅ resolved | Access model D5 (§1.6). |
| TBD-24 | ✅ resolved | Auth D6 (§1.6). |
| TBD-25 | ✅ confirmed | Multi-user concurrency = serialized transcript + queued inputs (§2.6); branching deferred. |
| TBD-26 | ✅ resolved | flow vs orchestrator (§2.6). |
| TBD-27 | ✅ resolved | Five layers incl. Registry & Hosting (§3.4). |
| TBD-28 | ✅ resolved | Restore = full replay, serves joiners (§2.9). |
| TBD-29 | ✅ resolved | One Registry surface, two catalogs (§3.4). |
| **TBD-30** | §1.5 / §1.7 | **(D8)** Per-binding credential resolution — v1 resolves keys from env by `provider`; multi-tenant / per-user key management deferred. |

**Owner-confirmed** (2026-07-09): TBD-3, TBD-5, TBD-9, TBD-25 — **all 4 〔derived〕 items now
confirmed.** **Deferred:** TBD-18 (field-level constraints, Phase 4), TBD-30 (multi-tenant key
management, post-v1).
