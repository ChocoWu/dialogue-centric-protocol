# Guide: Hosting, access, and delivery

DCP is server-hosted (decision D2): templates and participants are **registered**, instances are
**addressable and joinable** by other users under access control. This guide covers the
Registry & Hosting layer (§3.4) and the HTTP/SSE delivery binding (§3.5).

## The Registry

`Registry` is one surface over two catalogs (templates + participants) plus the hosting operations.
It is persisted through a `Store`.

```python
from dcp import Registry, SqlStore

reg = Registry(SqlStore("sqlite:///./dcp.db"))
```

### Templates — immutable per version (§2.1)

```python
reg.register_template(template)                 # first registration of (id, version)
reg.register_template(template)                 # identical re-register → no-op (idempotent)
reg.register_template(template_changed)         # same (id, version), new content → RegistryError
reg.get_template("design-review", "1.0.0")
reg.list_templates()
```

To publish a change, bump the `version`. This guarantees an instance's `template_ref` always resolves
to exactly the definition it was created from.

### Participants (§1.5, D4)

```python
reg.register_participant(participant)
reg.get_participant("proposer")
reg.list_participants(discoverable_only=True)   # discovery exposes only discoverable participants
```

### Instances — instantiate, list, restore

```python
inst = reg.instantiate(template_ref, owner="@alice", visibility=Visibility.PUBLIC)
reg.get_instance(inst.instance_id)              # == restore(): full replay
reg.list_instances(caller="@alice")             # visibility-filtered (see below)
reg.restore(inst.instance_id)                   # full-replay restore (D3)
```

`instantiate` creates the instance in status `created`, sets the caller as **owner**, and seats the
owner at the `own` tier.

## Access control (§1.6, D5)

Each instance has one **owner** and per-participant **tiers**:

```
own ⊃ speak ⊃ observe
```

- `own` — manage access & visibility, invite, assign/revoke tiers, terminate, transfer ownership.
- `speak` — may be cast into a role and contribute messages.
- `observe` — read-only transcript; may open-mic only if the template enables it.

**Visibility** governs joining:

| Visibility | Join rule |
|------------|-----------|
| `public` | anyone may join, admitted as `observe` (or a higher granted tier) |
| `unlisted` | not listed; join by id/link **requires a grant** |
| `private` (default) | invite-only; join **requires a grant** |

```python
# an `own` holder grants a tier; then the grantee may join
reg.grant_access(inst.instance_id, grantor="@alice", participant_id="@bob", tier=AccessTier.SPEAK)
joined = reg.join(inst.instance_id, participant_id="@bob")   # returns the full replay for the joiner
reg.leave(inst.instance_id, participant_id="@bob")
```

`join` triggers a restore so the joiner receives the full history to date (§2.5). `list_instances`
returns only instances that are non-`private`, or that the `caller` owns / has a grant on.

## Authentication (§1.6, D6)

Auth resolves a **bearer token → one `participant_id`** through a pluggable `Authenticator`. Auth
answers *who you are*; tiers answer *what you may do*.

```python
from dcp import Registry, SqlStore, SimpleTokenAuthenticator, AnonymousAuthenticator

# production-style: a token map
auth = SimpleTokenAuthenticator({"tok-alice": "@alice", "tok-bob": "@bob"})
reg = Registry(SqlStore(), authenticator=auth)
reg.authenticate("tok-alice")           # → "@alice"; unknown/missing → AuthError

# local dev: every request is one synthetic participant, no token needed
reg = Registry(SqlStore(), authenticator=AnonymousAuthenticator())
reg.authenticate(None)                  # → "@local"
```

The anonymous dev mode is what keeps the local hello-world key-free.

## Server introspection (§1.11)

Clients discover what a server can do before acting:

```python
info = reg.server_info()
info.dcp_version                        # "0.2.0"
info.capabilities.auto_generate         # bool
[(p.provider, p.configured) for p in info.model_providers]
# [("openai", True), ("anthropic", False), ("mock", True)]
```

`configured` reports whether a credential is present — it never exposes the key itself.

## Auto-generation: query → draft template (§2.2, D10)

Auto-generation is a standalone, model-backed step (not an orchestrator action). Wire a
`TemplateGenerator` into the Registry to enable it:

```python
from dcp import Registry, SqlStore, TemplateGenerator, build_provider
from dcp.provider import orchestrator_binding
from dcp import Config

provider = build_provider(orchestrator_binding(Config.from_env()))
reg = Registry(SqlStore(), generator=TemplateGenerator(provider))

draft = await reg.generate_template("A debate between an optimist and a skeptic about a plan.")
# `draft` is an unregistered DialogueTemplate — review/edit, then:
reg.register_template(draft)
```

Without a generator, `generate_template` raises a capability error and the HTTP endpoint returns
`501`. The pipeline is always *query → draft → (edit) → register → instantiate → run* — the draft is
reviewable by default.

## Delivery: HTTP + SSE (§3.5)

The semantic core never depends on a transport. `build_app(registry)` exposes the Registry as a
Starlette REST + Server-Sent-Events app:

```python
from dcp import Registry, SqlStore, build_app
import uvicorn

app = build_app(Registry(SqlStore("sqlite:///./dcp.db")))
uvicorn.run(app, host="127.0.0.1", port=8000)
```

| Method & path | Operation |
|---------------|-----------|
| `GET /` | server info + capabilities + providers |
| `POST /templates` · `GET /templates` | register · list |
| `GET /templates/{id}/versions/{version}` | fetch one version |
| `POST /templates/generate` | draft from a query (501 if not enabled) |
| `POST /participants` · `GET /participants` · `GET /participants/{id}` | register · list · fetch |
| `POST /instances` | instantiate `{template_id, version, owner, visibility?}` |
| `GET /instances` | list (visibility-filtered via `?caller=`) |
| `GET /instances/{id}` | full replay (+ `resumable`) |
| `POST /instances/{id}/join` · `.../leave` | join `{participant_id}` · leave |
| `GET /instances/{id}/events` | **SSE**: replay history, then tail live (`?tail=false` for a finite stream) |

Errors map to HTTP: `409` (immutability conflict), `403` (access denied), `404` (unknown),
`422` (bad body), `501` (capability not enabled).

### SSE: replay-then-tail (D3)

A subscriber to `GET /instances/{id}/events` first receives every event already in the log, in order,
then continues receiving new events as they are appended — the same one-mechanism restore that serves
orchestrator resume and late joiners. Pass `?tail=false` to get a finite stream that ends once caught
up (used in tests).

## Running a dialogue: the `Server` facade

`Server` wires a store, a registry, and providers behind one object, and adds a `run`/resume entry
point that builds the orchestrator for you:

```python
from dcp import Server

server = Server(database_url="sqlite:///./dcp.db")   # reads Config.from_env() for providers
server.register_template(template)
server.register_participant(participant)
server.instantiate(template_ref, owner="@alice", instance_id="run-1")

result = await server.run(
    "run-1",
    cast={"proposer": "proposer", "founder": "@alice"},   # role_id → participant_id
    human_gateway=my_gateway,                             # for human roles
)
```

`Server.run` derives each agent's provider from its `model_binding` (else the orchestrator default
from the environment), and **resumes** automatically if the instance is already partway through.
Pass `orchestrator_provider` / `agent_providers` to override (e.g. `MockProvider` for tests).
