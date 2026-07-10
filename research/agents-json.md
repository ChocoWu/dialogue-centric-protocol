# Reference Analysis: agents.json (Wildcard AI)

> **Purpose (per CLAUDE.md §0):** This is an *engineering-methodology* study — "how was
> agents.json made, implemented, and shipped?" — not a design source. Nothing about its
> semantics (OpenAPI-derived flows/actions/links/sources, stateless client-side execution,
> `/.well-known/agents.json` discovery) should enter DCP's `SPEC.md`. The takeaways in the
> final section are strictly about **method**. The single most transferable methodological
> question this reference answers is **"build on an existing schema standard vs. author your
> own"** — agents.json is the "build-on" data point (contrast MCP, which authored from scratch).

**Primary sources consulted (fetched 2026-07-09, not from memory):**
- GitHub repo (source of truth): `https://github.com/wild-card-ai/agents-json` (default branch `master`, MIT license, ~1,315 stars, created 2025-01-30, last push 2025-08-21)
- README: `https://raw.githubusercontent.com/wild-card-ai/agents-json/master/README.md`
- Canonical JSON Schema: `https://raw.githubusercontent.com/wild-card-ai/agents-json/master/agents_json/agentsJson.schema.json`
- Generated Pydantic models: `.../master/python/agentsjson/core/models/schema.py`
- SDK core: `.../python/agentsjson/{__init__.py, core/__init__.py, core/loader.py, core/executor.py, core/parsetools.py}`, `.../python/pyproject.toml`
- Real example file: `.../master/agents_json/resend/agents.json`
- Quickstart notebooks: `.../master/examples/{single.ipynb (Stripe), resend.ipynb}`
- Docs site: `https://docs.wild-card.ai/agentsjson/{introduction,schema,quickstart}` — **note: TLS certificate expired at fetch time (2026-07-09), so docs were reconstructed from the repo README + notebooks, which are the authoritative mirror.**
- Prose intro (via search cache): `https://docs.wild-card.ai/agentsjson/introduction`

> ⚠️ **Disambiguation:** `agent-json.com` / the `/.well-known/agent.json` "discovery document"
> project is a **different, unrelated spec**. The reference in scope is **agents.json (plural)
> by Wildcard AI**, built on OpenAPI. This file analyzes only the Wildcard AI spec.

---

## Snapshot
- **Maintainer / governance:** Started and maintained by **Wildcard AI** (San Francisco). Open
  source, **MIT license**. Governance is informal-community: *"This GitHub repository will host
  informal reviews, allowing for version control and public discussion"* with a Discord for
  discussion — no formal working group or RFC process. `MAINTAINERS.md` lists maintainers.
- **Maturity / versioning:** The **spec** is version **`0.1.0`** (declared via SemVer); the
  **Python package** (`agentsjson`) is at **`0.1.11`**. Explicitly early/pre-1.0: *"There are
  still open questions and more to be done… building iteratively."* A feature roadmap shows most
  advanced control-flow (conditionals, loops, failure handling, pagination, streaming) as
  **unchecked** — only OAuth and a validator are done.
- **Two artifacts, one repo:** (1) the **agents.json Specification** (a JSON Schema + prose),
  and (2) **Wildcard Bridge**, the Python reference implementation that loads/parses/runs it.
- **What it solves (context only):** *"an open specification that formally describes contracts
  for API and agent interactions, built on top of the OpenAPI standard."* It layers LLM-oriented
  "flows" (multi-call workflows) over an existing OpenAPI spec so an agent can discover and run a
  reliable *sequence* of API calls from one top-level directive. Tagline: *"Translate OpenAPI
  into LLM Tools."* Positioned explicitly against MCP: **stateless** (agent owns all context)
  where MCP is stateful.

---

## A. How the spec is authored  *(answers user Q1)*

- **Schema-first, and the schema is literally the spec.** Unlike MCP (prose site + separate
  `schema.ts`), agents.json's normative contract *is* a single JSON Schema file,
  `agents_json/agentsJson.schema.json` (JSON Schema **draft-07**). The README's "Schema" section
  just points to it: *"The full schema is available here."* Human prose (motivations, tenets,
  FAQ) lives in the README and the docs site; it is **informative**, and the machine-readable
  JSON Schema is authoritative.
