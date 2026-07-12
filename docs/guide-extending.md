# Guide: Extending DCP

DCP is a platform, not a black box. Its three "brains" are pluggable interfaces you implement in
isolation while the runtime handles the hard machinery — turn serialization, the append-only log,
replay/resume, termination priority, and delivery:

```
            ControlPolicy   — the orchestrator: who speaks / what control action
                 ▲
   ModelProvider ◀──▶ OversightPolicy — pre/post verification of every turn
```

You write one component; DCP runs it with everything else for free. And you **share** it as a normal
pip package via entry points — no hosted service, no lock-in. A complete, runnable example lives in
[`../examples/plugin-example/`](../examples/plugin-example/).

---

## 1. A custom orchestrator (`ControlPolicy`)

A control policy decides the **next control action** from a read-only `DialogueContext` (the replayed
state — transcript, roles, roster, turn, last speaker, plus the orchestrator's model provider). It
returns an `OrchestratorAction` — `select_speaker`, `stop` (terminate), or `suspend` (pause without
terminating, so a later `run()` resumes it). The runtime keeps ownership of oversight,
recovery/routing, termination, and replay — "policy proposes, runtime disposes."

```python
from dcp.orchestration import DialogueContext, OrchestratorAction
from dcp.schema import TerminationStatus

class RoundRobinPolicy:
    """Each role speaks once, in template order, then stop — using no model at all."""
    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        spoken = {m.role_id for m in ctx.messages}
        for role in ctx.roles:
            if role.role_id not in spoken:
                return OrchestratorAction(action="select_speaker", target_role_id=role.role_id)
        return OrchestratorAction(action="stop", status=TerminationStatus.DONE)
```

Use it directly:

```python
await server.run(instance_id, cast=..., control_policy=RoundRobinPolicy())
# or: Orchestrator(..., control_policy=RoundRobinPolicy())
```

A model-backed policy is just as simple — call `ctx.provider.structured(...)` inside `decide`
(that's exactly what the built-in `PlanPolicy` does). The built-ins `PlanPolicy` (emergent LLM
selection) and `FlowPolicy` (declared graph) are the defaults when you pass nothing.

## 2. Custom verification (`OversightPolicy`)

Oversight runs before every turn (speaker readiness → recovery) and after (output quality →
routing). The orchestrator **acts on** the records (D11): a post-action `outcome` of
`request_revision` sends the turn back, `escalate_gate` opens a human gate, etc.

**The easy way — one function per dimension with `RubricOversight`:**

```python
from dcp.orchestration import RubricOversight, CheckOutcome
from dcp.schema import Assessment

async def grounding(*, role, message, transcript) -> CheckOutcome:
    if "http" in message.content or "[" in message.content:   # crude "has a citation" check
        return CheckOutcome(Assessment.OK)
    return CheckOutcome(Assessment.WEAK, "no source cited")

oversight = RubricOversight(grounding=grounding)   # unset dimensions default to ok
await server.run(instance_id, cast=..., oversight=oversight)
```

A check returns a bare `Assessment` (`ok`/`weak`/`fail`) or a `CheckOutcome(assessment, issue)`. By
default a safety failure escalates to a human gate, any other non-`ok` requests a revision, and an
all-`ok` turn continues — override with `verdict_fn=...`.

**The full control way** — implement `pre` and `post` yourself (see `LlmOversight` for a model-backed
reference); anything structurally matching `OversightPolicy` works.

## 3. Custom models / agents (`ModelProvider`)

Any object with async `text(...)` and `structured(...)` is a provider — this is how you bring **your
own agent**. Point an agent or the orchestrator at it via a `ModelBinding{provider, model}`, or pass
a provider instance directly. One dialogue may mix providers (a GPT critic vs. a Claude strategist).
A provider that only ever *speaks* may implement `text` and leave `structured` unsupported.

```python
class LabProvider:
    def __init__(self, model: str = "lab-7b") -> None:
        self.model = model
    async def text(self, *, instructions: str, content: str) -> str:
        ...        # call your model, return the contribution
    async def structured(self, *, instructions, content, schema):
        ...        # return a validated `schema` instance (decisions/oversight)

await server.run(instance_id, cast=..., agent_providers={"@lab-agent": LabProvider()})
```

Packaged under a `dcp.providers` entry point, a provider **resolves by name** through
`build_provider` (so `ModelBinding(provider="lab_llm", …)` just works) — see §4 and
[guide-sharing.md](guide-sharing.md#4-share-an-agent). See also
[api-reference.md](api-reference.md#model-providers).

## 4. Share it — entry points

Ship your component as a package and declare an entry point; DCP discovers what's installed and
advertises it in `server_info`. All four kinds work the same way:

```toml
# your package's pyproject.toml
[project.entry-points."dcp.control_policies"]
round_robin = "my_pkg:RoundRobinPolicy"

[project.entry-points."dcp.oversight_policies"]
grounding = "my_pkg:GroundingOversight"

[project.entry-points."dcp.templates"]
research_companion = "my_pkg:research_companion"   # a DialogueTemplate or a 0-arg factory

[project.entry-points."dcp.providers"]
lab_llm = "my_pkg:LabProvider"                     # a ModelProvider — resolved by name
```

After `pip install`, discover and load by name:

```python
import dcp

dcp.available_plugins()
# {'dcp.control_policies': ['round_robin'], 'dcp.oversight_policies': ['grounding'],
#  'dcp.providers': ['lab_llm'], 'dcp.templates': ['research_companion']}

Policy   = dcp.load_plugin("dcp.control_policies", "round_robin")   # the class
template = dcp.plugins.load_template("research_companion")          # a DialogueTemplate

# a running server advertises installed components:
Server().server_info().plugins   # -> {group: [names]}
```

`list_plugins()` enumerates without importing; `load_plugin` imports on demand. There is no code
upload — a consumer installs your package deliberately, the standard Python way. For the full
distribution walkthrough of each of the four kinds, see [guide-sharing.md](guide-sharing.md).

## 5. The worked example

[`examples/plugin-example/`](../examples/plugin-example/) is a tiny package with one of each — a
`RoundRobinPolicy`, a `NoShoutingOversight` (a one-check rubric), a `two_agent_debate` template, and
an `EchoProvider` agent — wired via entry points. Install and use:

```bash
pip install -e examples/plugin-example
python -c "import dcp; print(dcp.available_plugins())"
```

Copy it as the skeleton for your own DCP components.

---

- [concepts.md](concepts.md) — the model these interfaces plug into.
- [api-reference.md](api-reference.md) — `ControlPolicy`, `OversightPolicy`, `RubricOversight`,
  `DialogueContext`, and the `dcp.plugins` surface.
