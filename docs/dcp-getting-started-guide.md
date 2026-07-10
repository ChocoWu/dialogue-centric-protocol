# DCP Getting Started Guide

## Overview

DCP, the Dialogue-centric Protocol, is a standalone protocol for human-agent multi-agent
dialogues. Its core idea is that a dialogue is not just a chat transcript: it is a governed,
replayable process with roles, participants, access tiers, orchestration decisions, human
intervention points, verification records, messages, events, and terminal outcomes.

The Python package in `sdk/` is the reference SDK for DCP. It currently provides the protocol
schema, append-only state replay, role casting and access-tier helpers, model-provider interfaces,
and a deterministic orchestration loop that can be tested with `MockProvider`.

Current status:

- Package name: `dcp`
- Python version: `>=3.11`
- Protocol version: `0.2.0`
- Package version: `0.2.0.dev0`
- Runtime status: development SDK, not yet a polished end-to-end user release
- Main contract: `SPEC.md`
- Machine-readable contract: Pydantic models in `sdk/src/dcp/schema/`

The SDK is intentionally independent of MCP, A2A, ACP, ANP, and agents-json. Those protocols are
used only as engineering references for how mature protocols are documented and shipped; DCP does
not inherit their schema, lifecycle, wire format, or compatibility model.

## Current DCP Architecture

DCP is organized around a layered runtime model. The current SDK implements the semantic core and
keeps I/O behind explicit interfaces so the protocol behavior remains testable and replayable.

### 1. Schema Layer

Location: `sdk/src/dcp/schema/`

The schema layer defines the protocol's public data model using Pydantic v2. These models are the
authoritative machine-readable contract for the SDK.

Core entities:

- `DialogueTemplate`: reusable dialogue definition with roles, goal, termination policy, optional
  flow, and orchestration settings.
- `DialogueInstance`: a concrete running dialogue created from a template.
- `Role`: dialogue-local identity such as `critic`, `founder`, or `planner`.
- `Participant`: persistent server-level identity, either `agent` or `human`.
- `Message`: immutable transcript contribution.
- `Event`: immutable process record used for audit, replay, and restore.

Important value objects and records:

- `ModelBinding`: provider/model pair for an orchestrator or agent participant.
- `TerminationPolicy`: stop condition, max turns, or token budget.
- `AccessGrant`, `RosterEntry`, `Gate`, `PendingInput`: access and human-intervention state.
- `PreActionVerification`, `PostActionVerification`: structured oversight records.
- `RolesCast`: audit record for role-to-participant assignment.

Enums define protocol states and controlled value spaces, including:

- `InstanceStatus`
- `TerminationStatus`
- `RoleKind`
- `ResponseRequirement`
- `AccessTier`
- `Visibility`
- `OrchestrationMode`
- `EventType`

### 2. State Layer

Location: `sdk/src/dcp/state/`

The state layer follows an append-only event-log model. Runtime state is derived by replaying
ordered `Message` and `Event` records, rather than by trusting mutable in-memory state.

Main pieces:

- `Store`: persistence protocol for instances, log records, and participants.
- `SqlStore`: SQLAlchemy-backed implementation. SQLite is used for local development and tests;
  Postgres support is planned through the package extra.
- `InstanceHeader`: immutable instance metadata that is not derived from the log.
- `restore(store, instance_id)`: rebuilds a `DialogueInstance` from persisted records.
- `replay(header, records)`: deterministic reducer from log records to instance state.

This gives DCP three useful properties:

- Auditability: every meaningful change is recorded as an event or message.
- Replayability: an instance can be reconstructed from its log.
- Late join support: the same restore path can replay prior state for a participant joining later.

### 3. Participation Layer

Location: `sdk/src/dcp/participation/`

The participation layer binds template roles to registered participants and enforces access-tier
rules.

Role casting follows this precedence:

1. Explicit role binding.
2. `role_id` matching a registered `participant_id`.
3. Capability/persona overlap.
4. Fallback to the first available participant of the right kind.

