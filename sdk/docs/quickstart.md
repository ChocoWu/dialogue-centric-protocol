# Quickstart

From zero to a running, overseen, multi-participant dialogue — first with no credentials, then with
a real model, then over HTTP. Every snippet here is exercised by the test suite or the
[`examples/`](examples/) scripts.

## 1. Install (Python ≥ 3.11)

```bash
cd sdk
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Verify:

```bash
python -c "import dcp; print(dcp.__version__, dcp.PROTOCOL_VERSION)"
# 0.2.0.dev0 0.2.0
```

## 2. First success — the key-free hello-world

```bash
python docs/examples/hello_dialogue_mock.py
```

Expected output:

```
configured providers: ['mock']

status: done  (turns: 3)
  proposer: I propose 'Northstar'.
  critic: 'Northstar' is clear and low trademark risk. +1.
  founder: Approved — ship it.
```

That run exercised the whole stack with **no API key**: a registered template, three participants
(two agents + one human), an instance, orchestrated turns, an approval gate, and a terminal status —
all persisted to an in-memory SQLite event log and replayed into the final `DialogueInstance`.

### The shape of a DCP program

1. **Author a template** — the reusable dialogue definition: roles, how each role responds
   (`required` / `optional` / `gate`), termination policy, orchestration mode (`plan` or `flow`).
2. **Register** the template and the participants with a `Server`.
3. **Instantiate** — create a runtime `DialogueInstance` from the template; the caller is its owner.
4. **Run** — hand the orchestrator a `cast` (role → participant) and the model providers; it drives
   and oversees the dialogue to a terminal status (`done` / `provisional` / `stopped` / `budget` /
   `error`).

See [concepts.md](concepts.md) for the full model.

## 3. Run it with a real model

`docs/examples/hello_dialogue.py` is the same dialogue, but the orchestrator and agents use a live
provider (the founder's approval stays scripted so it's non-interactive). Configure a provider in a
local `.env` (copy `.env.example`):

```bash
DCP_MODEL_PROVIDER=openai        # or anthropic
OPENAI_API_KEY=sk-...            # ANTHROPIC_API_KEY for anthropic
DCP_MODEL=gpt-5.4                # the model id for that provider
```

```bash
python docs/examples/hello_dialogue.py
```

Now the orchestrator's model decides who speaks and when to stop (plan mode), and each agent's model
writes its own contribution. Nothing else in your code changes — just drop the scripted
`MockProvider`s and the `Server` builds real providers from the environment.

Discover what a server can do at runtime:

```python
from dcp import Server
info = Server().server_info()
print(info.dcp_version)
for p in info.model_providers:
    print(p.provider, "configured" if p.configured else "no key")
```

## 4. Serve it over HTTP + SSE

The same `Registry` can be exposed as a REST + Server-Sent-Events API (Starlette/uvicorn):

```python
from dcp import Registry, SqlStore, build_app
import uvicorn

app = build_app(Registry(SqlStore("sqlite:///./dcp.db")))
uvicorn.run(app, host="127.0.0.1", port=8000)
```

Then, from any client:

```
GET  /                                     → server info + capabilities + providers
POST /templates                            → register a template
POST /participants                         → register a participant
POST /instances                            → instantiate  {template_id, version, owner}
GET  /instances                            → list instances (visibility-filtered)
GET  /instances/{id}                       → full replay (+ resumable hint)
POST /instances/{id}/join                  → join  {participant_id}
GET  /instances/{id}/events                → SSE stream: replay history, then tail live
POST /templates/generate                   → draft a template from a query (if enabled)
```

See [guide-hosting.md](guide-hosting.md) for auth, access tiers, visibility, and auto-generation.

## Next steps

- [concepts.md](concepts.md) — templates vs instances, roles vs participants, the five layers, and
  how the orchestrator's oversight loop drives control.
- [guide-hosting.md](guide-hosting.md) — multi-user hosting: registration, joining, access control,
  bearer auth, HTTP/SSE, and query→template auto-generation.
- [api-reference.md](api-reference.md) — the curated public API.
- [`../SPEC.md`](../SPEC.md) — the normative behavior (every acceptance criterion has a conformance test).
