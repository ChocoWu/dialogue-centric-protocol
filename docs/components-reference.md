# Components reference — describe, resolve, run (local & remote)

The full reference behind [07 · Extending & Sharing](07-extending-sharing.md). A **DCP component** is
a *versioned capability or definition* — a control policy (orchestrator), oversight policy, model
provider, **agent**, or dialogue template — described by a machine-readable **manifest** and delivered
as a local Python package, a local package plus a model checkpoint, or a **remote service** you
connect to. One pipeline handles all of them: **describe → resolve → provision → run**.

> **Component vs. plugin.** [07 · Extending & Sharing](07-extending-sharing.md) also covers the quick
> in-process path (an entry point, `pip install`, resolve by name). The two coexist (D1): an installed
> entry point *is* one delivery mode of a component.

The normative design is [PROPOSAL-component-ecosystem.md](../PROPOSAL-component-ecosystem.md); the
remote wire is specified in [bindings/](../bindings/).

> **Runnable example:** [`examples/component/`](examples/component/) is a complete, key-free component
> (one manifest, two delivery modes): `python docs/examples/component/run_local.py` (resolve →
> materialize) and `python docs/examples/component/run_remote.py` (serve over HTTP → connect) print
> the same transcript.

## 1. The manifest

A component ships a `dcp-component.yaml` (or `.json`). Identity, interface, and the kind-specific
`spec` are separate blocks:

> **YAML is an optional extra.** Parsing `.yaml` needs `pip install 'dcp[yaml]'`. **JSON manifests
> work with no extra** — write `dcp-component.json` with the same shape.

```yaml
schema_version: "1.0"

component:                       # identity only
  namespace: alice
  name: research-orchestrator
  version: 1.2.0
  kind: control_policy           # control_policy | oversight_policy | model_provider | agent | template

metadata:
  description: "Planning / delegation / verification orchestrator."
  license: Apache-2.0

interface:
  name: dcp.control_policy       # namespaced; must match the kind (validated)
  version: "1.0"                 # the runtime-interface contract version

capabilities: [dcp.control.next_speaker]      # advisory, namespaced (dcp.* / ext.<you>.*)

access_modes:
  - type: local
    implementation:
      type: python_package
      source: pypi
      package: alice-dcp-orchestrator
      entrypoint: alice_orchestrator:ResearchControlPolicy
```

**Kinds** map to a runtime interface: `control_policy → ControlPolicy`,
`oversight_policy → OversightPolicy`, `model_provider → ModelProvider`, `agent → AgentDefinition`
(§4c), `template → DialogueTemplate`. Templates are *declarative* — the rest are *executable*.

**Access modes** — `local` (a package, optionally with model `artifacts`) or `remote` (an endpoint).
Not every mode is valid for every kind: a `template` has no weights or remote mode; `oversight_policy`
has no remote mode (governance stays with the dialogue owner, D9).

## 2. Resolve → inspect → install → use

Resolution is **side-effect-free**: it locates, validates, selects a mode, and produces an
inspectable **plan** — it never installs or downloads. Provisioning and instantiation are explicit
later stages. A reference is a `file://` path or `installed://name`:

```bash
dcp inspect  file://./dcp-component.yaml     # print the plan; RUNS NOTHING
dcp install  file://./dcp-component.yaml -y  # resolve → consent → provision (pip install)
dcp use      file://./dcp-component.yaml -y  # install if needed → materialize → confirm the type
```

`dcp inspect` shows exactly what *would* happen:

```
component: alice/research-orchestrator @ 1.2.0  (control_policy)
interface: dcp.control_policy 1.0
mode:      local
side effects:
  - provision: install pypi:alice-dcp-orchestrator
  - instantiate: import alice_orchestrator:ResearchControlPolicy
licenses:
  - component license: Apache-2.0
```

The same three stages in code:

```python
from dcp.component import resolve, provision, materialize

plan = resolve("file://./dcp-component.yaml")     # ComponentResolutionPlan — no side effects
report = provision(plan)                           # pip install if the package is absent (idempotent)
policy = materialize(plan, artifacts=report.artifacts)   # import the entrypoint → a ControlPolicy
```

