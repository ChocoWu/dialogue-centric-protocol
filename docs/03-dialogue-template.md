# Templates & Instances

The single most important idea in DCP: a **DialogueTemplate** is the reusable *pattern*; a **DialogueInstance** is one *run* of it. 
Get this split right and everything else follows.

## 1 · What & why the split

- A **template** defines *how this kind of dialogue works*: its roles, the succession structure (`flow`) over those roles, the orchestration `mode`, and sensible defaults for goal and termination. It is **immutable** per `(template_id, version)` — register it once, reuse it forever.
- An **instance** is *one occurrence* aimed at a concrete task. It supplies this run's `goal`, `termination`, and `brief`, and then carries all the runtime state (transcript, roster, status).

Why bother splitting? **Reuse.** A single "design review" template should serve naming a product, reviewing an API, or vetting an architecture — the *mechanism* (propose → critique → approve) is the same; only the *task* changes. 
Baking the task into the template would make it single-use. So:

> **Structure lives in the template; content lives in the instance.**
> `roles` / `flow` / `mode` are the template's. `goal` / `termination` / `brief` are the instance's.

## 2 · Template fields

```python
from dcp import schema as s

TEMPLATE = s.DialogueTemplate(
    template_id="design-review", version="1.0.0",   # identity — immutable per (id, version)
    title="Design review",                          # generic pattern name, not one task
    goal="Converge on a proposal the approver signs off on.",     # generic; instance may override
    termination_policy=s.TerminationPolicy(condition="the approver approves", max_turns=8),
    roles=[
        s.Role(role_id="proposer", name="Proposer", kind=s.RoleKind.AGENT,
               persona="You propose candidates, one at a time, each with a rationale.",
               response_requirement=s.ResponseRequirement.REQUIRED),
        s.Role(role_id="critic", name="Critic", kind=s.RoleKind.AGENT,
               persona="You critique proposals for clarity and risk.",
               response_requirement=s.ResponseRequirement.REQUIRED),
        s.Role(role_id="approver", name="Approver", kind=s.RoleKind.HUMAN,
               response_requirement=s.ResponseRequirement.GATE),
    ],
    orchestration=s.Orchestration(mode=s.OrchestrationMode.PLAN),   # plan (emergent) | flow (graph)
    # flow=s.Flow(entry="proposer", edges=[...]),                   # required when mode=flow
)
```

