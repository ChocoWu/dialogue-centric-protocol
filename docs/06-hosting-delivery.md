# Hosting & Delivery

DCP is server-hosted (D2): templates and participants are **registered**, instances are **addressable and joinable** by other users under access control, and the whole thing is reachable over HTTP + SSE. 
This doc covers the Registry & Hosting layer (§3.4), access control, the delivery binding (§3.5), the `dcp` CLI, and deployment.

## The Registry & the Server

`Registry` is one surface over two catalogs (templates + participants) plus the hosting operations, persisted through a `Store`. 
`Server` wraps a store + registry + providers behind one object and adds `run`/resume. 
Use `Server` for the common case; reach for `Registry` directly when you want the catalog without the run machinery.

```python
from dcp import Registry, SqlStore
reg = Registry(SqlStore("sqlite:///./dcp.db"))
```

- **Templates** are immutable per `(id, version)` — re-registering identical content is a no-op; same version with new content is a `RegistryError`. Bump `version` to publish a change. See [03 · Templates & Instances](03-dialogue-template.md).
- **Participants** register once and are cast into roles per run. See
  [05 · Participant](05-participant.md).
- **Instances**:

```python
inst = reg.instantiate(template_ref, owner="@alice", visibility=Visibility.PUBLIC)
reg.get_instance(inst.instance_id)     # == restore(): full replay (D3)
reg.list_instances(caller="@alice")    # visibility-filtered
```

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
reg.grant_access(inst.instance_id, grantor="@alice", participant_id="@bob", tier=AccessTier.SPEAK)
joined = reg.join(inst.instance_id, participant_id="@bob")   # returns the full replay for the joiner
reg.leave(inst.instance_id, participant_id="@bob")
```

`join` triggers a restore so the joiner receives the full history to date (§2.5). 
`list_instances` returns only instances that are non-`private`, or that the `caller` owns / has a grant on.

## Authentication (§1.6, D6)

Auth resolves a **bearer token → one `participant_id`** through a pluggable `Authenticator`. 
Auth answers *who you are*; tiers answer *what you may do*.

```python
from dcp import Registry, SqlStore, SimpleTokenAuthenticator, AnonymousAuthenticator

auth = SimpleTokenAuthenticator({"tok-alice": "@alice", "tok-bob": "@bob"})   # production-style
reg = Registry(SqlStore(), authenticator=auth)
reg.authenticate("tok-alice")           # → "@alice"; unknown/missing → AuthError

reg = Registry(SqlStore(), authenticator=AnonymousAuthenticator())   # local dev: no token needed
reg.authenticate(None)                  # → "@local"
```

The anonymous dev mode is what keeps the local hello-world key-free.

## Server introspection (§1.11)

Clients discover what a server can do before acting; `configured` reports whether a credential is present — it never exposes the key itself:

```python
info = reg.server_info()
info.dcp_version                        # "0.2.0"
info.capabilities.auto_generate         # bool
[(p.provider, p.configured) for p in info.model_providers]
# [("openai", True), ("anthropic", False), ("mock", True)]
```

## Auto-generation: query → draft template (§2.2, D10)

A standalone, model-backed step (not an orchestrator action). 
Wire a `TemplateGenerator` into the Registry to enable it:

```python
from dcp import Registry, SqlStore, TemplateGenerator, build_provider, Config
from dcp.provider import orchestrator_binding

reg = Registry(SqlStore(), generator=TemplateGenerator(
    build_provider(orchestrator_binding(Config.from_env()))))
draft = await reg.generate_template("A debate between an optimist and a skeptic about a plan.")
reg.register_template(draft)            # draft is unregistered — review/edit first
```

Without a generator, `generate_template` raises a capability error and the HTTP endpoint returns `501`. The pipeline is always *query → draft → (edit) → register → instantiate → run*.

## Delivery: HTTP + SSE (§3.5)

The semantic core never depends on a transport. `build_app(registry)` exposes the Registry as a Starlette REST + Server-Sent-Events app:

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
| `POST /instances` | instantiate `{template_id, version, owner, visibility?, goal?, termination_policy?, brief?}` |
| `GET /instances` | list (visibility-filtered via `?caller=`) |
| `GET /instances/{id}` | full replay (+ `resumable`) |
| `POST /instances/{id}/join` · `.../leave` | join `{participant_id}` · leave |
| `GET /instances/{id}/events` | **SSE**: replay history, then tail live (`?tail=false` for a finite stream) |

Errors map to HTTP: `409` (immutability conflict), `403` (access denied), `404` (unknown), `422` (bad body), `501` (capability not enabled).

**SSE: replay-then-tail (D3).** A subscriber to `GET /instances/{id}/events` first receives every event already in the log, in order, then continues receiving new events as they are appended — the same one-mechanism restore that serves orchestrator resume and late joiners. `?tail=false` gives a finite stream that ends once caught up.

## The `dcp` command line

Installing the package puts a `dcp` command on your `PATH` — introspect a server, the preset catalog, and installed plugins without writing code:

```bash
dcp info                       # version, configured providers, capabilities, installed plugins
dcp presets                    # built-in dialogue templates
dcp plugins                    # components contributed by installed packages
dcp serve --db sqlite:///./dcp.db --port 8000   # run the HTTP + SSE server
dcp show <instance_id> --db sqlite:///./dcp.db --timeline   # transcript + control + oversight

# components (see 07-extending-sharing.md):
dcp inspect <ref>              # resolve a component; print its side-effect-free plan
dcp install <ref> --yes        # provision it into this environment (pip + artifacts)
dcp connect <ref> --token T    # verify a remote component endpoint; print its descriptor
```

`dcp info` reads your environment, so it doubles as a config check (which providers are configured).

## Deployment

For local/dev, `SqlStore` auto-creates its tables (SQLite). For a **production** deployment (Postgres), manage the schema with **Alembic migrations** instead:

```bash
pip install -e "./sdk[postgres,migrations]"
export DCP_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dcp
cd sdk && alembic upgrade head          # create/evolve the schema
```

Then construct the store with `SqlStore(url, create_tables=False)` so it uses the migrated schema.

---

**Next:** [07 · Extending & Sharing](07-extending-sharing.md) — package what you build for others. ·
[All docs](README.md)
