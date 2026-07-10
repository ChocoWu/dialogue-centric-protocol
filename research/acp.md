# Reference Analysis: Agent Communication Protocol (ACP)

> **Purpose (per CLAUDE.md §0):** This is an *engineering-methodology* study — "how was ACP
> made, implemented, and shipped?" — **not** a design source. Nothing about ACP's semantics
> (REST `/runs` endpoints, `Message`/`MessagePart`, the run status enum, `await`/resume, agent
> manifests, sessions) should enter DCP's `SPEC.md`. DCP does **not** adopt ACP's design. The
> takeaways in the final section are strictly about **method** — how the spec is authored, how
> schemas are organized, how the SDK is structured, how docs onboard users.

**Primary sources consulted (fetched 2026-07-09, verified live, not from memory):**
- Spec site (Mintlify docs): `https://agentcommunicationprotocol.dev/introduction/welcome`
- Quickstart: `https://agentcommunicationprotocol.dev/introduction/quickstart`
- Core concepts: `.../core-concepts/agent-manifest`, `.../core-concepts/message-structure`,
  `.../core-concepts/agent-run-lifecycle`
- GitHub repo (canonical): `https://github.com/i-am-bee/acp` (README raw:
  `https://raw.githubusercontent.com/i-am-bee/acp/main/README.md`)
- **Normative OpenAPI contract:** `https://raw.githubusercontent.com/i-am-bee/acp/main/docs/spec/openapi.yaml`
  (OpenAPI `3.1.1`, `info.version: 0.2.0`)
- Python SDK tree: `github.com/i-am-bee/acp/tree/main/python/src/acp_sdk` (via GitHub API,
  `git/trees/main?recursive=1`); `pyproject.toml` (`acp-sdk` `version = "1.0.3"`)
