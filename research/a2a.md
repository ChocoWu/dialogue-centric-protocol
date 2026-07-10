# Reference Analysis: Agent2Agent Protocol (A2A)

> **Purpose (per CLAUDE.md §0):** This is an *engineering-methodology* study — "how was A2A
> made, implemented, and shipped?" — **not** a design source. Nothing about A2A's semantics
> (AgentCard, Task/TaskState lifecycle, skills, protocol bindings, JSON-RPC/gRPC/REST) should
> enter DCP's `SPEC.md`. DCP is dialogue-centric, not task-delegation-centric; A2A's object
> model is explicitly *not* to be inherited. The takeaways in the final section are strictly
> about **method** (how the spec is authored, how schemas are organized, how the SDK is built,
> how users are onboarded).

**Primary sources consulted (fetched 2026-07-09, not from memory):**
- Spec site (rendered): `https://a2a-protocol.org/latest/specification/` and `https://a2a-protocol.org/latest/`
- Spec repo: `https://github.com/a2aproject/A2A` (top-level tree, `specification/`, `docs/`)
- **Normative proto (verbatim):** `https://raw.githubusercontent.com/a2aproject/A2A/main/specification/a2a.proto`
- v1 change notes: `https://github.com/a2aproject/A2A/blob/main/docs/whats-new-v1.md`
- Python SDK: `https://github.com/a2aproject/a2a-python` (README + `src/a2a/` tree)
- Hello-world sample (verbatim): `https://raw.githubusercontent.com/a2aproject/a2a-samples/main/samples/python/agents/helloworld/{__main__.py,agent_executor.py,test_client.py,README.md}`

---

## Snapshot
- **Maintainer / governance:** Originated at Google (announced 2025), now an open-source project
  **under the Linux Foundation**, contributed by Google (spec repo `README`/`GOVERNANCE.md`).
  The governance apparatus is fully materialized in-repo: `GOVERNANCE.md`, `MAINTAINERS.md`,
  `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CONTRIBUTING.md`, and an `adrs/` directory of
  Architecture Decision Records. The Linux-Foundation lineage is even encoded in the proto
  package name: `package lf.a2a.v1;`.
- **License:** Apache License 2.0.
- **Maturity / versioning:** Spec at **`1.0`** (repo release **v1.0.1**, dated 2026-05-28), with
  a compatibility mode for the prior **`0.3`** line. Versions are **`Major.Minor`** (semver-ish,
  patch excluded from compat decisions) — a different discipline from MCP's date-string
  revisions. This is a protocol that already survived a **major redesign** (0.x → 1.0) in which
  the normative schema technology itself was swapped (see §A).
- **What it solves (context only):** A standard for *opaque, independently-built agents* to
  discover one another (via an **AgentCard**) and delegate/track units of work (**Tasks**) across
  organizational boundaries, over multiple wire protocols. Its self-framing: peer agent-to-agent
  interoperability, positioned as complementary to MCP (spec Appendix B, "Relationship to MCP").

---

## A. How the spec is authored  *(answers user Q1)*

- **One large normative document + one normative schema file.** Unlike MCP's per-page site, the
  A2A human-readable spec is a **single comprehensive document** (`a2a-protocol.org/latest/specification/`,
  sourced from `docs/specification.md`) organized into **14 numbered sections plus appendices**.
  The proto file is cited *by* the prose as the machine-readable authority.
- **Document structure (verbatim TOC).** Section numbering is explicit and deeply nested:
  ```
  1. Introduction (1.1 Key Goals · 1.2 Guiding Principles · 1.3 Specification Structure · 1.4 Normative Content)
  2. Terminology (2.1 Requirements Language · 2.2 Core Concepts)
  3. A2A Protocol Operations (3.1 Core Operations · … · 3.6 Versioning · 3.7 Messages and Artifacts)
  4. Protocol Data Model (4.1 Core Objects · 4.2 Streaming Events · … · 4.6 Extensions)
  5. Protocol Binding Requirements and Interoperability
  6. Common Workflows & Examples
  7. Authentication and Authorization
  8. Agent Discovery: The Agent Card
  9. JSON-RPC Protocol Binding
  10. gRPC Protocol Binding
  11. HTTP+JSON/REST Protocol Binding
  12. Custom Binding Guidelines
  13. Security Considerations
  14. IANA Considerations
  Appendix A: Migration & Legacy Compatibility
  Appendix B: Relationship to MCP (Model Context Protocol)
  ```
  The ordering encodes the **three-layer architecture**: *abstract data model & operations first*
  (§3–4), *concrete wire bindings last* (§9–12). The spec states this explicitly:
  > "Layer 1: Canonical Data Model defines the core data structures … Layer 2: Abstract
  > Operations describes the fundamental capabilities … Layer 3: Protocol Bindings provides
  > concrete mappings of the abstract operations and data structures to specific protocol
  > bindings."
