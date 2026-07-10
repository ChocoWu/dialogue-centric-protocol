# DCP — Dialogue-centric Protocol

A standalone protocol **and** reference Python SDK for **human–agent multi-agent dialogue**: many
participants (agents *and* real people) take turns in a shared, replayable conversation that a
central **orchestrator** both *drives* (who speaks next) and *oversees* (verifying each turn before
and after it happens).

DCP is not built on MCP / A2A / ACP / ANP — it is derived ground-up from its own design. The
behavioral contract is [`../SPEC.md`](../SPEC.md); the Pydantic models in `dcp.schema` are the
authoritative machine-readable definition.

> **Status:** `0.2.0.dev0` — Phase 4 complete (full SDK: schema · DB-backed event log · participation ·
> model providers · orchestration with real oversight · registry/hosting · HTTP+SSE · facade · conformance).
> Docs & release hardening in progress. The API is pre-1.0 and may change.

---

## Why DCP

- **Humans are first-class participants**, not an afterthought — required inputs, optional enrichment,
  approval gates, and open-mic, each with timeout policies.
- **The orchestrator has real oversight.** Every turn is verified *before* (speaker readiness) and
  *after* (output quality); failing checks trigger recovery (inject context, ask a human, wait on a
  gate, pick an alternative) or routing (revise, verify, escalate, stop) — not just logging.
- **The event log is the source of truth.** An instance's state is a deterministic replay of its
  append-only `messages + events`, so any dialogue is auditable, resumable, and joinable mid-flight.
- **Server-hosted & multi-user.** Templates and participants are registered; instances are
  addressable, access-controlled (owner + `own`/`speak`/`observe` tiers + visibility), and joinable.
- **Batteries included, swappable at every edge.** Model providers (OpenAI / Anthropic / mock), the
  store (SQLite / Postgres), and delivery (HTTP + SSE) all sit behind interfaces.

## Install

```bash
pip install -e ".[dev]"      # from sdk/ ; requires Python ≥ 3.11
```

Runtime deps: `pydantic>=2`, `openai`, `anthropic`, `sqlalchemy>=2`, `starlette`, `uvicorn`,
`sse-starlette`. Postgres: `pip install -e ".[postgres]"`.

## 60-second hello-world (no API key)

```python
import asyncio
from dcp import Server, schema as s
from dcp.orchestration import HumanReply, ScriptedHumanGateway
from dcp.provider import MockProvider

TEMPLATE = s.DialogueTemplate(
    template_id="design-review", version="1.0.0", title="Product-name design review",
    goal="Agree on a product name the founder approves.",
    termination_policy=s.TerminationPolicy(condition="founder approves", max_turns=6),
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
    server.instantiate(s.TemplateRef(template_id="design-review", version="1.0.0"),
                       owner="founder", instance_id="demo")

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

Runnable copies live in [`docs/examples/`](docs/examples/): `hello_dialogue_mock.py` (above, key-free)
and `hello_dialogue.py` (same dialogue driven by a real model via `.env`).

## Docs

| Doc | What |
|-----|------|
| [docs/quickstart.md](docs/quickstart.md) | install → mock hello-world → real model → HTTP server |
| [docs/concepts.md](docs/concepts.md) | the entity model, five layers, lifecycle, oversight/control loop |
| [docs/guide-hosting.md](docs/guide-hosting.md) | `Server`, `Registry`, auth, HTTP+SSE, discovery, auto-generation |
| [docs/api-reference.md](docs/api-reference.md) | the curated public surface |
| [../SPEC.md](../SPEC.md) | the normative specification |

## Development

```bash
./scripts/check          # ruff + mypy --strict + pytest (the single CI gate)
python scripts/gen_schema.py   # regenerate JSON Schemas from the Pydantic source of truth
```

## Configuration

Copy `.env.example` → `.env`. Environment variables (names are stable):

| Var | Meaning | Default |
|-----|---------|---------|
| `DCP_MODEL_PROVIDER` | `openai` \| `anthropic` \| `mock` | `openai` |
| `DCP_MODEL` | model id for the orchestrator / global default | — |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | provider credentials (resolved by provider, never stored in a binding) | — |
| `DCP_DATABASE_URL` | SQLAlchemy URL | `sqlite:///./dcp.db` |

Each agent participant may carry its own `model_binding` independent of the orchestrator's default,
so one dialogue may mix providers/models.

## License

Not yet chosen — to be selected before public release. Until then, all rights reserved.
