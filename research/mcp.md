# Reference Analysis: Model Context Protocol (MCP)

> **Purpose (per CLAUDE.md §0):** This is an *engineering-methodology* study — "how was MCP
> made, implemented, and shipped?" — not a design source. Nothing about MCP's semantics
> (tools/resources/prompts, JSON-RPC, capability negotiation) should enter DCP's `SPEC.md`.
> The takeaways in the final section are strictly about **method**.

**Primary sources consulted (fetched 2026-07-09, not from memory):**
- Spec site: `https://modelcontextprotocol.io/specification/2025-06-18` and `.../basic/lifecycle`
- Latest spec revision: `https://modelcontextprotocol.io/specification/2025-11-25`
- Spec/schema repo: `https://github.com/modelcontextprotocol/modelcontextprotocol` (`schema/` tree)
- Canonical schema: `https://raw.githubusercontent.com/.../schema/2025-06-18/schema.ts`
- Python SDK: `https://github.com/modelcontextprotocol/python-sdk` (README + `src/mcp/`)

---

## Snapshot
- **Maintainer / governance:** Originated at Anthropic (late 2024), now developed as an open
  project under the `modelcontextprotocol` GitHub org with a public spec repo, contributing
  guide, and a versioned revision process. Open-source (MIT-style licensing on repos).
- **Maturity / versioning:** Multiple stable revisions shipped: `2024-11-05`, `2025-03-26`,
  `2025-06-18`, and latest stable **`2025-11-25`**, plus a rolling `draft`. Versions are
  **date strings**, not semver.
- **What it solves (context only):** A standardized way for LLM "host" applications to connect
  to external tools/data via "servers," using JSON-RPC 2.0 over pluggable transports. Analogy
  it uses for itself: "LSP, but for AI context/tools."

---

## A. How the spec is authored  *(answers user Q1)*

- **Site + repo split.** Human-readable spec is a documentation site
  (`modelcontextprotocol.io/specification/<version>`); the normative machine-readable contract
  is `schema.ts` in the spec repo. The site page states outright: *"This specification defines
  the authoritative protocol requirements, based on the TypeScript schema in schema.ts."* →
  **schema is the source of truth; prose references it.**
- **Document structure.** The spec is split into a small, stable set of top-level areas, each
  its own page (card-linked from the version index):
  `Architecture` · `Base Protocol` (`basic/…`: lifecycle, transports, utilities) ·
  `Server Features` (`server/…`: resources, prompts, tools) ·
  `Client Features` (`client/…`: sampling, roots, elicitation) · `Contributing`.
  Sub-utilities (ping, cancellation, progress, logging, completion) live under `basic/utilities`
  and `server/utilities`. Section numbering is toggled on via a page directive.
