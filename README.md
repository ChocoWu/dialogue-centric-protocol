# DCP — Dialogue-centric Protocol

A standalone protocol **and** reference Python SDK for **human–agent multi-agent dialogue**: many participants (agents *and* real people) take turns in a shared, replayable conversation that a central **orchestrator** both *drives* (who speaks next) and *oversees* (verifying each turn before and after it happens).

DCP is not built on MCP / A2A / ACP / ANP — it is derived ground-up from its own design. 
The behavioral contract is [`SPEC.md`](SPEC.md); the Pydantic models in `dcp.schema` are the authoritative machine-readable definition.

> **Status:** `0.2.0.dev0` — full SDK (schema · DB-backed event log · participation · model providers ·
> orchestration with real oversight · registry/hosting · HTTP+SSE) **plus a component ecosystem**:
> package and share orchestrators, oversight, agents, and templates — run them locally or **connect to
> them remotely**. Pre-1.0; the API may change, and a license is not yet chosen (see below).

---

## Why DCP

- **Humans are first-class participants**, not an afterthought — required inputs, optional enrichment, approval gates, and open-mic, each with timeout policies.
- **The orchestrator has real oversight.** Every turn is verified *before* (speaker readiness) and *after* (output quality); failing checks trigger recovery (inject context, ask a human, wait on a gate, pick an alternative) or routing (revise, verify, escalate, stop) — not just logging.
- **The event log is the source of truth.** An instance's state is a deterministic replay of its append-only `messages + events`, so any dialogue is auditable, resumable, and joinable mid-flight.
- **Reusable templates, per-run inputs.** A template is the *pattern* (roles, flow, generic goal/termination); each run aims it at a task by supplying its own `goal`, `termination` policy, and structured `brief` at instantiation — so one "design review" template serves naming, API review, or architecture review, each replayable.
- **Server-hosted & multi-user.** Templates and participants are registered; instances are addressable, access-controlled (owner + `own`/`speak`/`observe` tiers + visibility), and joinable.
- **A component ecosystem.** Orchestrators, oversight policies, agents, and templates are *shareable components* — describe one with a manifest and deliver it as local code, code + an open-weights checkpoint, or a **remote service** others connect to (with digest-verified artifacts and owner-controlled context projection).
- **Batteries included, swappable at every edge.** Model providers (OpenAI / Anthropic / **open-weights, in-process or served** / mock), the store (SQLite / Postgres), and delivery (HTTP + SSE) all sit behind interfaces.

## Install

The package lives in `sdk/`; run from the repository root (Python ≥ 3.11). Use whichever environment manager you prefer — both install the same editable package:

```bash
# venv + pip
python3 -m venv .venv && source .venv/bin/activate
pip install -e "./sdk[dev]"

# — or — conda / miniforge
conda create -n dcp python=3.11 -y && conda activate dcp
pip install -e "./sdk[dev]"        # DCP has no conda-forge package yet; install it with pip
```

Runtime deps: `pydantic>=2`, `openai`, `anthropic`, `sqlalchemy>=2`, `starlette`, `uvicorn`, `sse-starlette`. Postgres: `pip install -e "./sdk[postgres]"`.

## 60-second hello-world (no API key)

```python
import asyncio
from dcp import Server, schema as s
from dcp.orchestration import HumanReply, ScriptedHumanGateway
from dcp.provider import MockProvider

# The template is the reusable *pattern* — generic title/goal/termination, not one task.
TEMPLATE = s.DialogueTemplate(
    template_id="design-review", version="1.0.0", title="Design review",
    goal="Converge on a proposal the designated approver signs off on.",
    termination_policy=s.TerminationPolicy(condition="the approver approves", max_turns=8),
    roles=[
        s.Role(role_id="proposer", name="Proposer", kind=s.RoleKind.AGENT,
               response_requirement=s.ResponseRequirement.REQUIRED),
        s.Role(role_id="critic", name="Critic", kind=s.RoleKind.AGENT,
               response_requirement=s.ResponseRequirement.REQUIRED),
        s.Role(role_id="founder", name="Founder", kind=s.RoleKind.HUMAN,
               response_requirement=s.ResponseRequirement.GATE),
    ],
)

async def main():
    server = Server(database_url="sqlite:///:memory:")
    server.register_template(TEMPLATE)
    for pid, kind in (("proposer", s.RoleKind.AGENT), ("critic", s.RoleKind.AGENT),
                      ("founder", s.RoleKind.HUMAN)):
        server.register_participant(s.Participant(participant_id=pid, kind=kind, display_name=pid))
    # This run aims the generic template at a task: goal + termination override the template's,
    # and brief carries the specifics — all reach the orchestrator and every agent.
    server.instantiate(s.TemplateRef(template_id="design-review", version="1.0.0"),
                       owner="founder", instance_id="demo",
                       goal="Agree on a product name the founder approves.",
                       termination=s.TerminationPolicy(condition="the founder approves", max_turns=6),
                       brief={"product": "a developer-tools startup", "constraints": ["one word"]})

    result = await server.run(
        "demo",
        cast={"proposer": "proposer", "critic": "critic", "founder": "founder"},
        orchestrator_provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "proposer"},
            {"action": "select_speaker", "target_role_id": "critic"},
            {"action": "select_speaker", "target_role_id": "founder"},
            {"action": "stop", "status": "done"},
        ]),
        agent_providers={
            "proposer": MockProvider(texts=["I propose 'Northstar'."]),
            "critic": MockProvider(texts=["'Northstar' is clear and low trademark risk. +1."]),
        },
        human_gateway=ScriptedHumanGateway(
            {"founder": HumanReply(content="Approved — ship it.", decision="approve")}),
    )
    print(result.status.value)
    for m in result.messages:
        print(f"  {m.role_id}: {m.content}")

asyncio.run(main())
```

