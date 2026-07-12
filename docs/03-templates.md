# Guide: Templates & presets

A **DialogueTemplate** is the reusable definition of a dialogue — its roles, how it ends, and how it's orchestrated. 
DCP ships a small library of **presets** so you can start from a working template
and adapt it, rather than authoring one from scratch.

## Use a preset

```python
from dcp import presets, Server, schema as s

server = Server(database_url="sqlite:///:memory:")
template = presets.get_preset("design_review")     # a fresh DialogueTemplate
server.register_template(template)
# ... register participants, cast roles, run (see 01-quickstart.md)
```

`presets.list_presets()` enumerates them; each name also has a direct factory (`presets.design_review()`).

## The catalog

| Preset | Roles | Orchestration | When to use |
|--------|-------|---------------|-------------|
| `design_review` | Proposer, Critic (agents) · Owner (human gate) | flow | Converge on a design decision a human approves, with risks surfaced |
| `debate` | Optimist, Skeptic (agents) · Judge (human gate) | flow | Explore both sides of a contested question, then a judged conclusion |
| `brainstorm` | Facilitator, Divergent, Pragmatist (agents) · User (human, optional) · open-mic | plan | Generate diverse ideas and shortlist; humans may chime in freely |
| `red_team_review` | Author, Red Teamer, Safety Reviewer (agents) · Approver (human gate) | flow | Stress-test a plan for failure modes and safety before sign-off |
| `research_companion` | Scout, Methodologist, Writing Coach (agents) · Advisor (human gate) · Student (human, optional) | flow | Help a student advance a research question into a grounded direction |

All presets seat at least one human and set `human_policy_defaults` (so a waited human can never hang the instance).

Every preset except `brainstorm` declares a **non-linear `flow`** and runs in **`mode: flow`** — the natural (branching/looping) succession of its roles. 
For example `design_review` iterates `proposer ⇄ critic` and lets the critic's turn advance to the `owner`; `research_companion` runs `scout → methodologist → coach → advisor` with loops back for more literature or another revision.

Under `mode: flow`, succession is **guided** — constrained to the flow's edges (deterministic when a role has one outgoing edge; the orchestrator's model chooses among the allowed roles at a branch).
The flow is the *initial* order, not a rigid script: the oversight loop may still adapt it at runtime (e.g. switch to an alternative when a candidate isn't ready — SPEC §2.6). 
`brainstorm` is genuinely emergent, so it uses `mode: plan` with no flow.

## Adapt a preset

A preset is a plain `DialogueTemplate` — copy and change what you need, then register it under **your own** `template_id` / `version`:

```python
t = presets.get_preset("debate")
t = t.model_copy(update={
    "template_id": "my-debate",
    "roles": [*t.roles],                 # add/replace roles
    "orchestration": s.Orchestration(mode=s.OrchestrationMode.FLOW),
    "flow": s.Flow(entry="optimist", edges=[s.Edge(from_role="optimist", to_role="skeptic")]),
})
server.register_template(t)
```

Common adaptations:

- **Roles** — change personas, add a role, or switch a role's `response_requirement` (`required` / `optional` / `gate`).
- **Orchestration** — keep `plan` (emergent) or switch to `flow` with a declared graph; or supply a custom `ControlPolicy` at run time (see [05-extending.md](05-extending.md)).
- **Termination** — adjust `termination_policy.condition` / `max_turns`.
- **Open mic** — set `allow_open_mic=True` to let `observe`-tier participants interject.

## Author from scratch

Presets are optional — you can build a `DialogueTemplate` directly (see the hello-world in [01-quickstart.md](01-quickstart.md) and the field reference in [10-api-reference.md](10-api-reference.md)).

## Share your template

Package a template factory and declare a `dcp.templates` entry point so others can `pip install` and `load_template("name")` it — see [07-sharing.md](07-sharing.md#1-share-a-dialogue-template).

---

**Next:** [04-hosting.md](04-hosting.md) to run a template as a multi-user server, or [05-extending.md](05-extending.md) to drive it with a custom orchestrator. ·
[All docs](README.md)
