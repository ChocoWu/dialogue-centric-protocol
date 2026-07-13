# Quickstart

From zero to a running, overseen, multi-participant dialogue — first with no credentials, then with a real model, then over HTTP. Every snippet here is exercised by the test suite or the [`examples/`](examples/) scripts.

## 1. Install (Python ≥ 3.11)

Run everything from the repository root; the package lives in `sdk/`. 
Pick whichever environment manager you use — both install the same editable package.

**venv + pip**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e "./sdk[dev]"
```

**conda / miniforge**

```bash
conda create -n dcp python=3.11 -y && conda activate dcp
pip install -e "./sdk[dev]"          # dcp is a pip package; install it into the conda env with pip
```

> DCP ships on PyPI-style packaging (there is no conda-forge package yet), so inside a conda env you
> still install it with `pip`. Everything else — the `dcp` CLI, extras like `./sdk[transformers]`,
> the tests — works identically.

Verify (either way):

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

That run exercised the whole stack with **no API key**: a registered template, three participants (two agents + one human), an instance, orchestrated turns, an approval gate, and a terminal status — all persisted to an in-memory SQLite event log and replayed into the final `DialogueInstance`.

### Reading the result — five words

| Word | Meaning |
|------|---------|
| **template** | The reusable *pattern* — roles, flow, generic goal/termination. You register it once. |
| **instance** | One *run* of a template, aimed at a task (its own `goal`/`termination`/`brief`). `status: done` etc. describe an instance. |
| **turn** | One contribution to the transcript. `turns: 3` means three participants spoke. |
| **status** | How the instance ended: `done` (goal met, no open gate) · `provisional` (a waited human timed out) · `stopped` (turn cap hit) · `budget` (token cap) · `error`. Priority: `error > budget > stopped > provisional > done`. |
| **orchestrator** | The non-participant that drives *who speaks* and *whether each turn is OK*. Not shown in the transcript, but it ran every turn. |

Full model in [02 · Design Overview](02-design-overview.md); the template/instance split in
[03 · Templates & Instances](03-dialogue-template.md).

### The shape of a DCP program

1. **Author a template** — the reusable dialogue definition: roles, how each role responds (`required` / `optional` / `gate`), termination policy, orchestration mode (`plan` or `flow`).
2. **Register** the template and the participants with a `Server`.
3. **Instantiate** — create a runtime `DialogueInstance` from the template; the caller is its owner.
4. **Run** — hand the orchestrator a `cast` (role → participant) and the model providers; it drives and oversees the dialogue to a terminal status (`done` / `provisional` / `stopped` / `budget` / `error`).

See [02-design-overview.md](02-design-overview.md) for the full model.

## 3. Run it with a real model

`docs/examples/hello_dialogue.py` is the same dialogue, but the orchestrator and agents use a live provider (the founder's approval stays scripted so it's non-interactive). The example reads a local `.env` from the working directory (or your shell environment); copy the template and fill it in:

```bash
cp sdk/.env.example .env         # then edit .env
# DCP_MODEL_PROVIDER=openai      # or anthropic
# OPENAI_API_KEY=sk-...          # ANTHROPIC_API_KEY for anthropic
# DCP_MODEL=gpt-5.4              # the model id for that provider
```

```bash
python docs/examples/hello_dialogue.py
```

Now the orchestrator's model decides who speaks and when to stop (plan mode), and each agent's model writes its own contribution. 
Nothing else in your code changes — just drop the scripted `MockProvider`s and the `Server` builds real providers from the environment.

### Run it on an open / local model

You don't need a hosted API. Two provider options run open-weights models:

- **`local`** — talk to any **OpenAI-compatible server** (vLLM, Ollama, LM Studio, …). Point at it with `DCP_BASE_URL`; no key needed. No extra install.

  ```bash
  DCP_MODEL_PROVIDER=local DCP_BASE_URL=http://localhost:11434/v1 DCP_MODEL=llama3.1
  ```

- **`transformers`** — load and run the model **inside the Python process** with HuggingFace `transformers` + `torch` (e.g. **Qwen3**). No server, no API, no key — but it needs the extra:

  ```bash
  pip install -e "./sdk[transformers]"
  # then: DCP_MODEL_PROVIDER=transformers DCP_MODEL=Qwen/Qwen3-4B
  ```

See the [api reference](09-api-reference.md#model-providers) for `LocalProvider` /
`TransformersProvider` if you'd rather construct them directly.

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

See [06-hosting-delivery.md](06-hosting-delivery.md) for auth, access tiers, visibility, and auto-generation.

## 5. The `dcp` command line

Installing the package puts a `dcp` command on your `PATH` — a quick way to introspect a server, the preset catalog, and installed plugins without writing any code.

```bash
dcp --version                      # 0.2.0.dev0
dcp info                           # version, capabilities, configured providers, plugins
dcp presets                        # the built-in template catalog
dcp plugins                        # components contributed by installed packages
dcp serve --db sqlite:///./dcp.db  # run the HTTP + SSE server (host/port flags too)
```

`dcp info` reads your environment, so it doubles as a config check — it shows which providers are configured (an API key present, `DCP_BASE_URL` set, or the `transformers` extra installed):

```
model providers:
  openai       not configured
  anthropic    not configured
  local        not configured
  transformers not configured
  mock         configured
```

And once a dialogue has run, replay its transcript straight from the database — add `--timeline` to interleave the control decisions and oversight verdicts:

```bash
dcp show <instance-id> --db sqlite:///./dcp.db --timeline
```

## Next steps

**Read next**, in order:
- [02 · Design Overview](02-design-overview.md) — the whole map: entities, five layers, the runtime flow, the content-vs-structure split.
- [03 · Templates & Instances](03-dialogue-template.md) — the pattern vs. the run, field by field; presets; per-run `goal`/`termination`/`brief`.
- [04 · Orchestrator](04-orchestrator.md) — the turn loop, control policies, oversight.
- [05 · Participant](05-participant.md) — humans and agents; the provider taxonomy and per-agent model binding.

**Then by task:**
- [06 · Hosting & Delivery](06-hosting-delivery.md) — multi-user hosting: registration, joining, access control, auth, HTTP/SSE, the CLI, deployment.
- [07 · Extending & Sharing](07-extending-sharing.md) — distribute a policy/agent/template as a plugin or a portable local/remote component.
- [08 · Evaluation](08-evaluation.md) — benchmark orchestrators and oversight policies.
- [Walkthrough: a Research Companion](walkthrough-research-companion.md) — a full flagship MAS, end to end.
- [09 · API Reference](09-api-reference.md) · [10 · Troubleshooting](10-troubleshooting.md) · [`../SPEC.md`](../SPEC.md) — the public API, the FAQ, and the normative spec.