- **Built on an existing standard rather than from scratch.** The defining authorship decision:
  *"Why is `agents.json` built on OpenAPI? — OpenAPI is the gold standard for describing how API
  endpoints work… These specs alone aren't sufficient for the age of AI agents, but provide
  great groundwork."* The spec is deliberately framed as *"a set of additions to the OpenAPI
  spec"* — it references OpenAPI operations by `operationId` rather than re-describing them.
- **Normative language via embedded RFC 2119.** The requirement vocabulary is carried **inside
  the JSON Schema `description` strings**, not in separate prose. The schema's top-level
  `description` states verbatim: *"This schema uses key words such as \"MUST\", \"MUST NOT\",
  \"REQUIRED\", \"SHALL\"… as defined in [RFC 2119] and [RFC 8174] to indicate requirement
  levels."* Every field description then opens with MUST/SHOULD/OPTIONAL (e.g. `id`: *"MUST
  provide a unique, human-readable identifier… MUST be in snake_case format and globally
  unique"*). So the spec's normative text and its schema are **the same document**.
- **Structure / ordering.** Top-level required keys establish the document skeleton:
  `["agentsJson", "info", "sources", "flows"]` (plus optional `overrides`). Ordering mirrors
  OpenAPI's own top-level shape (`info`, version string first) to stay familiar to OpenAPI
  authors — a deliberate "minimal cognitive delta" choice.
- **Design tenets are stated as authoring constraints** (README "Design Tenets"), verbatim:
  1. *"Build on top of the OpenAPI standard — Leverage existing standards and infrastructure
     where possible."*
  2. *"Optimize schema for LLMs, not humans — Design with AI consumption in mind."*
  3. *"Enforce Statelessness — Orchestration is handled by the calling agent."*
  4. *"Require minimal changes to existing APIs — Make adoption as seamless as possible."*
- **Versioning convention.** SemVer, declared in-band twice: a spec-version field `agentsJson`
  (*"MUST specify the version… Adheres to Semantic Versioning"*) and a per-file `info.version`.
  This contrasts with MCP's **date-string** revisions — agents.json chose classic **SemVer**.

---

## B. How schemas & core objects are defined  *(answers user Q1 schema + Q2)*

- **Schema technology: JSON Schema draft-07, hand-written, as the single source of truth.** One
  file, `agentsJson.schema.json`. Pydantic models are **generated from it** (see §C) — the
  reverse direction from MCP (which hand-writes TypeScript and generates JSON Schema). Evidence
  is in the generated file's own header (verbatim):
  ```python
  # generated by datamodel-codegen:
  #   filename:  schema7.json
  #   timestamp: 2025-01-29T17:53:15+00:00
  ```
- **Organization:** *not* one-file-per-entity. A single nested JSON Schema object; entities
  (`Source`, `Override`, `Flow`, `Action`, `Link`, `Parameter`, …) are inline nested object
  definitions under `properties`, each with per-field `description`. Extensibility is expressed
  with `"additionalProperties": true` on most objects (open by default) — except `Link`,
  `Parameter`, `Content`, `RequestBody`, `Responses` which set `additionalProperties: false`
  (closed where wire-precision matters).