The materialized `policy` is a normal `ControlPolicy` — hand it to `Server.run(..., control_policy=…)`
(see [04 · Orchestrator](04-orchestrator.md)).

## 3. Local model + checkpoint (open-weights components)

An open-weights orchestrator or agent ships a `local` mode with **artifacts** — checkpoints carried
by reference, with a mandatory digest:

```yaml
access_modes:
  - type: local
    implementation:
      type: python_package
      source: pypi
      package: alice-dcp-orchestrator
      entrypoint: alice_orchestrator:load     # a factory: load(checkpoint_path) -> the object
    artifacts:
      - uri: "hf://alice/orchestrator-7b@<revision>"
        digest: { algorithm: sha256, value: "…" }
        size_bytes: 15600000000
        format: safetensors
```

`provision` downloads each artifact, **verifies the digest** (a mismatch is rejected, never cached),
and caches it **content-addressed** (`$DCP_CACHE_DIR`, else `~/.cache/dcp/artifacts`). `materialize`
then calls the entrypoint as `factory(checkpoint_path)`. `hf://` needs `pip install 'dcp[hf]'`;
`file://` and `https://` artifacts need no extra. For reproducible installs, write a lockfile:

```bash
dcp install file://./dcp-component.yaml -y --lock dcp-components.lock
```

A `TransformersProvider` (Qwen3 and friends) accepts a local checkpoint directly —
`TransformersProvider.from_checkpoint(path)` — so a model-provider component's factory is often a
one-liner.

## 4. Remote components

When a component is too large to run locally, or the author keeps it hosted, declare a `remote` mode.
The consumer **connects** instead of installing — no code or weights are downloaded; the component
runs on the author's server.

### 4a. Host a component (the author's side)

Host a **payload handler** (the wire contract is the projected payload, not a Python type):

```python
from dcp.component import ComponentManifest, serve_component
from dcp.orchestration import OrchestratorAction
from dcp.schema import TerminationStatus
import uvicorn

manifest = ComponentManifest.model_validate({...})     # kind: control_policy, a remote access_mode

def decide(payload: dict) -> OrchestratorAction:        # payload = the projected DialogueContext
    spoken = {m["role_id"] for m in payload.get("transcript", [])}
    for role in payload["roles"]:
        if role["role_id"] not in spoken:
            return OrchestratorAction(action="select_speaker", target_role_id=role["role_id"])
    return OrchestratorAction(action="stop", status=TerminationStatus.DONE)

app = serve_component(manifest, decide=decide, token="…optional bearer…")
uvicorn.run(app, host="0.0.0.0", port=8000)
```

An **agent** hosts a `generate` operation (payload → `{"text": …}`) and, for token-by-token output,
a streaming operation:

```python
def generate(payload: dict) -> dict:                    # non-streaming: full contribution
    return {"text": run_llm(payload["content"])}

async def generate_stream(payload: dict):               # streaming: incremental frames
    for tok in llm_tokens(payload["content"]):
        yield tok

app = serve_component(manifest, operations={"generate": generate},
                      stream_operations={"generate": generate_stream})
```