- **Normative language.** Formal RFC 2119 / BCP 14 boilerplate is stated once at the top:
  *"The key words 'MUST', 'MUST NOT', … 'MAY', and 'OPTIONAL' … are to be interpreted as
  described in BCP 14 … when, and only when, they appear in all capitals."* MUST/SHOULD/MAY then
  appear in caps throughout (e.g. lifecycle: *"The initialization phase **MUST** be the first
  interaction"*).
- **Normative vs. informative split.** Prose interleaves normative requirements, `mermaid`
  sequence diagrams (informative), inline JSON-RPC examples (informative), and capability
  tables. Security/Trust sections are explicitly softer ("implementors **SHOULD**").
- **Versioning management.** Each revision is a frozen dated folder/page; a `draft` accrues
  changes; a per-version changelog/"Key Changes" page summarizes deltas. Old versions stay
  addressable at their date URL. The wire protocol echoes the same date string (see §B/lifecycle).

---

## B. How schemas & core objects are defined  *(answers user Q1 schema + Q2)*

- **Schema technology: TypeScript-first, JSON-Schema-generated.** The single source of truth is
  `schema/<version>/schema.ts` — a hand-written TypeScript file of `interface`/`type`
  declarations. A `schema.json` (JSON Schema) is **generated** from it for language-agnostic
  consumption. Per the project: *"defined in TypeScript first, but made available as JSON Schema
  as well, for wider compatibility … the TypeScript schema … is the single source of truth …
  all other artifacts derive from this canonical source."*
- **Organization:** one file per version, grouped by `/* … */` banner comments (e.g.
  `/* JSON-RPC types */`), not one-file-per-entity. Versions are sibling dated folders under
  `schema/`.
- **Definition style — inline JSDoc per field, `@category` routing.** Every type and field
  carries a `/** … */` doc comment; `@category` tags map types to their wire method. Example
  (verbatim):
  ```typescript
  /**
   * Definition for a tool the client can call.
   * @category `tools/list`
   */
  export interface Tool extends BaseMetadata {
    /** A human-readable description of the tool. … "hint" to the model. */
    description?: string;
    /** A JSON Schema object defining the expected parameters for the tool. */
    inputSchema: {
      type: "object";
      properties?: { [key: string]: object };
      required?: string[];
    };
    annotations?: ToolAnnotations;
    _meta?: { [key: string]: unknown };
  }
  ```
  Requests are literal-typed by method string:
  ```typescript
  /** Used by the client to invoke a tool provided by the server. @category `tools/call` */
  export interface CallToolRequest extends Request {
    method: "tools/call";
    params: { name: string; arguments?: { [key: string]: unknown }; };
  }
  ```
  Version/const pinning lives in the same file:
  ```typescript
  export const LATEST_PROTOCOL_VERSION = "2025-06-18";
  export const JSONRPC_VERSION = "2.0";
  ```
- **Extensibility mechanism:** an open `_meta?: { [key: string]: unknown }` escape hatch on
  types, an `experimental` capability bucket, and capability negotiation (below) — extension is
  *declared and negotiated*, not implicit.
- **Core-object definition style (2–3 real examples).** MCP defines objects as **JSON-RPC 2.0
  envelopes**; state is expressed as message exchange, not stored status enums. Representative
  lifecycle messages (verbatim from `basic/lifecycle`):
  - *Initialize request* — version + capabilities + client identity in one object:
    ```json
    { "jsonrpc": "2.0", "id": 1, "method": "initialize",
      "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": { "roots": { "listChanged": true }, "sampling": {}, "elicitation": {} },
        "clientInfo": { "name": "ExampleClient", "version": "1.0.0" } } }
    ```
  - *Initialize response* — server mirrors the shape with its own capabilities:
    ```json
    { "jsonrpc": "2.0", "id": 1,
      "result": {
        "protocolVersion": "2025-06-18",
        "capabilities": { "prompts": {"listChanged": true},
          "resources": {"subscribe": true, "listChanged": true}, "tools": {"listChanged": true} },
        "serverInfo": { "name": "ExampleServer", "version": "1.0.0" },
        "instructions": "Optional instructions for the client" } }
    ```
  - *Initialized notification* — a method-only message (no `id`, no params):
    ```json
    { "jsonrpc": "2.0", "method": "notifications/initialized" }
    ```
  **Lifecycle-as-definition style:** three phases — **Initialization → Operation → Shutdown**.
  There is *no* explicit state field; phase is defined *procedurally* by ordering rules ("MUST
  be first interaction," "SHOULD NOT send requests before…") and by transport events for
  shutdown (stdio: close stdin → SIGTERM → SIGKILL). Errors reuse JSON-RPC error codes
  (`-32602` "Unsupported protocol version", with a `data.supported[]` list).

---

## C. How the SDK implements the spec  *(answers user Q3)*

- **Repo layout.** `src/mcp/` top-level modules: `client/`, `server/`, `shared/`, `cli/`,
  `os/`, plus `__init__.py` and **`py.typed`** (ships type info). Around it: `examples/`,
  `tests/`, `docs/` + `docs_src/`, and a vendored `schema/`. So: **spec-mirroring layout** —
  client vs server vs shared session/transport code.
- **Core abstraction: two layers.** A **low-level** `Server`/session API that maps 1:1 onto the
  spec's request/notification types, and a **high-level ergonomic facade** (`FastMCP` in stable
  v1.x; being renamed `MCPServer` in the v2 beta) that most users touch. The facade is
  **decorator-based**:
  ```python
  @mcp.tool()
  def add(a: int, b: int) -> int: ...
  @mcp.resource("greeting://{name}")
  def greeting(name: str) -> str: ...
  ```
- **Type system as the ergonomics.** Python type hints + docstrings are introspected to
  **auto-generate the tool's JSON Schema** (`inputSchema`) and descriptions — the user writes no
  schema by hand. Under the hood the wire types are Pydantic models mirroring `schema.ts`. `Tool`
  from the spec becomes an inferred artifact of a decorated Python function.
- **Transport decoupling.** The session/protocol core is transport-agnostic; concrete transports
  (**stdio**, **Streamable HTTP**, **SSE**, plus in-memory for tests) are pluggable and selected
  at run/connect time. Same server object runs over any transport; clients connect by URL or
  subprocess.
- **Spec↔code sync.** The SDK vendors the versioned schema and models the wire types after
  `schema.ts`; because TS is the source of truth, SDK types are kept consistent with (and partly
  generated/validated against) that canonical schema rather than being independently authored.
- **Async + testing.** Async-first (`anyio`); in-memory transport enables fast client↔server
  tests without real I/O. `tests/` sits beside `src/`.
- **API surface.** Deliberately small at the top (`FastMCP`/`MCPServer` + a few decorators) with
  a fuller low-level API underneath for advanced users. Ships `py.typed` so downstream gets full
  typing.

---

## D. What hello-world looks like  *(answers user Q4)*

**Smallest complete server (current `main`, v2.0 beta — verbatim):**
```python
from mcp.server import MCPServer

mcp = MCPServer("Demo")

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

@mcp.resource("greeting://{name}")
def greeting(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"
```
*(In stable **v1.x** the import is `from mcp.server.fastmcp import FastMCP` and the class is
`FastMCP`; the v2 beta renames it to `MCPServer`. Same decorator ergonomics.)*

**Install (verbatim):**
```bash
uv add "mcp[cli]==2.0.0b1"      # or: pip install "mcp[cli]==2.0.0b1"
```
**Run (dev inspector):**
```bash
uv run mcp dev server.py
```

- **Concept count to first success:** ~3 concepts — instantiate a server, decorate a function as
  a `tool`, decorate a function as a `resource`. **~6 lines of real code.** No schema authoring,
  no transport wiring, no manual JSON-RPC.
- **Prereqs:** Python + `uv` (or pip); the `[cli]` extra provides the `mcp dev`/inspector tooling.

---

## E. Adoption path — what got it used  *(answers user Q5)*

- **Docs site.** `modelcontextprotocol.io` separates **guides/quickstart** from the **numbered
  spec** from **SDK docs**. A dedicated `llms.txt` index exists so LLM tools can crawl the docs.
- **Quickstart design.** Time-to-first-success is minimized: install one package → paste a
  ~6-line server → run `mcp dev` and see it in the **MCP Inspector** GUI. Immediate visual
  feedback loop before any client integration.
- **Example/SDK ecosystem.** First-party SDKs across many languages (Python, TypeScript, etc.),
  an `examples/` dir in each SDK, an official **Inspector** tool, and a growing catalog of
  reference servers. Third parties publish servers/registries.
- **What drove adoption:** (1) a *reference host* — Claude Desktop shipped MCP support, giving
  server authors an instant real client; (2) LSP-style framing made the value legible to
  developers; (3) the 6-line quickstart + Inspector made the first success nearly frictionless;
  (4) multi-language SDKs from day one lowered the barrier. **Friction that remains:** rapid
  dated-version churn and now a v1→v2 SDK rename (`FastMCP`→`MCPServer`) that can break users —
  the README explicitly warns *"v1.x is the only stable release line and remains recommended for
  production"* and advises pinning `mcp>=1.27,<2`.

---

## Methodology takeaways (for Phase 2 / DCP — *method only, no MCP semantics*)

1. **Make one machine-readable schema the single source of truth, and generate the rest.** MCP
   hand-writes `schema.ts` and *generates* JSON Schema + informs SDK types from it. → DCP:
   author entities once as **Pydantic v2 models** (our chosen tech) and generate JSON Schema +
   docs tables from them, so spec and SDK can never silently diverge.
2. **Document every field inline at the schema layer.** MCP's per-field JSDoc + `@category` tags
   mean the schema *is* the reference doc. → DCP: put docstrings on every Pydantic field and tag
   each model with its lifecycle stage/layer, then render the SPEC field tables from those
   docstrings.
3. **Split "authoritative + numbered spec" from "quickstart guide" from "SDK reference."** MCP's
   three-surface docs let a newcomer reach a running demo without reading normative prose. →
   DCP: keep `SPEC.md` normative and terse; put onboarding in a separate quickstart; don't force
   users through the spec to run hello-world.
4. **Give the high-level SDK a tiny, decorator/registration-style surface that hides schema and
   transport.** MCP's 6-line `@mcp.tool()` demo works because type hints auto-derive schemas and
   transport is pluggable underneath. → DCP: a minimal facade for registering roles/participants
   where types drive validation, with the transport-agnostic core (SPEC §3.4) behind it.
5. **Ship a reference host + an inspector so the first success is visual and instant.** MCP's
   Claude Desktop client + Inspector GUI gave authors somewhere to *see it work*. → DCP: pair the
   SDK with a runnable reference orchestrator/replay-viewer so a new user watches a dialogue run,
   not just reads logs.
6. **Version deliberately and warn loudly about breaking renames.** MCP's dated revisions are
   clean, but the `FastMCP`→`MCPServer` rename shows the cost of churn. → DCP: adopt an explicit
   protocol-version string echoed on the wire, and treat public SDK identifier renames as
   breaking changes with pinning guidance — decide the versioning scheme *before* v1.