- **The three core objects — verbatim from the schema.**

  **(1) Top-level document — required keys `agentsJson/info/sources/flows`:**
  ```json
  "required": ["agentsJson", "info", "sources", "flows"],
  "properties": {
    "agentsJson": { "type": "string",
      "description": "MUST specify the version of the `agents.json` specification being used. Adheres to Semantic Versioning (SemVer)…" },
    "sources": { "type": "array",
      "description": "MUST include an array of API sources available for use within flows. Each source references an OpenAPI 3+ specification, enabling the chaining of multiple APIs.",
      "items": { "type": "object", "required": ["id", "path"],
        "properties": {
          "id":   { "type": "string", "description": "MUST provide a unique, human-readable identifier for the API source. Identifiers MUST be in snake_case format and globally unique…" },
          "path": { "type": "string", "description": "MUST specify the file path or URL to the OpenAPI 3+ specification of the API source…" } } } }
  ```

  **(2) Flow — the LLM-facing unit: `actions` (which OpenAPI ops to call) + `links` (how their
  data connects) + `fields` (the flow's own params/requestBody/responses):**
  ```json
  "flows": { "type": "array", "items": { "type": "object",
    "required": ["id", "title", "description", "actions", "fields"],
    "properties": {
      "id":          { "description": "MUST provide a unique, human-readable identifier for the flow… **Example**: `process_order_flow`" },
      "description": { "description": "MUST include a detailed description of the flow… Essential for LLMs to determine the appropriate flow to execute based on user intent." },
      "actions": { "type": "array", "items": { "type": "object",
        "required": ["id", "sourceId", "operationId"],
        "properties": {
          "sourceId":    { "description": "MUST reference the `id` of an API source defined in the `sources` array." },
          "operationId": { "description": "MUST identify the specific operation within the API source to execute. Must match an `operationId` in the referenced OpenAPI specification." } } } } } } }
  ```

  **(3) Link — declarative data plumbing between actions, addressed by JSON path
  (`origin → target`); a `null` `actionId` means the flow's own inputs/outputs:**
  ```json
  "links": { "type": "array", "items": { "type": "object",
    "required": ["origin", "target"],
    "properties": {
      "origin": { "type": "object", "required": ["fieldPath"],
        "properties": {
          "actionId":  { "type": ["string","null"], "description": "OPTIONAL. The identifier of the action providing the data. If null, the source is the flow's input parameters." },
          "fieldPath": { "type": "string", "description": "MUST be a JSON path expression specifying the source field… (e.g., `response.data.items.0.name`), treating the OpenAPI operation as the root." } } },
      "target": { "type": "object", "required": ["fieldPath"],
        "properties": {
          "actionId":  { "type": ["string","null"], "description": "OPTIONAL. The identifier of the action receiving the data. If null, the target is the flow's response fields…" },
          "fieldPath": { "type": "string", "description": "MUST be a JSON path expression specifying the destination field… (e.g., `parameters.userId`)…" } } } } }
  ```

- **A real, complete flow (verbatim, `agents_json/resend/agents.json`) — a whole single-action
  "Send Email" flow, showing how a source, action, link, and fields compose:**
  ```json
  {
    "agentsJson": "0.1.0",
    "info": {
      "title": "Resend API Integration Agents",
      "version": "0.1.0",
      "description": "This agents.json specification integrates with the Resend Email API platform…"
    },
    "sources": [
      { "id": "resend",
        "path": "https://raw.githubusercontent.com/wild-card-ai/agents-json/refs/heads/master/agents_json/resend/openapi.yaml",
        "description": "The Resend OpenAPI specification covering emails, domains, API Keys, audiences, contacts, and broadcasts." }
    ],
    "overrides": [],
    "flows": [
      {
        "id": "resend_post_emails_flow",
        "title": "Send Email",
        "description": "Sends an email via the Resend API. Requires sender, recipients, subject, and (optionally) HTML/text content.",
        "actions": [
          { "id": "send_email_action", "sourceId": "resend", "operationId": "resend_post_emails" }
        ],
        "links": [
          { "origin": { "actionId": "resend_post_emails_flow", "fieldPath": "requestBody" },
            "target": { "actionId": "send_email_action",       "fieldPath": "requestBody" } }
        ],
        "fields": {
          "parameters": [],
          "requestBody": {
            "content": { "application/json": {
              "schema": { "type": "object",
                "properties": {
                  "from":    { "type": "string", "description": "Sender email address." },
                  "to":      { "type": "array",  "description": "List of recipient email addresses.", "items": { "type": "string" } },
                  "subject": { "type": "string", "description": "Email subject." },
                  "html":    { "type": "string", "description": "HTML content of the email." },
                  "text":    { "type": "string", "description": "Plain text content of the email." } },
                "required": ["from", "to", "subject"] },
              "example": { "from": "sender@example.com", "to": ["recipient@example.com"], "subject": "Hello", "html": "<p>Hello</p>" } } },
            "required": true },
          "responses": { "success": { "type": "object", "description": "Response containing the email ID.", "example": { "id": "email123" } } }
        }
      }
    ]
  }
  ```
  Note how the flow **re-embeds a JSON-Schema `requestBody`** even though the same shape exists
  in the referenced OpenAPI op — the spec duplicates the LLM-facing contract into the flow so the
  model has a self-contained, description-rich target (tenet 2, "optimize for LLMs").

- **Extensibility mechanism.** `overrides[]` — a patch list (`sourceId` + `operationId` +
  `fieldPath` JSON path + `value`) that mutates the underlying OpenAPI op *without editing the
  original spec* (*"enabling tailored behavior without altering the original API definitions"*).
  This is how agents.json adapts a borrowed standard: **layer patches, don't fork.**

---

## C. How the SDK implements the spec  *(answers user Q3)*

- **Package:** `agentsjson` (aka "Wildcard Bridge"), `python/pyproject.toml`, Poetry-built,
  `python = ">=3.9"`, Pydantic v2 (`pydantic >=2.0.0`). Install: `pip install agentsjson`.
- **Repo layout (`python/agentsjson/`):**
  - `core/models/` — `schema.py` (**codegen'd Pydantic** from the JSON Schema), `auth.py`
    (`AuthConfig`/`AuthType`: Basic, ApiKey, Bearer, OAuth1, OAuth2), `bundle.py` (`Bundle`),
    `tools.py` (`ToolFormat` enum: `OPENAI` / `JSON`).
  - `core/loader.py` — fetches an agents.json URL, validates it, fetches + `overrides`-patches +
    indexes the referenced OpenAPI spec by `operationId`, returns a `Bundle`.
  - `core/parsetools.py` — converts `Flow`s into LLM tool schemas (`flow_to_openai_tool`,
    `flow_to_json_tool`) and system-prompt text (`flows_prompt`).
  - `core/executor.py` — `execute` / `execute_flows`, `apply_link` (does the JSON-path data
    mapping between actions using `benedict` dot/array notation), `resolve_auth`.
  - `integrations/` — **per-API executor code** (`stripe`, `giphy`, `twitter`/`tweepy`,
    `googlesheets`, `hubspot`, `alpaca`, `slack`, `linkup`), each a `map.py` + `tools.py`, some
    wrapping vendored client SDKs. This is where the FAQ's *"route to an SDK instead of making
    HTTP requests directly"* is realized — execution dispatches into real client libraries.
- **Curated public API (small surface).** `agentsjson/__init__.py` (verbatim):
  ```python
  from .core import AgentsJson, ToolFormat, execute, get_tool_prompt, get_tools
  __all__ = ["AgentsJson", "ToolFormat", "execute", "get_tool_prompt", "get_tools"]
  ```
  Five names. The whole user-facing flow is: **`load_agents_json(url) → Bundle`** →
  **`get_tools(agentsjson, ToolFormat.OPENAI)`** (flows become function-calling tools) → hand to
  any LLM → **`execute(agentsjson, llm_response, ToolFormat.OPENAI, auth)`**.
- **Spec↔code sync.** One-directional codegen: `schema.py` is *generated* from the JSON Schema
  (`# generated by datamodel-codegen: filename: schema7.json`). So the JSON Schema is the single
  source of truth and the SDK types can't silently drift — but it also means **hand-edits to
  `schema.py` would be clobbered on regeneration** (a codegen discipline cost).
- **Statelessness by construction.** No sessions, no persistent connection, no server object.
  `load → get_tools → execute` is a pure request/response pipeline; the calling agent holds all
  state. `Bundle` (`agentsJson` + resolved `openapi` + `operations` index) is the only in-memory
  artifact and it is immutable input, not conversation state.
- **`Link` model is closed (`extra='forbid'`), most others open (`extra='allow'`).** The
  codegen faithfully carried the JSON Schema's `additionalProperties` choices into Pydantic
  `ConfigDict` — schema decisions propagate automatically into validation strictness.

---

## D. What hello-world looks like  *(answers user Q4)*

**Smallest complete working example (verbatim, composed from `examples/single.ipynb`, the
Stripe quickstart — the direct-load path with no hosted dependency):**
```python
%pip install agentsjson openai

from agentsjson.core import load_agents_json
from agentsjson.core.models.bundle import Bundle
from agentsjson import ToolFormat, get_tools, get_tool_prompt, execute
from agentsjson.core.models.auth import AuthType, BearerAuthConfig
from openai import OpenAI

agents_json_url = "https://raw.githubusercontent.com/wild-card-ai/agents-json/refs/heads/master/agents_json/stripe/agents.json"

# 1. Load + resolve the agents.json (fetches & indexes the referenced OpenAPI spec)
data: Bundle = load_agents_json(agents_json_url)
agentsjson = data.agentsJson

# 2. Turn flows into a system prompt + OpenAI tools
system_prompt = f"You are an AI assistant... You have access to the following API flows:\n{get_tool_prompt(agentsjson)}"
query = "Create a new Stripe product for Tie Dye T-Shirts priced at $10, $15, and $30 for small, medium, and large sizes"

# 3. Auth
auth = BearerAuthConfig(type=AuthType.BEARER, token=STRIPE_API_KEY)

# 4. Let the LLM pick a flow + fill args, then execute it
client = OpenAI(api_key=OPENAI_API_KEY)
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "system", "content": system_prompt},
              {"role": "user",   "content": query}],
    tools=get_tools(agentsjson, format=ToolFormat.OPENAI),
    temperature=0,
)
response = execute(agentsjson, response, format=ToolFormat.OPENAI, auth=auth)
```

- **Concept count to first success:** ~5 concepts — `load_agents_json`/`Bundle`, `get_tools`,
  an auth config, your own LLM call, `execute`. **~15 lines** of real code, but crucially the
  **agents.json file itself is pre-written** (you point at a URL); the user authors *no schema*.
- **Prereqs:** Python ≥3.9, `agentsjson`, an LLM client (`openai`), an API key for the target
  service (Stripe/Resend), and — for the Stripe path — nothing else. **The `resend.ipynb` path
  additionally requires a hosted `WILDCARD_API_KEY`** and calls `https://api.wild-card.ai/search`
  to *dynamically select* which agents.json to load — i.e. the "magic" tool-selection demo has a
  **hosted-service dependency**, whereas the direct-`load_agents_json(url)` path is fully local.
- **No transport wiring, no server to run.** Because execution is stateless and dispatches into
  bundled integration SDKs, "hello world" is a single Python script, not a running server (the
  opposite of MCP's `mcp dev` inspector loop).

**Install (verbatim, from the notebooks):**
```bash
%pip install agentsjson
%pip install openai
```

---

## E. Adoption path — what got it used  *(answers user Q5)*

- **Onboarding = pick a notebook.** No "write your own server" first step. The README's
  Quickstart is a **table of five runnable Jupyter notebooks** keyed by auth type (Resend/API
  Key, Stripe/Bearer, Rootly/Bearer, Twitter+Giphy/OAuth1, Resend+Hubspot+Sheets/OAuth2). First
  success = open a notebook, paste keys, run cells — an integration executes end-to-end.
- **Prebuilt registry lowers the "who writes the file?" barrier.** The hard part (authoring a
  correct agents.json for a real API) is pre-done for ~10 services in-repo (`agents_json/<svc>/`
  each with `agents.json` + `openapi.yaml`), and *"we maintain a registry for available
  agents.json files"* (`wild-card.ai/registry`) plus a hosted search endpoint. Adoption strategy:
  **ship a catalog so consumers never author the schema.**
- **Discovery convention borrowed from robots.txt/llms.txt.** *"We propose the file placed in
  `/.well-known/agents.json` so it is easily discoverable by agents"* — reuses a familiar web
  convention rather than inventing a discovery protocol.
- **Distribution:** PyPI package `agentsjson` (`pip install agentsjson`); repo demos hosted at
  `demo.wild-card.ai/<svc>`; community via Discord; MIT license.
- **What drove attention:** (1) a sharp, legible framing — *"Translate OpenAPI into LLM Tools"* —
  and a timely "why now" (OpenAI Operator); (2) explicit positioning against MCP
  (**stateless / no new servers / reuse your existing API infra** — see the FAQ) that resonated
  with teams wary of MCP's stateful server model; (3) a ready-made catalog + notebooks so the
  first run needs zero schema authoring; (4) a Show HN launch (`news.ycombinator.com/item?id=43243893`).
- **Friction / blockers that remain:** (a) **spec is 0.1.0 and shallow** — the roadmap leaves
  conditionals, loops, failure handling, pagination, streaming, and runtime field-transforms
  **unchecked**, so real multi-step robustness is unproven; (b) **the flashy dynamic-selection
  demo depends on Wildcard's hosted API** (`api.wild-card.ai` + `WILDCARD_API_KEY`), coupling
  "the good experience" to a vendor; (c) **execution routes through bundled per-vendor SDKs**, so
  the core package `pyproject.toml` hard-depends on `stripe`, `tweepy`, `google-api-python-client`,
  `hubspot-api-client`, `slack_sdk`, `linkup-sdk`, etc. — a **heavy, coupled dependency tree** for
  what is nominally a spec parser; (d) authoring a *new* agents.json by hand is nontrivial (the
  "Interactive Builder" is still unchecked on the roadmap); (e) low bus factor / single-vendor
  governance with only informal review.

---

## Methodology takeaways (for Phase 2 / DCP — *method only, no agents.json semantics*)

1. **"Build on an existing schema standard vs. author your own" is a first-class methodology
   fork — agents.json is the *build-on* case, MCP the *author-from-scratch* case.** agents.json
   reused OpenAPI (borrowed its `operationId` addressing, `requestBody`/`responses` shapes, SemVer
   habit) and only *added* a thin flows/links layer + a patch mechanism (`overrides`) instead of
   forking. Benefit: instant familiarity + existing infra; cost: it inherits OpenAPI's complexity
   and must duplicate LLM-facing schema into flows anyway. → **DCP:** treat this as a *decision to
   make explicitly and record in the Decision Log*, not a default. DCP's dialogue semantics have
   no mature host standard to borrow, so authoring our own Pydantic-first schema is defensible —
   but where a neutral primitive already has a standard (e.g. JSON Schema for message *payloads*,
   RFC 3339 for timestamps), **reuse it rather than reinventing**, and confine our novelty to the
   dialogue layer.

2. **Pick one machine-readable schema as the source of truth and codegen the SDK types from it —
   direction matters and is reversible.** agents.json hand-writes JSON Schema (draft-07) and
   generates Pydantic via `datamodel-codegen` (`# generated by datamodel-codegen`); MCP goes the
   other way (TS → JSON Schema). Either works; the invariant is *single source + generation so
   spec and code can't drift.* → **DCP:** since we've chosen **Pydantic v2 as the source of
   truth** (CLAUDE.md §3), generate JSON Schema *from* the models — and never hand-edit generated
   artifacts (agents.json's `schema.py` would be clobbered on regen; enforce "generated, do not
   edit" banners).

3. **Embed the normative RFC-2119 vocabulary directly in the schema field descriptions so the
   schema *is* the spec.** agents.json states the RFC 2119/8174 boilerplate once in the schema's
   top-level `description`, then opens every field with MUST/SHOULD/OPTIONAL — one artifact serves
   as both contract and reference. → **DCP:** put a MUST/SHOULD-worded docstring on every Pydantic
   field and render SPEC.md's field tables from those docstrings, so normative prose and validation
   can never disagree (reinforces the MCP takeaway, from an independent example).

4. **Ship a *catalog of prebuilt, runnable examples* so first-success needs zero schema
   authoring.** agents.json's entire onboarding is "pick one of five notebooks pointed at a
   pre-written file in the registry" — the hard authoring step is pre-done. → **DCP:** pair the
   SDK with a small library of ready-made dialogue configurations (roles/orchestration presets)
   and a canonical hello-world that a user *runs* before they ever *author* a dialogue spec;
   don't make "write a valid spec file by hand" the first task.

5. **Keep the public API surface tiny and pipeline-shaped (`load → adapt → execute`).**
   agentsjson exposes 5 names and a linear flow; statelessness means no session objects to manage.
   → **DCP:** curate `__init__` to a handful of verbs, and prefer a legible pipeline for the happy
   path. *But note the trade-off DCP should reject:* agents.json achieves simplicity partly by
   pushing all state onto the caller — DCP's value *is* managed dialogue state, so keep the API
   small **without** offloading orchestration correctness to the user.

6. **Don't let a spec-parser's core package drag in heavy execution/vendor dependencies, and
   don't couple the best demo to a hosted service.** agentsjson's core `pyproject.toml` hard-deps
   on `stripe`/`tweepy`/`google-api-python-client`/`hubspot`/`slack_sdk`, and its dynamic-selection
   demo needs `api.wild-card.ai` — both raise adoption friction and lock-in. → **DCP:** keep the
   core package dependency-light (schema + orchestration only), push transport/integration
   adapters into optional extras behind an interface (CLAUDE.md §3), and make the *fully local*
   path the headline demo — never gate hello-world on a hosted endpoint or an API key we control.