Runnable copies live in [`docs/examples/`](docs/examples/): `hello_dialogue_mock.py` (above, key-free) and `hello_dialogue.py` (same dialogue driven by a real model via `.env`).

## Docs

**Start at [docs/README.md](docs/README.md)** — a guided path from zero to building your own system. The reading order:

| # | Doc | What |
|---|-----|------|
| 1 | [Quick Start](docs/01-quickstart.md) | install → mock hello-world → real model → HTTP server → CLI |
| 2 | [Design Overview](docs/02-design-overview.md) | the whole map: entities, five layers, runtime flow, content-vs-structure |
| 3 | [Templates & Instances](docs/03-dialogue-template.md) | the reusable pattern vs. the per-run task; fields; presets; lifecycle |
| 4 | [Orchestrator](docs/04-orchestrator.md) | the turn loop, control policies (plan/flow/custom), oversight |
| 5 | [Participant](docs/05-participant.md) | humans and agents; the provider taxonomy; per-agent model binding |
| 6 | [Hosting & Delivery](docs/06-hosting-delivery.md) | multi-user server: registry, access, auth, HTTP+SSE, CLI, deployment |
| 7 | [Extending & Sharing](docs/07-extending-sharing.md) | ship a policy/agent/template as a plugin or local/remote component |
| 8 | [Evaluation](docs/08-evaluation.md) | benchmark orchestrators & oversight policies |
| 9 | [API Reference](docs/09-api-reference.md) | the curated public API + HTTP endpoint table |
| 10 | [Troubleshooting / FAQ](docs/10-troubleshooting.md) | symptom → cause → fix for the common gotchas |

Off the main path: a full [worked example](docs/walkthrough-research-companion.md), the
[components reference](docs/components-reference.md), the normative [SPEC.md](SPEC.md), and the remote
wire [bindings/](bindings/).

## CLI

Installing the package provides a `dcp` command:

```bash
dcp info                       # version, configured providers, capabilities, installed plugins
dcp presets                    # built-in dialogue templates
dcp plugins                    # installed third-party components (entry points)
dcp serve --db sqlite:///./dcp.db --port 8000   # run the HTTP + SSE server
dcp show <instance_id> --timeline               # transcript + control decisions + oversight verdicts

# components (see docs/components-reference.md):
dcp inspect <ref>              # resolve a component; print its side-effect-free plan
dcp install <ref> --yes        # provision it into this environment (pip + artifacts)
dcp connect <ref> --token T    # verify a remote component endpoint and print its descriptor
```

## Development

```bash
cd sdk
./scripts/check                # ruff + mypy --strict + pytest (the single CI gate)
python scripts/gen_schema.py   # regenerate JSON Schemas from the Pydantic source of truth
```

## Configuration

Copy `sdk/.env.example` → `sdk/.env`. Environment variables (names are stable):

| Var | Meaning | Default |
|-----|---------|---------|
| `DCP_MODEL_PROVIDER` | `openai` \| `anthropic` \| `local` \| `transformers` \| `mock` | `openai` |
| `DCP_MODEL` | model id for the orchestrator / global default | — |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | provider credentials (resolved by provider, never stored in a binding) | — |
| `DCP_BASE_URL` | OpenAI-compatible endpoint for the `local` provider (vLLM / Ollama / LM Studio) | — |
| `DCP_DATABASE_URL` | SQLAlchemy URL | `sqlite:///./dcp.db` |

**Open-source models, two ways:**
- **Served** — `DCP_MODEL_PROVIDER=local` + `DCP_BASE_URL` pointing at an OpenAI-compatible server (e.g. `http://localhost:11434/v1` for Ollama). Works with the core install.
- **In-process** — `DCP_MODEL_PROVIDER=transformers` + `DCP_MODEL=Qwen/Qwen3-4B` runs an open-weights model (Qwen3 by default) directly via HuggingFace `transformers`, no server. Install the extra: `pip install -e "./sdk[transformers]"`.

Each agent participant may carry its own `model_binding` independent of the orchestrator's default, so one dialogue may mix providers/models.

## Deployment

For local/dev, `SqlStore` auto-creates its tables (SQLite). For a **production** deployment (Postgres), manage the schema with **Alembic migrations** instead:

```bash
pip install -e "./sdk[postgres,migrations]"
export DCP_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dcp
cd sdk && alembic upgrade head          # create/evolve the schema
```

Then construct the store with `SqlStore(url, create_tables=False)` so it uses the migrated schema. 
CI runs the full gate on SQLite and a separate job against a real Postgres (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## License

Not yet chosen — to be selected before public release. Until then, all rights reserved.