The server exposes `GET /component` (a **descriptor** of what's actually deployed), `GET /health`, and
`POST /invoke` (add `Accept: text/event-stream` for SSE).

### 4b. Connect to a component (the consumer's side)

```python
from dcp.component import resolve, http_transport, connect

plan = resolve("file://./remote-orchestrator.yaml", mode="remote")
transport = http_transport(plan, token="…")            # bearer from --token or $DCP_CRED_<SLOT>
policy = await connect(plan, transport)                # verifies the descriptor vs the manifest (D20)
# `policy` is a RemoteControlPolicy — a normal ControlPolicy; use it anywhere a local one goes.
```

From the CLI:

```bash
DCP_CRED_TOKEN=secret dcp connect file://./remote-orchestrator.yaml    # verify + print the descriptor
dcp use file://./remote-orchestrator.yaml --mode remote --token secret # connect + confirm ready
```

A remote **agent** connects the same way — `connect` returns an `AgentDefinition` (§4c), which is also
a drop-in `agent_provider`:

```python
agent = await connect(resolve("file://./remote-agent.yaml", mode="remote"), transport)
await server.run(instance_id, cast={"scout": "@scout"}, agent_providers={"@scout": agent})
# token-by-token, if you want it (streaming lives on the underlying provider):
async for frame in agent.provider.stream_text(instructions="search", content="…"):
    print(frame, end="")
```

### 4c. Agents: definition → participant (the identity path)

An `agent` component doesn't materialize into a bare provider — it becomes an **`AgentDefinition`**
(local via `materialize`, remote via `connect`): the shareable blueprint (persona defaults,
capabilities, a bound provider). Instantiate it into a **registered `Participant`** — the identity
step (D2/D10) — and materialize its `role_defaults` into a `Role` (fills an empty persona, never
overrides one — D8):

```python
defn = materialize(resolve("file://./scout-agent.yaml"))    # or: await connect(plan, transport)
scout = defn.to_participant("@scout")                        # a Participant with an @id + capabilities
role = defn.apply_role_defaults(role)                        # seed the seat's persona (if it has none)

server.register_participant(scout)
await server.run(instance_id, cast={"scout": "@scout"}, agent_providers={"@scout": defn})
```

`AgentDefinition` also *acts as* a `ModelProvider` (it delegates `text`/`structured`), which is why it
drops straight into `agent_providers`.

### What remote guarantees (and doesn't)

- **Descriptor verification (D20):** `connect` refuses if the deployed identity/interface/binding
  disagrees with the manifest.
- **Owner-controlled projection (D12):** *you* decide what leaves your boundary with a
  `ContextProjection` (full / summary / omit per field); what was transmitted is recorded in the
  event log (`CONTEXT_PROJECTED`, with a digest).
- **Credentials (D22):** the manifest names a logical `credential_slot`; you map it to a token
  (`$DCP_CRED_<SLOT>` or `--token`). Secrets are never in a manifest or lockfile.
- **Reliability (D13):** single attempt, **no automatic retry**; after an ambiguous failure a
  duplicate call is possible. Only a `stateless` agent is treated as retry-safe.
- **Excluded:** remote **oversight** — governance stays on the owner's machine (D9).

## 5. Reference

**CLI**

| Command | Does |
|---------|------|
| `dcp inspect <ref>` | resolve + print the plan (no side effects) |
| `dcp install <ref> [-y] [--lock PATH]` | resolve → consent → provision (+ artifacts, + lockfile) |
| `dcp use <ref> [-y] [--mode remote] [--token T]` | install/connect → materialize/verify |
| `dcp connect <ref> [--token T]` | verify a remote endpoint, print its descriptor |

**Python** (`dcp.component`)

```python
resolve(ref, *, mode=None, mode_preference=None) -> ComponentResolutionPlan   # side-effect-free
provision(plan) -> ProvisionReport                    # pip install + artifact download/verify/cache
materialize(plan, *, artifacts=()) -> object          # local → runtime interface / AgentDefinition
connect(plan, transport, *, projection=None)          # remote → RemoteControlPolicy/RemoteAgent/AgentDefinition
http_transport(plan, *, token=None) -> HttpRemoteTransport
serve_component(manifest, *, decide=/operations=/stream_operations=, token=None) -> ASGI app
write_lock(plan, path) / read_lock(path)              # dcp-components.lock
render_plan(plan) -> str                              # what `dcp inspect` prints

# AgentDefinition (an `agent` component; also acts as a ModelProvider):
defn.to_participant(id, *, discoverable=False) -> Participant   # the identity step (D2)
defn.apply_role_defaults(role) -> Role                          # fill an empty persona (D8)
```

## Deferred (v1 scope)

- Reference schemes: `file://` and `installed://` resolve today; `git+…` / `pypi://` / `hf://`
  *manifest* resolvers land later (artifact `hf://` download works now).
- Full-payload projection retention (beyond metadata+digest); a central registry, `dcp://` names, and
  `search` — all v1.5.

---

- [07 · Extending & Sharing](07-extending-sharing.md) — the reading-path guide this backs.
- [PROPOSAL-component-ecosystem.md](../PROPOSAL-component-ecosystem.md) — the full design contract.
- [bindings/remote-component.md](../bindings/remote-component.md) — the remote wire semantics.