- **Normative language.** Formal RFC 2119 boilerplate is declared once in §2.1:
  > "The keywords 'MUST', 'MUST NOT', 'REQUIRED', 'SHALL', 'SHALL NOT', 'SHOULD', 'SHOULD NOT',
  > 'RECOMMENDED', 'MAY', and 'OPTIONAL' in this document are to be interpreted as described in
  > RFC 2119."

  and MUST/SHOULD then appear throughout (e.g. versioning §3.6: "Clients **MUST** send the
  `A2A-Version` header with each request").
- **Normative vs. informative split is stated, not just implied.** §1.4 ("Normative Content")
  designates the authority precisely:
  > "In addition to the protocol requirements defined in this document, the file `spec/a2a.proto`
  > is the single authoritative normative definition of all protocol data objects and
  > request/response messages."

  Prose defines *behavior* and requirements; the proto defines *shapes*; generated JSON is
  informative. §6 ("Common Workflows & Examples") is a dedicated informative section, keeping
  worked examples out of the normative operation text.
- **Versioning management.** `Major.Minor` (e.g. `1.0`); patch versions do not affect protocol
  compatibility. Two negotiation levers: a per-interface `protocol_version` on each `AgentInterface`
  (an agent can expose several versions simultaneously), and a request-level `A2A-Version` header
  ("Server validates and rejects if unsupported"; empty is interpreted as `0.3`). A `CHANGELOG.md`
  and a dedicated `docs/whats-new-v1.md` narrate the 0.x→1.0 migration.

---

## B. How schemas & core objects are defined  *(answers user Q1 schema + Q2)*

- **Schema technology: Protocol Buffers (proto3), single normative file.** The source of truth is
  `specification/a2a.proto` (`package lf.a2a.v1`). This is a **deliberate reversal**: `docs/whats-new-v1.md`
  frames v1.0's central move as
  > "Elevate a2a.proto from being a gRPC-specific implementation file to the universal, normative
  > source of truth."

  A `spec/a2a.json` (JSON Schema) is produced *at build time and not committed* — non-normative.
  All SDK bindings "MUST be regenerated from the proto … rather than edited manually." So A2A and
  MCP land on the *same meta-strategy* (one hand-written schema is canonical, everything else is
  generated) but pick different technologies (Protobuf vs TypeScript).
- **Schema tooling = Buf + Google API linter.** The `specification/` dir ships
  `buf.yaml`, `buf.gen.yaml`, `buf.lock`, and `.api-linter.yaml` — i.e. codegen and lint are
  wired into the schema itself, and the proto imports Google's AIP annotations
  (`google/api/field_behavior.proto`, `google/api/annotations.proto`). Requiredness is expressed
  as an annotation, not proto's native `required`: `[(google.api.field_behavior) = REQUIRED]`.
- **Organization:** one flat `a2a.proto` grouped by ordering and comment banners (data objects,
  then enums, then security schemes), **not** one-file-per-entity. Every message and field carries
  a `//` doc comment — the proto *is* the field-level reference (same discipline as MCP's JSDoc).
- **Core-object definition style — 3 real verbatim examples.**

  *(1) The lifecycle is an explicit `enum`* (contrast MCP, which has no state field — its lifecycle
  is procedural). A2A stores state as a first-class typed value:
  ```protobuf
  // Defines the possible lifecycle states of a `Task`.
  enum TaskState {
    // The task is in an unknown or indeterminate state.
    TASK_STATE_UNSPECIFIED = 0;
    // Indicates that a task has been successfully submitted and acknowledged.
    TASK_STATE_SUBMITTED = 1;
    // Indicates that a task is actively being processed by the agent.
    TASK_STATE_WORKING = 2;
    // Indicates that a task has finished successfully. This is a terminal state.
    TASK_STATE_COMPLETED = 3;
    // Indicates that a task has finished with an error. This is a terminal state.
    TASK_STATE_FAILED = 4;
    // Indicates that a task was canceled before completion. This is a terminal state.
    TASK_STATE_CANCELED = 5;
    // Indicates that the agent requires additional user input to proceed.
    // This is an interrupted state.
    TASK_STATE_INPUT_REQUIRED = 6;
    // Indicates that the agent has decided to not perform the task.
    // This may be done during initial task creation or later once an agent
    // has determined it can't or won't proceed. This is a terminal state.
    TASK_STATE_REJECTED = 7;
    // Indicates that authentication is required to proceed. This is an interrupted state.
    TASK_STATE_AUTH_REQUIRED = 8;
  }
  ```
  Note the comments **classify each state** (terminal / interrupted) inline — the taxonomy lives
  in the schema doc-comment, not only in prose.

  *(2) `Task` — a stateful aggregate* carrying status + history + outputs:
  ```protobuf
  // `Task` is the core unit of action for A2A. It has a current status
  // and when results are created for the task they are stored in the
  // artifact. If there are multiple turns for a task, these are stored in
  // history.
  message Task {
    // Unique identifier (e.g. UUID) for the task, generated by the server
    // for a new task.
    string id = 1 [(google.api.field_behavior) = REQUIRED];
    // Unique identifier (e.g. UUID) for the contextual collection of
    // interactions (tasks and messages).
    string context_id = 2;
    // The current status of a `Task`, including `state` and a `message`.
    TaskStatus status = 3 [(google.api.field_behavior) = REQUIRED];
    // A set of output artifacts for a `Task`.
    repeated Artifact artifacts = 4;
    // The history of interactions from a `Task`.
    repeated Message history = 5;
    // A key/value object to store custom metadata about a task.
    google.protobuf.Struct metadata = 6;
  }
  ```

  *(3) `AgentCard` — the discovery manifest*, showing the "declare capabilities + interfaces +
  skills + security" pattern and the `// Next ID: 20` field-evolution convention (trimmed to the
  representative head; all fields carry `field_behavior` annotations verbatim):
  ```protobuf
  // A self-describing manifest for an agent. It provides essential
  // metadata including the agent's identity, capabilities, skills, supported
  // communication methods, and security requirements.
  // Next ID: 20
  message AgentCard {
    // A human readable name for the agent.  Example: "Recipe Agent"
    string name = 1 [(google.api.field_behavior) = REQUIRED];
    string description = 2 [(google.api.field_behavior) = REQUIRED];
    // Ordered list of supported interfaces. The first entry is preferred.
    repeated AgentInterface supported_interfaces = 3
        [(google.api.field_behavior) = REQUIRED];
    AgentProvider provider = 4;
    string version = 5 [(google.api.field_behavior) = REQUIRED];
    optional string documentation_url = 6;
    AgentCapabilities capabilities = 7 [(google.api.field_behavior) = REQUIRED];
    map<string, SecurityScheme> security_schemes = 8;
    repeated SecurityRequirement security_requirements = 9;
    repeated string default_input_modes = 10 [(google.api.field_behavior) = REQUIRED];
    repeated string default_output_modes = 11 [(google.api.field_behavior) = REQUIRED];
    repeated AgentSkill skills = 12 [(google.api.field_behavior) = REQUIRED];
    repeated AgentCardSignature signatures = 13;
    optional string icon_url = 14;
  }
  ```
- **Extensibility mechanism:** three explicit, *declared-and-negotiated* hatches (not implicit
  open maps everywhere): (a) `google.protobuf.Struct metadata` on most objects; (b) a formal
  `AgentExtension { uri, description, required, params }` mechanism advertised inside
  `AgentCapabilities.extensions`, plus `repeated string extensions` (extension URIs) on `Message`
  and `Artifact`; (c) `AgentInterface.protocol_binding` is deliberately an "open form string … to
  be easily extended for other protocol bindings," with a dedicated §12 "Custom Binding Guidelines".
  Content polymorphism uses a proto `oneof` (`Part { oneof content { text | raw | url | data } }`)
  rather than a tagged union of interfaces.

---

## C. How the SDK implements the spec  *(answers user Q3)*

- **Package:** distribution `a2a-sdk`, import root `a2a` (repo `a2aproject/a2a-python`). Ships
  `py.typed`. **Python 3.10+.**
- **Repo layout (`src/a2a/`)** — organized by *role and concern*, not by wire protocol:
  ```
  src/a2a/
    __init__.py   _base.py   py.typed
    types/        # generated + hand-wrapped protocol models (from a2a.proto)
    client/       # A2ACardResolver, create_client, ClientConfig
    server/       # request_handlers, routes, tasks, agent_execution, events
    auth/         # security schemes / credentials
    extensions/   # the AgentExtension mechanism
    helpers/      # new_text_message, new_task_from_user_message, new_text_part, get_message_text …
    compat/       # 0.3 compatibility mode
    utils/
    migrations/   # Alembic DB migrations (alembic.ini)  + a2a_db_cli.py
  ```
  Notable: the SDK is heavier than MCP's — it bundles **persistence** (Alembic migrations, a DB
  CLI, `[postgresql]/[mysql]/[sqlite]` extras) and an explicit **`compat/`** module for the prior
  spec version. Compatibility is a first-class package concern, not an afterthought.
