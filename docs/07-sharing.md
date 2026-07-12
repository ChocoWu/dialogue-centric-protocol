# Guide: Sharing your DCP components

DCP is a platform, not a walled garden. The four things you can build — a **dialogue template**, a
**custom orchestrator**, a **verification method**, and an **agent** — are all shared the same way:
you ship a normal Python package that declares an **entry point**, and DCP discovers it once it's
installed. There is **no hosted code-upload service** and no lock-in — a consumer installs your
package deliberately (`pip install your-pkg`) and resolves your component **by name**.

> This is the quick in-process path. For a portable **manifest** with pinned references, model
> checkpoints, dependencies, lockfiles, and **remote** delivery, see
> [08-components.md](08-components.md) — the two coexist (an installed entry point is one
> delivery mode of a component).

| You built… | Interface | Entry-point group | Consumers load it with | Runtime resolves it via |
|------------|-----------|-------------------|------------------------|-------------------------|
| a **template** | `DialogueTemplate` (or a 0-arg factory) | `dcp.templates` | `plugins.load_template(name)` | — (used directly) |
| an **orchestrator** | `ControlPolicy` | `dcp.control_policies` | `plugins.load_control_policy(name)` | `control_policy=…` |
| a **verification method** | `OversightPolicy` | `dcp.oversight_policies` | `plugins.load_oversight_policy(name)` | `oversight=…` |
| an **agent** | `ModelProvider` | `dcp.providers` | `plugins.load_model_provider(name)` | `ModelBinding(provider=name)` |

Authoring each interface is covered in [05-extending.md](05-extending.md); this guide is about
**packaging and distributing** what you built. A complete package with one of each lives in
[`../examples/plugin-example/`](../examples/plugin-example/).

## The packaging recipe (same for all four)

1. Make a small package that imports `dcp` and exposes your object (a class, a factory function, or —
   for a template — a ready instance).
2. Declare an entry point in its `pyproject.toml` under the matching group above.
3. Publish it (PyPI) or share the repo. Consumers `pip install` it; DCP sees it immediately.

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
# {'dcp.templates': ['lit_review'], 'dcp.control_policies': ['cost_aware'],
#  'dcp.oversight_policies': ['citation_check'], 'dcp.providers': ['lab_llm']}
```

---

## 1. Share a dialogue template

Package a `DialogueTemplate` (or a 0-arg factory returning one). Consumers load and register it:

```python
from dcp import plugins, Server

template = plugins.load_template("lit_review")   # a DialogueTemplate
Server().register_template(template)
```

Tips: give it a stable `template_id` / `version` (templates are immutable per `(id, version)`), seat
at least one human, and set `human_policy_defaults`. See [03-templates.md](03-templates.md).

## 2. Share a custom orchestrator

Package a `ControlPolicy` (an object with `async decide(ctx) -> OrchestratorAction`). Consumers load
it by name and hand it to a run — the runtime still owns oversight, recovery, and termination:

```python
from dcp import plugins

Policy = plugins.load_control_policy("cost_aware")     # the class
await server.run(instance_id, cast=..., control_policy=Policy())
```

## 3. Share a verification method

Package an `OversightPolicy` (pre/post verification), or the easy one-check-per-dimension
`RubricOversight`. Consumers load it and pass it as `oversight`; the orchestrator **acts on** its
verdicts (revise / escalate to a human gate / stop):

```python
from dcp import plugins

Oversight = plugins.load_oversight_policy("citation_check")
await server.run(instance_id, cast=..., oversight=Oversight())
```

## 4. Share an agent

An "agent" you share is a **`ModelProvider`** — an object with `async text(...)` (contributions) and
`async structured(...)` (decisions/oversight). Unlike the others, an agent resolves **by name inside
the model binding**, so a consumer never has to import your class at all — they just name your
provider:

```python
from dcp import build_provider
from dcp.schema import ModelBinding

# construct it directly…
provider = build_provider(ModelBinding(provider="lab_llm", model="lab-7b"))

# …or wire it into a run as one participant's agent
await server.run(
    instance_id, cast={"scout": "@lab-agent"},
    agent_providers={"@lab-agent": provider},
)
```

Because it resolves by name, a shared agent also drops into a template's `ModelBinding` and into the
env default (`DCP_MODEL_PROVIDER=lab_llm`) — anywhere a built-in provider name works. A built-in name
(`openai`/`anthropic`/`local`/`transformers`/`mock`) always wins, so a plugin can't shadow one.

An agent that only ever *speaks* may implement `text` and leave `structured` unsupported — that's a
valid, common shape (only orchestrators/oversight call `structured`). The example `EchoProvider` does
exactly this.

---

## How a server advertises what it offers

A running server surfaces installed components so clients can discover them — no out-of-band docs
needed:

```python
info = Server().server_info()
info.plugins            # {group: [names]} across all four groups
info.model_providers    # built-ins + installed provider plugins, each with a `configured` flag
```

From the command line:

```bash
dcp plugins     # every installed plugin, by group
dcp info        # capabilities + model providers (built-in and plugin) + plugins
```

## The worked example

[`examples/plugin-example/`](../examples/plugin-example/) is a tiny package wiring **all four** via
entry points — a `two_agent_debate` template, a `RoundRobinPolicy`, a `NoShoutingOversight`, and an
`EchoProvider` agent. Install it and DCP discovers every one:

```bash
pip install -e examples/plugin-example
python -c "import dcp; print(dcp.available_plugins())"
# {'dcp.control_policies': ['round_robin'], 'dcp.oversight_policies': ['no_shouting'],
#  'dcp.providers': ['echo'], 'dcp.templates': ['two_agent_debate']}
```

Copy it as the skeleton for your own DCP components.

---

- [05-extending.md](05-extending.md) — how to *author* each of the four interfaces.
- [03-templates.md](03-templates.md) — authoring and adapting templates.
- [10-api-reference.md](10-api-reference.md#plugins) — the `dcp.plugins` surface and loaders.