Access tiers are ordered as:

```text
own > speak > observe
```

Only participants with at least `speak` can be cast into speaking roles. `observe` participants can
read but cannot contribute or be cast into dialogue roles.

### 4. Provider Layer

Location: `sdk/src/dcp/provider/`

All model calls pass through the provider-neutral `ModelProvider` protocol:

- `text(...)`: free-text model output for agent contributions.
- `structured(...)`: model output validated into a Pydantic schema for orchestration and oversight.

Current provider implementations:

- `MockProvider`: deterministic, key-free provider for tests and examples.
- `OpenAIProvider`: OpenAI-backed provider selected with `DCP_MODEL_PROVIDER=openai`.
- `AnthropicProvider`: Anthropic-backed provider selected with `DCP_MODEL_PROVIDER=anthropic`.

Provider selection is done per `ModelBinding`, not as a global singleton. This means the
orchestrator can use one provider/model while individual agent participants use their own
`model_binding`.

### 5. Orchestration Layer

Location: `sdk/src/dcp/orchestration/`

The orchestration layer drives a serialized dialogue turn loop:

1. Start the instance.
2. Record role casting and participant joins.
3. Decide the next speaker.
4. Emit pre-action verification.
5. Collect an agent or human contribution.
6. Emit post-action verification.
7. Repeat until a terminal condition is reached.

The current `Orchestrator` supports:

- Plan mode: a model-backed structured decision selects the next role or stops the dialogue.
- Flow mode: a declared role graph determines the next role.
- Agent contributions through `ModelProvider`.
- Human roles through `HumanGateway`.
- Human gates and timeouts.
- Open-mic pending inputs.
- Termination priorities: `error > budget > stopped > provisional > done`.

Delivery, registry, authentication, and HTTP/SSE hosting are planned in later milestones. The
semantic core is already structured so those pieces can sit at the edges without changing the
protocol data model.

## Protocol SDK

### Install for Local Development

From the repository root:

```bash
cd sdk
python3.13 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
```

Run the SDK checks:

```bash
./.venv/bin/pytest
./.venv/bin/ruff check .
./.venv/bin/mypy
```

Or use the project check script:

```bash
./scripts/check
```

### Configure Providers

The SDK reads configuration from environment variables:

```bash
DCP_MODEL_PROVIDER=mock
DCP_MODEL=mock
DCP_DATABASE_URL=sqlite:///./dcp.db
```

For real providers:

```bash
DCP_MODEL_PROVIDER=openai
DCP_MODEL=<openai-model-id>
OPENAI_API_KEY=<your-key>
```

or:

```bash
DCP_MODEL_PROVIDER=anthropic
DCP_MODEL=<anthropic-model-id>
ANTHROPIC_API_KEY=<your-key>
```

Use `mock` for key-free local tests and deterministic examples.

### Create a Template

```python
from dcp import schema as s

template = s.DialogueTemplate(
    template_id="product-review",
    version="1.0.0",
    title="Product Review",
    topic="Evaluate a proposed product idea",
    goal="Produce a concise recommendation",
    termination_policy=s.TerminationPolicy(
        condition="recommendation produced",
        max_turns=4,
    ),
    roles=[
        s.Role(
            role_id="critic",
            name="Technical Critic",
            kind=s.RoleKind.AGENT,
            persona="Identify technical risks and implementation tradeoffs.",
            response_requirement=s.ResponseRequirement.REQUIRED,
        ),
        s.Role(
            role_id="founder",
            name="Founder",
            kind=s.RoleKind.HUMAN,
            response_requirement=s.ResponseRequirement.GATE,
            human_policy=s.HumanPolicy(wait_window_seconds=60),
        ),
    ],
)
```

### Register Participants and Cast Roles