- **Core abstraction: an interface to *subclass*, not a decorator to *sugar*.** The user implements
  `AgentExecutor` (abstract base) with `execute(context, event_queue)` and `cancel(...)`, and wires
  it into a `DefaultRequestHandler` alongside a `TaskStore`. State is advanced *imperatively* by
  emitting events through a `TaskUpdater` / `EventQueue`. This is a materially different ergonomic
  from MCP's `@mcp.tool()` — A2A exposes the task/event machinery to the developer rather than
  hiding it. (See the verbatim executor in §D.)
- **Type system.** `a2a.types` are Pydantic models mirroring the proto (snake_case fields:
  `default_input_modes`, `context_id`, `input_modes`). Because the proto is normative and Buf-generated,
  the Python types are a *derived binding* kept in sync with the schema rather than
  independently authored — same "generate from canonical schema" discipline as MCP, different
  toolchain (Buf/proto → Pydantic vs TS → Pydantic).
- **Transport decoupling.** The same `AgentExecutor`/`DefaultRequestHandler` is served over any of
  three bindings by choosing a route factory: `create_jsonrpc_routes`, plus gRPC / `HTTP+JSON`
  variants (the sample comments: *"Alternatively, you can choose GRPC or HTTP_JSON as protocol
  bindings"*). Routes mount onto any ASGI app (Starlette or FastAPI) served by uvicorn. The web
  framework and the wire binding are both pluggable at the edge; the executor core is unaware of
  either. README: "compatibility mode for `0.3` … Both versions support JSON-RPC, HTTP+JSON/REST,
  and gRPC transports."
- **Async + testing.** Async-first (`async def execute`, `async for chunk in client.send_message`).
  Testability shown in the sample's `test_client.py`, which uses a pytest fixture to `subprocess`-launch
  the server and drive it — an end-to-end style rather than an in-memory transport.
- **API surface.** Broader and lower-level than MCP's facade: a first-time user touches ~10
  symbols (`AgentSkill`, `AgentCard`, `AgentCapabilities`, `AgentInterface`, `AgentExecutor`,
  `RequestContext`, `EventQueue`, `TaskUpdater`, `DefaultRequestHandler`, `InMemoryTaskStore`,
  route factories) before hello-world runs. Convenience is pushed into `helpers/`
  (`new_text_message`, `new_task_from_user_message`, `new_text_part`) rather than into a single
  high-level server object.

---

## D. What hello-world looks like  *(answers user Q4)*

A2A's smallest working example is **two files** (an executor + a server bootstrap) — there is no
one-object, six-line equivalent to MCP's `@mcp.tool()` demo. Both files verbatim from the
`helloworld` sample:

**`agent_executor.py` (the agent logic — verbatim):**
```python
from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState


class HelloWorldAgent:
    """Hello World Agent."""

    async def invoke(self, user_request: str) -> str:
        """Invoke the Hello World agent to generate a response."""
        return f'Hello, World! I have received your request ({user_request})'


class HelloWorldAgentExecutor(AgentExecutor):
    """Test AgentProxy Implementation."""

    def __init__(self) -> None:
        self.agent = HelloWorldAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Process user request."""
        # 1. Collect a task from request context
        if context.current_task:
            task = context.current_task
        else:
            # 1.1 If there is no task, create one and add it event queue
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        # 2. Update task status in EventQueue using TaskUpdater class object
        task_updater = TaskUpdater(
            event_queue=event_queue, task_id=task.id, context_id=task.context_id
        )
        await task_updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message('Processing request...'),
        )

        # 3. Collect user request from request content and invoke LLM agent to generate content
        query = get_message_text(context.message)
        if query:
            result = await self.agent.invoke(user_request=query)
        else:
            result = 'No text input is provided!'

        # 4. Add generated response as an artifact to EventQueue
        await task_updater.add_artifact(parts=[new_text_part(text=result, media_type='text/plain')])
        print('Result: ', result)

        # 5. Update task status to completed
        await task_updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message('Request is completed!'),
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Raise exception as cancel is not supported."""
        raise NotImplementedError('Cancel is not supported.')
```

**`__main__.py` (the server bootstrap — verbatim, comment scaffolding retained):**
```python
import uvicorn

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
)
from agent_executor import (
    HelloWorldAgentExecutor,  # type: ignore[import-untyped]
)
from starlette.applications import Starlette


if __name__ == '__main__':
    skill = AgentSkill(
        id='echo_bot',
        name='Echo Bot',
        description='An example agent that acknowledges client request and responds with a "Hello World" message.',
        input_modes=['text/plain'],
        output_modes=['text/plain'],
        tags=['a2a', 'echo-example'],
        examples=['hi', 'how are you'],
    )

    public_agent_card = AgentCard(
        name='Hello World Agent',
        description='Just a hello world agent',
        version='0.0.1',
        default_input_modes=['text/plain'],
        default_output_modes=['text/plain'],
        capabilities=AgentCapabilities(streaming=True, extended_agent_card=True),
        supported_interfaces=[
            AgentInterface(
                protocol_binding='JSONRPC',
                url='http://127.0.0.1:9999',
                protocol_version='1.0',
            )
        ],
        skills=[skill],
    )

    request_handler = DefaultRequestHandler(
        agent_executor=HelloWorldAgentExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=public_agent_card,
    )

    routes = []
    routes.extend(create_agent_card_routes(public_agent_card))
    routes.extend(create_jsonrpc_routes(request_handler, '/'))

    app = Starlette(routes=routes)
    uvicorn.run(app, host='127.0.0.1', port=9999)
```
*(The real sample additionally builds an `extended_agent_card`; omitted above as non-essential to
first success. Everything shown is verbatim.)*

- **Concept count to first success:** high — roughly **10–12 concepts** (`AgentSkill`, `AgentCard`,
  `AgentCapabilities`, `AgentInterface`, subclassing `AgentExecutor`, `RequestContext`,
  `EventQueue`, `TaskUpdater`, `TaskState`, `DefaultRequestHandler`, `InMemoryTaskStore`, route
  factories, plus an ASGI app + uvicorn). **~40 lines** of executor + **~30 lines** of bootstrap
  before anything runs. Contrast MCP (~6 lines, ~3 concepts). The developer must manually manage
  the task state machine (create task → WORKING → add artifact → COMPLETED).
- **Install / run (verbatim, from the sample `README.md`):**
  ```bash
  python -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```
  ```bash
  python __main__.py
  ```
  In a separate terminal:
  ```bash
  source .venv/bin/activate
  python test_client.py
  ```
  SDK install (from the `a2a-python` README, verbatim): `uv add a2a-sdk` or `pip install a2a-sdk`,
  with extras `[http-server] [fastapi] [grpc] [telemetry] [encryption] [postgresql] [mysql]
  [sqlite] [sql] [all]` (e.g. `pip install "a2a-sdk[all]"`).
- **Prereqs:** Python 3.10+, `uv` or `pip`; an ASGI server (uvicorn) and an ASGI framework
  (Starlette/FastAPI); there is **no bundled inspector GUI** — first feedback is a CLI client
  hitting `127.0.0.1:9999`, or the separate `hosts/cli` demo (`uv run . --agent http://127.0.0.1:9999`).

---

## E. Adoption path — what got it used  *(answers user Q5)*

- **Docs site structure.** `a2a-protocol.org` separates seven top-level areas: **Home ·
  Documentation** (conceptual guides: "What is A2A?", agent discovery, enterprise/multi-tenancy)
  **· Extensions · Specification** (the single normative doc) **· Resources** (SDKs + tutorials)
  **· Community** (roadmap, partners) **· Blog** (release notes). The clean split of *conceptual
  guide ≠ normative spec ≠ SDK reference ≠ tutorial* mirrors MCP's three-surface approach.
- **Quickstart design.** A dedicated **Python quickstart** walks a fixed ladder: *Introduction →
  Setup → Agent Skills & Agent Card → Agent Executor → Start Server → Interact with Server →
  Streaming & Multiturn → Next Steps*. Each doc step maps to one region of the sample code (the
  sample files even carry `--8<-- [start:AgentCard]` / `[start:RequestHandler]` markers so the
  docs can **snippet-include exact source ranges** — docs and runnable code cannot drift). This
  is a strong method signal: *the tutorial text transcludes the real sample file, not a copy.*
- **Time-to-first-success is longer than MCP's** by construction: multiple concepts and a
  two-terminal (server + client) loop before output, and no visual inspector.
- **Examples / ecosystem.** A **separate `a2a-samples` repo** holds runnable agents (`helloworld`,
  framework integrations) and host clients (`hosts/cli`) — samples are versioned independently of
  both spec and SDK. First-party SDKs exist across languages; the Python SDK ships to PyPI as
  `a2a-sdk`.
- **What drove adoption:** (1) heavyweight institutional backing — **Google origin + Linux
  Foundation stewardship** with a large launch partner roster, giving enterprises governance
  confidence; (2) **multi-transport from day one** (JSON-RPC + gRPC + REST) so it fit existing
  infra rather than dictating one; (3) explicit **complementary positioning to MCP** (spec
  Appendix B) that avoided a turf fight and let both be adopted together; (4) external training
  (a DeepLearning.AI short course) drove developer funnel. **Friction that remains:** a *heavy*
  hello-world (task state machine, ASGI wiring, ~10 concepts) raises the on-ramp; a **0.x→1.0
  redesign that changed the normative schema technology** (JSON-Schema-era → protobuf-normative)
  forced a `compat/` module and a whole `whats-new-v1` migration guide — real churn cost, though
  managed transparently.

---

## Methodology takeaways (for Phase 2 / DCP — *method only, no A2A semantics*)

1. **Pick the canonical schema technology once, early, and don't change it later.** A2A's biggest
   self-inflicted cost was migrating its *normative source* from JSON-Schema-era artifacts to
   protobuf at 1.0, forcing a `compat/` module and a migration guide. → DCP: commit to **Pydantic
   v2 as the single canonical source** (already chosen in CLAUDE.md §3) *before* any spec text is
   frozen, and generate JSON Schema + docs from it — never plan to swap the source-of-truth tech
   post-1.0.
2. **State the normative hierarchy in the spec itself, in a numbered "Normative Content" clause.**
   A2A §1.4 names exactly which file is authoritative and declares generated artifacts
   non-normative. → DCP: add a short SPEC.md section that says "the Pydantic models in
   `src/dcp/schema/` are authoritative; rendered JSON Schema and field tables are generated and
   informative," so there is never ambiguity about which representation wins.
3. **Order the spec abstract-model-first, wire-binding-last, and keep bindings pluggable behind an
   interface.** A2A's Layer-1/2/3 structure (data model & operations §3–4, concrete bindings §9–12)
   let it serve three transports off one schema. → DCP: structure SPEC.md as *dialogue/state model
   → orchestration operations → delivery bindings*, and keep the Delivery layer (SPEC §3.4) an
   adapter interface so HTTP/SSE/WebSocket are appendices, not the core.
4. **Transclude real sample source into the tutorial with snippet markers, don't paste copies.**
   A2A's docs `--8<--` include exact line-ranges from the runnable `helloworld` files, so quickstart
   and working code cannot silently diverge. → DCP: mark up the canonical hello-world example and
   have the quickstart include those exact ranges, so docs stay correct as the SDK evolves.
5. **Watch the concept-count of hello-world — it is an adoption tax.** A2A's ~10-concept, two-file,
   manual-state-machine first example is markedly heavier than MCP's ~6 lines, and that friction is
   visible. → DCP: budget an explicit *concepts-to-first-success* target (aim MCP-low, not A2A-high),
   and hide the state machine/transport behind a facade so the newcomer writes intent, not plumbing.
6. **Materialize governance and versioning discipline in-repo from the start.** A2A ships
   `GOVERNANCE.md`, `MAINTAINERS.md`, an `adrs/` decision-record trail, `Major.Minor` versioning,
   a `CHANGELOG`, and a `whats-new` migration doc — the process is legible, which builds adopter
   trust even across a major redesign. → DCP: keep the STATUS.md Decision Log as our ADR trail,
   fix the version scheme before v1, and write migration notes for any breaking change — treat the
   *process artifacts* as part of the deliverable, not overhead.
