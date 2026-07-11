# dcp-plugin-example

A minimal package showing how to **share DCP components** — one of each kind — via Python entry
points. See [`../../docs/guide-extending.md`](../../docs/guide-extending.md) for the full walkthrough.

## What's inside

| Component | Kind | Entry point (group) |
|-----------|------|---------------------|
| `RoundRobinPolicy` | control policy (a custom orchestrator, no model) | `dcp.control_policies` |
| `NoShoutingOversight` | oversight policy (one rubric check) | `dcp.oversight_policies` |
| `two_agent_debate` | dialogue template (factory) | `dcp.templates` |

The wiring is in [`pyproject.toml`](pyproject.toml) under `[project.entry-points."dcp.*"]`.

## Try it

```bash
pip install -e examples/plugin-example      # from the repo root, after installing dcp
python -c "import dcp; print(dcp.available_plugins())"
# {'dcp.control_policies': ['round_robin'], 'dcp.oversight_policies': ['no_shouting'],
#  'dcp.templates': ['two_agent_debate']}
```

```python
import dcp
Policy   = dcp.load_plugin("dcp.control_policies", "round_robin")   # the class
template = dcp.plugins.load_template("two_agent_debate")           # a DialogueTemplate
```

Your own package works the same way: implement a `ControlPolicy` / `OversightPolicy` / template,
declare an entry point, `pip install`, and any DCP server discovers and advertises it.