| Field | Meaning | Layer note |
|-------|---------|------------|
| `template_id`, `version` | Identity. Immutable per pair; a change is a **new version** (§2.1). | structure |
| `title`, `topic` | Human-readable name/subject of the *pattern*. Keep generic. | structure |
| `goal` | The pattern's generic purpose. **An instance may override it** (§ below). | structure (default) |
| `termination_policy` | `condition` (free-text, shown to the orchestrator) + `max_turns` + `token_budget`. **An instance may override it.** | structure (default) |
| `roles[]` | The seats: `role_id`, `name`, `kind` (`agent`/`human`), `persona`, `response_requirement` (`required`/`optional`/`gate`), optional `binding` and `human_policy`. | structure |
| `orchestration.mode` | `plan` (emergent — the orchestrator's model picks each speaker) or `flow` (succession constrained to the graph). | structure |
| `orchestration.model_binding` | Optional per-template model for the orchestrator (else the server default). | structure |
| `flow` | `entry` + `edges` succession graph over the roles. Advisory in `plan` mode, binding in `flow` mode (§2.6). | structure |
| `human_policy_defaults` | Default wait window + timeout for waited human roles (roles may override). | structure |
| `default_visibility` | `public`/`unlisted`/`private` applied at instantiate unless overridden. | structure |
| `allow_open_mic` | Let `observe`-tier participants interject (§2.8). | structure |
| `metadata` | Open map for your own keys (preserved; never interpreted by the protocol). | — |

> **Flow is template-level.** It is a graph over the template's `roles`, so it belongs with them —
> not with the per-run instance. In `plan` mode a declared flow is an *advisory hint* the
> orchestrator's model may follow or override; in `flow` mode it *binds* succession. See
> [04 · Orchestrator](04-orchestrator.md#control-policies).

## 3 · The instance — per-run inputs

You create an instance from a template and aim it at *this* task. Three inputs are per-run, and each **overrides** the template's default (effective value = instance's when set, else the template's):

```python
server.instantiate(
    s.TemplateRef(template_id="design-review", version="1.0.0"),
    owner="founder", instance_id="demo",
    goal="Agree on a product name the founder approves.",        # overrides template.goal
    termination=s.TerminationPolicy(condition="the founder approves", max_turns=6),  # overrides
    brief={"product": "a devtools startup", "constraints": ["one word", "memorable"]},
)
```

| Input | What it is | Effective value |
|-------|-----------|-----------------|
| `goal` | This run's concrete objective. | `instance.goal or template.goal` |
| `termination` | This run's completion condition + caps. | `instance.termination_policy or template.termination_policy` |
| `brief` | Free-form structured task input (product, audience, constraints, …). | as given (default `{}`) |
| `owner` | The `participant_id` that owns the instance (gets the `own` tier). | required |
| `visibility` | `public`/`unlisted`/`private`. | else the template's default, else `private` |

All three (`goal`/`termination`/`brief`) are **recorded in the `instance_created` event** so they replay (D3), and all are **surfaced to the orchestrator and every agent** so they act on *this* task rather than the generic template. 
The rest of a `DialogueInstance` — `status`, `turn`, `roster`, `messages`, `events`, `open_gates`, `pending_inputs`, `budget` — is runtime state, all derived from the log (§4).

## 4 · Create a template — four ways

| Way | How | When |
|-----|-----|------|
| **By hand** | Construct a `DialogueTemplate` (as in §2). | You know the shape you want. |
| **From a preset** | `presets.get_preset("design_review")` → a ready template you copy and adapt. | Start from a working pattern. |
| **Auto-generate** | `await registry.generate_template("a debate about a plan")` → a *draft* to review, edit, register. | You have a prompt, not a schema. Needs a `TemplateGenerator` wired in — see [06](06-hosting-delivery.md#auto-generation). |
| **From a shared plugin/component** | `load_template("name")` after `pip install`. | Reuse someone else's template — see [07](07-extending-sharing.md). |

### Presets

DCP ships a small catalog so you rarely start from scratch:

| Preset | Roles | Mode | Use |
|--------|-------|------|-----|
| `design_review` | Proposer, Critic · Owner (gate) | flow | Converge on a design a human approves |
| `debate` | Optimist, Skeptic · Judge (gate) | flow | Both sides of a question, then a verdict |
| `brainstorm` | Facilitator, Divergent, Pragmatist · User (optional) · open-mic | plan | Diverge, shortlist; humans chime in |
| `red_team_review` | Author, Red Teamer, Safety Reviewer · Approver (gate) | flow | Stress-test a plan before sign-off |
| `research_companion` | Scout, Methodologist, Writing Coach · Advisor (gate) · Student (optional) | flow | Advance a research question |

`presets.list_presets()` enumerates them; each has a direct factory (`presets.design_review()`). 
A preset is a plain `DialogueTemplate` — copy, `model_copy(update={...})`, and register under **your own** `template_id`/`version`. 
Common adaptations: change personas / add a role / switch a role's `response_requirement`; keep `plan` or switch to `flow` with a graph; adjust `termination_policy`; set `allow_open_mic=True`.

## 5 · Use a template

```python
server.register_template(TEMPLATE)                  # once; re-registering identical content is a no-op
server.register_participant(s.Participant(participant_id="proposer", kind=s.RoleKind.AGENT,
                                          display_name="Proposer"))
# … register critic, approver …
server.instantiate(ref, owner="founder", instance_id="demo", goal=..., termination=..., brief=...)
result = await server.run("demo", cast={"proposer": "proposer", ...}, human_gateway=...)
```

`cast` maps `role_id → participant_id`. Running (and resuming) is the [Orchestrator](04-orchestrator.md)'s job; who participates and how models are bound is [Participant](05-participant.md); hosting it for multiple users is [Hosting & Delivery](06-hosting-delivery.md).

## 6 · Lifecycle & persistence

- **Templates are immutable.** To publish a change, bump `version`. This guarantees an instance's `template_ref` always resolves to exactly the definition it was created from.
- **Instances are runtime state, derived from the log.** `instantiate` creates one in status `created`; the first orchestration action moves it to `running`; it reaches a terminal status (`done`/`provisional`/`stopped`/`budget`/`error`, §2.10).
- **Everything replays.** `restore(instance_id)` rebuilds the full `DialogueInstance` from its `messages + events` (D3) — the same path that lets the orchestrator **resume** a partway run, a **late joiner** catch up, and an evaluator **audit** after the fact. A run can also `suspend` on purpose (pause without terminating) so a later `run()` continues it across sessions. Operationally, this is `server.run(...)` (auto-resumes) and `GET /instances/{id}` (full replay) — see [06 · Hosting & Delivery](06-hosting-delivery.md).

## 7 · Share your template

Package a template factory under a `dcp.templates` entry point so others `pip install` and `load_template("name")` it — or publish it as a portable component. 
See [07 · Extending & Sharing](07-extending-sharing.md#share-a-template).

---

**Next:** [04 · Orchestrator](04-orchestrator.md) — how a template is *driven and overseen* into a finished dialogue. · [All docs](README.md)
