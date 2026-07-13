# Extending & Sharing

DCP is a platform, not a black box. The pieces you can build are pluggable interfaces you implement in isolation; then you distribute them so others resolve your work **by name**. 
This doc is the map of *what* you can extend and *how* to ship it; the deep authoring of each interface lives in its home doc.

## 1 · What you can extend

| You build… | Interface | Authored in | Wired in via |
|------------|-----------|-------------|--------------|
| a **template** | `DialogueTemplate` | [03 · Templates & Instances](03-dialogue-template.md) | `register_template` |
| a **custom orchestrator** | `ControlPolicy` | [04 · Orchestrator](04-orchestrator.md#control-policies) | `control_policy=…` |
| a **verification method** | `OversightPolicy` | [04 · Orchestrator](04-orchestrator.md#oversight-policies) | `oversight=…` |
| an **agent / model** | `ModelProvider` | [05 · Participant](05-participant.md#bring-your-own-agent) | `ModelBinding(provider=name)` / `agent_providers=` |

You write one object; the runtime keeps everything else (turn serialization, the log, replay, termination, delivery). This doc is about **distributing** those objects.

## 2 · Two ways to distribute — which one?

They **coexist** (an installed entry point is simply one delivery mode of a component):

| | **Plugin** (§3) | **Component** (§4) |
|---|-----------------|--------------------|
| What | a pip package with an **entry point** | a machine-readable **manifest** |
| Resolve | by name, in-process | resolve → provision → materialize / connect |
| Carries | just code | code **+ pinned refs, model checkpoints, lockfiles** |
| Delivery | local (installed) | local **or remote** service |
| Best for | a policy/template you and your team use | publishing an open-weights orchestrator, or hosting an agent others connect to |

Start with a plugin; reach for a component when you need checkpoints or remote hosting.

## 3 · Share as a plugin (the quick path)

Ship a normal Python package that declares an **entry point**; DCP discovers it once installed. 
No hosted upload service, no lock-in — a consumer `pip install`s your package deliberately and resolves your component by name.

| You built… | Entry-point group | Consumers load it with | Runtime resolves via |
|------------|-------------------|------------------------|----------------------|
| a template | `dcp.templates` | `plugins.load_template(name)` | — (used directly) |
| an orchestrator | `dcp.control_policies` | `plugins.load_control_policy(name)` | `control_policy=…` |
| a verification method | `dcp.oversight_policies` | `plugins.load_oversight_policy(name)` | `oversight=…` |
| an agent | `dcp.providers` | `plugins.load_model_provider(name)` | `ModelBinding(provider=name)` |

**The packaging recipe** (same for all four): expose your object (a class, a factory, or — for a template — a ready instance), declare the entry point, publish/share; consumers `pip install`.

```toml
# your-pkg/pyproject.toml
[project]
name = "dcp-lab-components"
dependencies = ["dcp"]

[project.entry-points."dcp.templates"]
lit_review = "dcp_lab:lit_review"            # a DialogueTemplate or a 0-arg factory
[project.entry-points."dcp.control_policies"]
cost_aware = "dcp_lab:CostAwarePolicy"       # a ControlPolicy class
[project.entry-points."dcp.oversight_policies"]
citation_check = "dcp_lab:CitationOversight" # an OversightPolicy class
[project.entry-points."dcp.providers"]
lab_llm = "dcp_lab:LabProvider"              # a ModelProvider class/factory
```

Discovery is metadata-only until you load — nothing is imported just by being installed:

```python
import dcp
dcp.available_plugins()
# {'dcp.templates': ['lit_review'], 'dcp.control_policies': ['cost_aware'], …}
```

### Per-kind consumer snippets

<a id="share-a-template"></a>**Template** — load and register:
```python
from dcp import plugins, Server
Server().register_template(plugins.load_template("lit_review"))
```

**Orchestrator** — load and hand to a run (runtime still owns oversight/recovery/termination):
```python
Policy = plugins.load_control_policy("cost_aware")
await server.run(instance_id, cast=..., control_policy=Policy())
```

**Verification method** — load and pass as `oversight`:
```python
Oversight = plugins.load_oversight_policy("citation_check")
await server.run(instance_id, cast=..., oversight=Oversight())
```

<a id="share-an-agent"></a>**Agent** — resolves **by name inside the model binding**, so a consumer never imports your class; they just name your provider (and it drops into a template binding or the env default `DCP_MODEL_PROVIDER=lab_llm` too). A built-in name always wins, so a plugin can't shadow one:
```python
from dcp import build_provider
from dcp.schema import ModelBinding
provider = build_provider(ModelBinding(provider="lab_llm", model="lab-7b"))
await server.run(instance_id, cast={"scout": "@lab-agent"}, agent_providers={"@lab-agent": provider})
```

A running server advertises what it offers — `Server().server_info().plugins` / `.model_providers`, or `dcp plugins` / `dcp info`. A complete package wiring **all four** is [`../examples/plugin-example/`](../examples/plugin-example/) — copy it as your skeleton.

## 4 · Share as a component (portable, local or remote)

A **component** is a *versioned capability* described by a machine-readable **manifest** and delivered as a local package, a local package **+ a model checkpoint**, or a **remote service** you connect to.
One pipeline handles all of them: **describe → resolve → provision → run**.

```bash
dcp inspect  file://./dcp-component.json     # resolve + print the plan; RUNS NOTHING
dcp install  file://./dcp-component.json -y  # resolve → consent → provision (pip + artifacts)
dcp use      file://./dcp-component.json -y  # install/connect → materialize/verify
dcp connect  file://./remote.json --token T  # verify a remote endpoint; print its descriptor
```

```python
from dcp.component import resolve, provision, materialize
plan   = resolve("file://./dcp-component.json")      # side-effect-free plan
report = provision(plan)                             # pip install + artifact download/verify/cache
policy = materialize(plan, artifacts=report.artifacts)   # → a normal ControlPolicy
```

- **Local + checkpoint** — an open-weights orchestrator/agent carries digest-verified `artifacts` (checkpoints); `provision` downloads + verifies + content-addresses them.
- **Remote** — too large to run locally, or kept hosted: the consumer **connects** (no code/weights downloaded), the component runs on the author's server, and `connect` verifies the deployed descriptor against the manifest. *You* control what context leaves your boundary (owner projection).
- **Agents** take an identity path: an `agent` component materializes/connects into an `AgentDefinition` → `to_participant("@id")` → a registered Participant.

The full manifest schema, checkpoints, remote host/connect, the agent identity path, reliability, and the CLI/Python reference are in **[Components reference](components-reference.md)**; the runnable, key-free example is [`examples/component/`](examples/component/) (one manifest, run local *and* remote). 
The remote **wire protocol** is specified in [`../bindings/`](../bindings/).

## 5 · When to use which

- **Private / team** — a plugin (`pip install` from your repo).
- **Public release** — a plugin on PyPI, or a component with pinned refs + a lockfile for
  reproducibility.
- **Open-weights or hosted** — a component: local + checkpoint, or a remote service others connect to.

---

**Next:** [08 · Evaluation](08-evaluation.md) — measure what you built. · [All docs](README.md)