- Governance move: `https://github.com/orgs/i-am-bee/discussions/5` ("ACP Joins Forces with A2A
  Under the Linux Foundation")

---

## Snapshot
- **Maintainer / governance:** Created by **IBM Research / the BeeAI team** (launched March 2025),
  developed in the open under the **`i-am-bee`** GitHub org. BeeAI (with ACP) was **donated to
  the Linux Foundation**; version headers now read `Copyright 2025 © BeeAI a Series of LF
  Projects, LLC`. **Governance status as of 2026: ACP has been merged into A2A** — the repo README
  and docs both state *"ACP is now part of A2A under the Linux Foundation!"* with a migration
  guide. So ACP is effectively a **superseded / archived** protocol whose reference
  implementation continues but whose forward path is A2A. (Relevant to us as a *method* case
  study and as a cautionary governance/consolidation story, not as a living design.)
- **License:** **Apache 2.0** (repo, SDK, and OpenAPI `info.license`).
- **Maturity / versioning:** Two independent version lines — the **protocol/OpenAPI spec is
  `0.2.0`** (semver, pre-1.0), while the **`acp-sdk` PyPI package is `1.0.3`** (semver). This
  divergence (spec 0.x, SDK 1.x) is itself a finding.
- **What it solves (context only):** A **REST/HTTP-native** standard for agents, apps, and humans
  to invoke and coordinate each other. Contrast with MCP: MCP is **JSON-RPC 2.0** over pluggable
  transports; ACP is *"a standardized RESTful API"* — plain `POST /runs`, `GET /runs/{id}`, JSON
  bodies, ordinary HTTP status — deliberately usable with `curl` and no special client. (This
  contrast is a *design* difference we note only to characterize the reference; DCP inherits
  neither.)

---

## A. How the spec is authored

- **The spec IS an OpenAPI document; the docs site renders it.** Unlike MCP (prose site +
  TypeScript `schema.ts` as source of truth), ACP's normative contract is a single
  **`docs/spec/openapi.yaml`** (`openapi: 3.1.1`) living *inside the docs folder of the main
  repo*. The human-readable reference pages are thin **`.mdx` wrappers generated per operation**
  that point at that YAML. The `docs/spec/` tree is literally:
  ```
  docs/spec/openapi.yaml        # the normative contract
  docs/spec/openapi.mdx         # rendered reference entry
  docs/spec/agents-list.mdx     docs/spec/agents-get.mdx    docs/spec/agents-manifest.mdx
  docs/spec/run-create.mdx      docs/spec/run-get.mdx       docs/spec/run-resume.mdx
  docs/spec/run-cancel.mdx      docs/spec/run-get-events.mdx
  docs/spec/ping.mdx            docs/spec/sessions-get.mdx
  ```
  → **One machine-readable file is the source of truth; the reference docs are a projection of
  it, one page per operation.** This is the same *principle* as MCP (schema-first, docs derive),
  achieved with OpenAPI instead of hand-written TS.
- **Document structure = OpenAPI's built-in structure.** Top of `openapi.yaml`:
  ```yaml
  openapi: 3.1.1
  info:
    title: ACP - Agent Communication Protocol
    description: >-
      The Agent Communication Protocol (ACP) provides a standardized RESTful API for managing,
      orchestrating, and executing AI agents. It supports synchronous, asynchronous, and streamed
      agent interactions, with both stateless and stateful execution modes.
    license:
      name: Apache 2.0
      url: https://www.apache.org/licenses/LICENSE-2.0.html
    version: 0.2.0
  externalDocs:
    description: Comprehensive documentation for ACP
    url: https://agentcommunicationprotocol.dev
  servers:
    - url: http://localhost:8000
  tags:
    - name: agent
      description: Operations for listing, describing, and managing agent definitions and metadata.
    - name: run
      description: Operations for creating, managing, controlling, and monitoring agent runs...
  ```
  Endpoints are grouped by **`tags`** (`agent`, `run`); every operation has an **`operationId`**
  (`listAgents`, `getAgent`, `createRun`, `getRun`, `resumeRun`, `cancelRun`, `listRunEvents`,
  `getSession`, `ping`). Reusable types live under **`components/schemas`**. There is **no
  RFC-2119 MUST/SHOULD prose layer** — normativity is expressed *structurally* (required fields,
  enums, `$ref`s, HTTP status codes), which is a much lighter authoring model than MCP's prose +
  schema pairing.
- **Conceptual prose lives separately from the contract.** The `core-concepts/*` pages
  (agent-manifest, message-structure, agent-run-lifecycle) explain semantics narratively and even
  paste **Python `pydantic` class bodies** as the reference definition (see §B) — so the site mixes
  "OpenAPI schema" and "Python model" as two views of the same objects.
- **Versioning management:** the OpenAPI `info.version` (`0.2.0`) is the protocol version; it is a
  **plain semver string**, not MCP's dated-revision folders. There is no evidence of frozen dated
  spec snapshots; the spec evolves in-place in the repo. This is lighter but less auditable than
  MCP's per-date frozen pages.

---

## B. How schemas & core objects are defined  *(2–3 real verbatim examples)*

- **Schema technology: OpenAPI 3.1 `components/schemas` (JSON-Schema dialect) as the wire
  contract, mirrored by Pydantic v2 models in the SDK.** OpenAPI 3.1.1 uses the 2020-12 JSON
  Schema vocabulary, so the schemas are ordinary JSON Schema with `$ref`, `enum`, `required`,
  `pattern`, `format`. Objects are defined **once in the YAML** and **again as Pydantic classes**
  in `acp_sdk/models/` (`models.py`, `schemas.py`, `types.py`, `common.py`). The docs pages quote
  the **Pydantic** form as the human reference.

- **Example 1 — `Message` / `MessagePart` (the core content object), as the docs present it
  (Pydantic, verbatim):**
  ```python
  class MessagePart(BaseModel):
      name: Optional[str] = None
      content_type: str
      content: Optional[str] = None
      content_encoding: Optional[Literal["plain", "base64"]] = "plain"
      content_url: Optional[AnyUrl] = None
      metadata: Optional[CitationMetadata | TrajectoryMetadata] = None

  class Message(BaseModel):
      role: Literal["user"] | Literal["agent"] | str
      parts: list[MessagePart]
  ```
  with the constraint *"Parts must provide either `content` or `content_url` (not both)"* stated in
  prose (not enforceable purely in the schema). Wire example (verbatim JSON from the docs):
  ```json
  {
    "role": "user",
    "parts": [{
      "content_type": "text/plain",
      "content": "Hello, world!"
    }]
  }
  ```

- **Example 2 — `Run` and its status enum (the lifecycle object), verbatim from `openapi.yaml`:**
  ```yaml
  RunStatus:
    type: string
    enum:
      - created
      - in-progress
      - awaiting
      - cancelling
      - cancelled
      - completed
      - failed
    description: Status of the run
  RunMode:
    type: string
    enum: [sync, async, stream]
    description: Mode of the request
  Run:
    type: object
    properties:
      agent_name:   { $ref: "#/components/schemas/AgentName" }
      session_id:   { $ref: "#/components/schemas/SessionId" }
      run_id:       { $ref: "#/components/schemas/RunId" }
      status:       { $ref: "#/components/schemas/RunStatus" }
      await_request:
        $ref: "#/components/schemas/AwaitRequest"
        nullable: true
      output:
        type: array
        items: { $ref: "#/components/schemas/Message" }
      error:
        $ref: "#/components/schemas/Error"
        nullable: true
      created_at:  { type: string, format: date-time }
      finished_at: { type: string, format: date-time }
    required:
      - agent_name
      - run_id
      - status
      - output
      - created_at
  ```
  **Definition style is an explicit `status` enum field** (a stored state machine), the *opposite*
  of MCP's procedural, field-less lifecycle. State names are the same seven the docs describe:
  `created → in-progress → {completed | failed | awaiting}`, `awaiting → in-progress`, and
  `* → cancelling → cancelled`. (Design contrast only; DCP re-derives its own lifecycle.)

- **Example 3 — `AgentManifest` (the discovery/identity object), verbatim from `openapi.yaml`:**
  ```yaml
  AgentName:
    type: string
    pattern: "^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"
    minLength: 1
    maxLength: 63
    description: A unique identifier for the agent following the RFC 1123 DNS label naming convention.
    example: chat
  AgentManifest:
    type: object
    properties:
      name:        { $ref: "#/components/schemas/AgentName" }
      description:
        type: string
        description: Human-readable description of the agent.
      input_content_types:
        type: array
        minItems: 1
        description: List of supported MIME content types for input Messages...
        items: { type: string, examples: ["*/*", image/*, text/plain, application/json, image/png] }
      output_content_types:
        type: array
        minItems: 1
        items: { type: string, examples: ["*/*", image/*, text/plain, application/json, image/png] }
      metadata: { $ref: "#/components/schemas/Metadata" }
      status:   { $ref: "#/components/schemas/Status" }
    required:
      - name
      - description
      - input_content_types
      - output_content_types
  ```
  Note the **`status` sub-object is system-provided runtime telemetry** (`avg_run_tokens`,
  `avg_run_time_seconds`, `success_rate` 0–100), i.e. the manifest carries live operational
  metrics, not just static identity.

- **Extensibility mechanism:** open **`metadata`** objects on manifests and typed metadata on
  message parts (`CitationMetadata | TrajectoryMetadata`); MIME `*/*` wildcards for content-type
  negotiation; and — because it is plain REST — the usual "add fields, tolerate unknown ones"
  posture. There is **no formal capability-negotiation handshake** like MCP's `initialize`; content
  compatibility is declared via `input/output_content_types` and defaults to `["*/*"]`.

---

## C. How the SDK implements the spec

- **Repo layout — `python/src/acp_sdk/` mirrors the MCP split (client / server / shared /
  models):** verified tree:
  ```
  acp_sdk/
    __init__.py   version.py   instrumentation.py   py.typed
    client/    __init__.py  client.py  types.py  utils.py
    models/    __init__.py  models.py  schemas.py  types.py  common.py  errors.py  platform.py
    server/    __init__.py  server.py  app.py  agent.py  context.py  executor.py
               resources.py  errors.py  logging.py  telemetry.py  types.py  utils.py
               store/  (store.py  memory_store.py  postgresql_store.py  redis_store.py  utils.py)
    shared/    __init__.py  resources.py
  ```
  → **spec-mirroring layout**: `models/` = the schemas (Pydantic mirror of `openapi.yaml`),
  `server/` = host that serves the REST API, `client/` = consumer, `shared/` = common resource
  handling. Ships **`py.typed`** (typed package), same as MCP.
- **Core abstraction: a decorator-registered async generator over FastAPI.** `server/app.py`
  imports directly from **FastAPI** (`from fastapi import Depends, FastAPI, HTTPException, ...`;
  `create_app(...) -> FastAPI`) — the REST surface is **not hand-rolled**, it is a FastAPI app, so
  the OpenAPI-defined endpoints (`/runs`, `/agents`, …) are FastAPI routes. Users never see FastAPI:
  they get a `Server` facade and an `@server.agent()` decorator.
- **The public server surface is tiny** — from `server/__init__.py` (verbatim exports):
  `Server`, `agent`, `create_app`, `Context`, `AgentManifest`, `RunYield`, `RunYieldResume`,
  `MemoryStore`/`RedisStore`/`PostgreSQLStore`/`Store`. So the first-touch types are
  **`Server`, `@server.agent()`, `Message`, `Context`** — four names.
- **Agents are async generators, not request handlers.** The programming model: an agent is an
  `async def` that takes `input: list[Message]` and **`yield`s** `RunYield` values; yielding a
  `Message` emits output, yielding a dict (e.g. `{"thought": ...}`) emits a trajectory/event, and
  the framework maps `yield`/resume onto the run's `sync|async|stream` modes and the
  `awaiting`/resume lifecycle. This is how one function body serves all three `RunMode`s.
- **Sync vs async:** SDK is **async-first** (`async def`, `AsyncGenerator`, async `Client`
  context manager), matching the streaming/await lifecycle. Pluggable **state stores**
  (`memory`/`redis`/`postgresql` behind a `Store` interface) isolate persistence — the same
  "I/O at the edges" pattern DCP wants.
- **Spec ↔ code sync:** the SDK **hand-maintains** Pydantic models (`models/models.py`,
  `schemas.py`) alongside `openapi.yaml`; there is a Sphinx `docs/sdks/python/.../rst_source/*.rst`
  set generated from the code. Unlike a strict codegen pipeline, the OpenAPI YAML and the Pydantic
  models are **two hand-kept mirrors** — a divergence risk (and a reason the spec is `0.2.0` while
  the SDK is `1.0.3`).

---

## D. What hello-world looks like  *(verbatim smallest example)*

**Smallest complete agent (verbatim, identical in README and quickstart):**
```python
# agent.py
import asyncio
from collections.abc import AsyncGenerator

from acp_sdk.models import Message
from acp_sdk.server import Context, RunYield, RunYieldResume, Server

server = Server()


@server.agent()
async def echo(
    input: list[Message], context: Context
) -> AsyncGenerator[RunYield, RunYieldResume]:
    """Echoes everything"""
    for message in input:
        await asyncio.sleep(0.5)
        yield {"thought": "I should echo everything"}
        await asyncio.sleep(0.5)
        yield message


server.run()
```

**Install / init (verbatim quickstart):**
```sh
uv init --python '>=3.11' my_acp_project
cd my_acp_project
uv add acp-sdk
```
**Run (verbatim):**
```sh
uv run agent.py
```
**Call it — no SDK needed, plain `curl` (verbatim):**
```sh
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "echo", "input": [{"role": "user", "parts": [{"content": "Howdy!", "content_type": "text/plain"}]}]}'
```
**…or the Python client (verbatim):**
```python
async with Client(base_url="http://localhost:8000") as client:
    run = await client.run_sync(
        agent="echo",
        input=[Message(parts=[MessagePart(content="Howdy!", content_type="text/plain")])]
    )
```

- **Concept count to first success:** ~4 concepts — instantiate `Server()`, decorate an `async def`
  with `@server.agent()`, `yield` a `Message`, `server.run()`. **~10 lines of real code** (a touch
  more than MCP's ~6, mostly the async-generator signature). The function name (`echo`) *becomes*
  the agent's `name`; the docstring *becomes* its `description` — **zero manual manifest authoring**,
  exactly MCP's "types/hints derive the schema" trick applied to the manifest.
- **Prereqs:** Python ≥ 3.11 + `uv` (or pip); nothing else — the win is that the **HTTP endpoint is
  immediately `curl`-able**, so first success needs no client SDK, no GUI inspector, no host app.

---

## E. Adoption path — what got it used (and what stalled it)

- **Docs organization (Mintlify site):** clean separation of **`introduction/` (welcome,
  quickstart)** → **`core-concepts/` (narrative semantics)** → **`spec/` (per-operation OpenAPI
  reference)** → **`sdks/` (Python/TS reference)**. A newcomer reaches a running server from the
  quickstart without reading the OpenAPI reference — same three-surface separation MCP uses.
- **Time-to-first-success is very low** precisely because it is REST: paste ~10 lines, `uv run`,
  then `curl` the endpoint. No inspector tool or reference host is *required* (BeeAI Platform exists
  as one, but the `curl` path stands alone). "It's just HTTP" is the headline adoption argument.
- **Distribution:** `acp-sdk` on **PyPI** (semver, currently `1.0.3`); a TypeScript SDK also exists;
  Apache-2.0. GitHub issue/PR templates, CI (`.github/workflows/main.yml`, `release.yml`) show a
  conventional OSS release pipeline.
- **What drove early adoption:** (1) **REST/OpenAPI familiarity** — any language, any HTTP client,
  instant `curl`; (2) **framework-agnostic** positioning (LangChain/CrewAI/etc. can all expose an
  ACP endpoint); (3) IBM Research backing + BeeAI reference platform; (4) manifest auto-derived from
  the decorated function.
- **What stalled it / friction (the cautionary finding):** ACP was **consolidated into A2A under
  the Linux Foundation** — the README's first line is now *"ACP is now part of A2A!"* with a
  migration guide. Overlapping IBM-adjacent standards (ACP vs A2A) converged, so **an adopter who
  bet on ACP now faces a migration**. Also: the **spec-version (`0.2.0`) vs SDK-version (`1.0.3`)
  mismatch** and the **two hand-kept schema mirrors** (OpenAPI YAML + Pydantic) are latent
  divergence/confusion risks. Net: strong *method*, but a governance/consolidation trajectory that
  is itself the biggest lesson.

---

## Methodology takeaways (for Phase 2 / DCP — *method only, no ACP design semantics*)

1. **Pick ONE machine-readable source of truth and make the reference docs a projection of it —
   but avoid ACP's two-mirror trap.** ACP keeps `openapi.yaml` *and* hand-written Pydantic models,
   which can silently drift (and shows up as spec `0.2.0` vs SDK `1.0.3`). → DCP: author entities
   **once as Pydantic v2 models** (our chosen tech, per CLAUDE.md §3) and **generate** the
   JSON-Schema/reference-doc artifacts from them, so there is exactly one authored surface, never
   two mirrors to reconcile.
2. **Structural normativity (required fields, enums, refs) can carry a lot without heavy MUST/SHOULD
   prose — but keep a thin normative layer for the rules a schema can't express.** ACP encodes
   almost everything in OpenAPI and states cross-field rules ("`content` XOR `content_url`") only in
   prose, unenforced. → DCP: let Pydantic models carry field-level normativity, and reserve `SPEC.md`
   prose for exactly the invariants types can't capture (ordering, XOR constraints, state-transition
   legality) — and make those testable in the pytest acceptance suite.
3. **Derive identity/metadata from code, not hand-authored manifests.** ACP's function name →
   agent `name` and docstring → `description` means hello-world writes zero manifest. → DCP: let the
   registration decorator introspect the Python function (name, signature, docstring) to populate a
   role/participant's descriptor, so users declare behavior, not boilerplate.
4. **Put the ergonomic facade over a boring, standard server core, and keep the first-touch surface
   to ~4 names.** ACP hides FastAPI entirely behind `Server` + `@server.agent()`; its public
   `server/__init__.py` exports a short, curated list. → DCP: build the reference orchestrator on a
   conventional, well-understood server substrate but expose a tiny curated `__init__`, and keep
   persistence behind a pluggable `Store`-style interface (ACP's memory/redis/postgres pattern) so
   the semantic core stays transport/storage-agnostic (SPEC §3.4).
5. **Separate docs into quickstart → concepts → generated reference → SDK reference, and make first
   success require the fewest possible external pieces.** ACP's strongest adoption lever is that
   hello-world is `curl`-able with no client, GUI, or host app. → DCP: ensure the quickstart's first
   success needs only `pip install` + run + one command to observe a dialogue — no mandatory
   companion tool — even if we *also* ship a nicer replay viewer later.
6. **Decide governance and versioning BEFORE promoting adoption — overlapping standards get
   consolidated and strand adopters.** ACP was absorbed into A2A under the Linux Foundation; its
   adopters now face migration, and its dual spec/SDK version lines confuse. → DCP: commit up front
   to a single, clearly-scoped positioning and **one coherent version scheme spanning spec and SDK**
   (or an explicit, documented mapping), and record in `STATUS.md` how we avoid the "two competing
   in-house standards" failure mode ACP fell into.