```python
from dcp import schema as s
from dcp.participation import cast_roles

participants = [
    s.Participant(
        participant_id="agent.critic",
        kind=s.RoleKind.AGENT,
        display_name="Technical Critic",
        profile="Technical risk analysis and architecture review",
        discoverable=True,
        model_binding=s.ModelBinding(provider="mock", model="mock"),
    ),
    s.Participant(
        participant_id="@founder",
        kind=s.RoleKind.HUMAN,
        display_name="Founder",
    ),
]

roles_cast = cast_roles(
    template=template,
    participants=participants,
    instance_id="dlg_1",
)

cast = {entry.role_id: entry.participant_id for entry in roles_cast.roles}
```

### Create an Instance Store

```python
from datetime import UTC, datetime

from dcp import PROTOCOL_VERSION, schema as s
from dcp.state import InstanceHeader, SqlStore

store = SqlStore("sqlite:///:memory:")
store.create_instance(
    InstanceHeader(
        instance_id="dlg_1",
        template_ref=s.TemplateRef(template_id=template.template_id, version=template.version),
        owner="@founder",
        visibility=s.Visibility.PRIVATE,
        dcp_version=PROTOCOL_VERSION,
        created_at=datetime.now(UTC),
    )
)
```

### Run a Mock Dialogue

```python
from dcp.orchestration import HumanReply, Orchestrator, ScriptedHumanGateway
from dcp.provider import MockProvider

participant_map = {p.participant_id: p for p in participants}

orchestrator = Orchestrator(
    store=store,
    template=template,
    instance_id="dlg_1",
    cast=cast,
    participants=participant_map,
    provider=MockProvider(
        structured_queue=[
            {"action": "select_speaker", "target_role_id": "critic"},
            {"action": "select_speaker", "target_role_id": "founder"},
            {"action": "stop", "status": "done", "reason": "review complete"},
        ]
    ),
    agent_providers={
        "agent.critic": MockProvider(
            texts=["The main risk is orchestration reliability; add replay tests early."]
        )
    },
    human_gateway=ScriptedHumanGateway(
        {
            "founder": HumanReply(
                content="Approved. Proceed with the replay-first design.",
                decision="approve",
            )
        }
    ),
)

instance = await orchestrator.run()

print(instance.status)
for message in instance.messages:
    print(f"{message.role_id}: {message.content}")
```

Because the orchestration API is async, run the example inside an async function:

```python
import asyncio

asyncio.run(main())
```

### Restore an Instance

Every run appends records to the store. To rebuild the current state:

```python
from dcp.state import restore

restored = restore(store, "dlg_1")
assert restored == instance
```

Restore is the normal path for audit, recovery, and late join replay.

### Generate JSON Schema

The SDK can generate JSON Schema artifacts from the Pydantic models:

```bash
cd sdk
./.venv/bin/python scripts/gen_schema.py
```

Generated schemas are written under:

```text
sdk/schema/generated/
```

### What Is Ready vs. Planned

Ready in the current SDK:

- Pydantic schema models for core DCP entities.
- JSON Schema generation.
- SQLAlchemy-backed append-only store.
- Deterministic replay and restore.
- Role casting.
- Access-tier checks.
- Provider-neutral model interface.
- Mock, OpenAI, and Anthropic provider modules.
- Async orchestration loop with mock-testable behavior.
- Human gateway abstraction and scripted human replies.
- Pre/post-action oversight records.

Planned but not yet the main user path:

- Registry and hosting facade.
- Authenticator implementations.
- HTTP API and SSE delivery.
- Packaged hello-world examples under docs.
- Conformance suite covering the full protocol.
- Polished release/onboarding documentation.

### Suggested First Success Path

For a new contributor, the best first success path is:

1. Install the SDK in editable mode.
2. Run `./scripts/check`.
3. Create a `DialogueTemplate`.
4. Create `Participant` objects.
5. Cast roles with `cast_roles`.
6. Create an `InstanceHeader` in `SqlStore`.
7. Run `Orchestrator` with `MockProvider`.
8. Call `restore` and inspect `messages`, `events`, `status`, and `turn`.

That path exercises the current protocol core without requiring API keys, network calls, or the
future delivery layer.
