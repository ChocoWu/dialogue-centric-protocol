# Reference Analysis: Agent Network Protocol (ANP)

> **Purpose (per CLAUDE.md §0):** This is an *engineering-methodology* study — "how was ANP
> made, implemented, and shipped?" — **not** a design source. ANP is a *decentralized* protocol
> built on **W3C DIDs (`did:wba`)**, **JSON-LD / semantic web (schema.org, RDF)**, and a
> natural-language **meta-protocol**. None of that design — decentralized identity, DID methods,
> linked-data descriptions, protocol negotiation — may enter DCP's `SPEC.md`. The DID/identity
> stack is **design**; from it we extract only the *documentation, spec-authoring, schema-
> organization, and SDK methodology* around it. The takeaways at the end are strictly **method**.

**Primary sources consulted (fetched 2026-07-09, not from memory):**
- Spec repo (source of truth): `https://github.com/agent-network-protocol/AgentNetworkProtocol`
  (root file listing via `api.github.com/repos/.../contents/`)
- Agent Description spec, **repo `main`**: `https://raw.githubusercontent.com/agent-network-protocol/AgentNetworkProtocol/main/07-anp-agent-description-protocol-specification.md`
- Agent Description spec, **published site**: `https://agentnetworkprotocol.com/en/specs/07-anp-agent-description-protocol-specification/`
- did:wba method spec: `https://raw.githubusercontent.com/agent-network-protocol/AgentNetworkProtocol/main/03-did-wba-method-design-specification.md`
- Technical white paper: `https://agentnetworkprotocol.com/en/specs/01-agentnetworkprotocol-technical-white-paper/`
- SDK repo `AgentConnect` (PyPI package `anp`): `https://github.com/agent-network-protocol/AgentConnect`
  README (`.../blob/master/README.md`) + `anp/` package listing via `api.github.com/.../contents/anp`
- Project site: `https://agent-network-protocol.com/`

---

## Snapshot
- **Maintainer / governance:** Single-author project. Copyright `(c) 2024 GaoWei Chang`
  (`chgaowei@gmail.com`; affiliated "Hangzhou Bit Intelligence Technology Co., Ltd." in examples).
  **MIT License.** The white paper "provides no explicit statement regarding governance
  structures, contribution processes, or community participation mechanisms" beyond a
  `CONTRIBUTING.md`; community lives in a Discord and the project site. Contrast MCP/A2A, which
  are backed by an org + formal revision process — ANP is closer to a founder-led open project.
- **Maturity / versioning:** Specification-set release **v1.1** (documents `ANP-03/04/07/08/09/10`
  marked "Released v1.1"; the **meta-protocol `ANP-06` remains draft**). Two-tier versioning:
  the *document release version* is `1.1`, while the *wire* `protocolVersion` field is still
  `"1.0.0"` — the README notes v1.1 "does not change protocol payload fields." Numbering scheme is
  `ANP-{number}` with `major.minor` doc versions (**not** date-stamped like MCP).
- **What it solves (context only — NOT our concern):** A protocol *suite* to "become the HTTP of
  the Agentic Web era" — decentralized agent **identity** (`did:wba`), **naming** (WNS handles),
  **description**, **discovery**, **encrypted messaging**, and **payment**, so agents authenticate
  and interoperate directly across platforms without a central broker. Framing: identity-first,
  decentralized, semantic-web-based.

---

## A. How the spec is authored  *(answers user Q1)*

- **Many numbered documents in one repo, not a schema file.** Unlike MCP (site prose + one
  canonical `schema.ts`), ANP's normative content is a set of **numbered Markdown specs living
  directly in the repo root**, each a self-contained document. Verbatim root listing:
  ```
  01-agentnetworkprotocol-technical-white-paper.md
  03-did-wba-method-design-specification.md
  04-anp-did-wba-name-space-specification.md
  06-anp-agent-communication-meta-protocol-specification.md
  07-anp-agent-description-protocol-specification.md
  08-ANP-Agent-Discovery-Protocol-Specification.md
  09-ANP-end-to-end-instant-messaging-protocol-specification.md
  appendix-a-did-wba-k1-compatibility-extension.md
  appendix-b-compatibility-with-native-did-web.md
  ```
  Plus directories `application/`, `message/`, `standard/`, `references/`, `examples/`,
  `deprecated/`, `chinese/`, `docs/`, `blogs/`. The **white paper (`01`) is the entry document**
  that frames the three-layer architecture; each capability then gets its own numbered spec.
  Numbers are **sparse and stable** (no `02`/`05` at root), so a document can be added or
  deprecated without renumbering the set — a deliberate cataloguing method.
- **Document-internal structure.** Each spec follows a house template: a **metadata header**
  (Document ID, Status, Version, Applicability) → Abstract → numbered sections → Appendices →
  a References section (the did:wba spec cites "25+" references). This gives every document a
  predictable, RFC-like shape.
- **Normative language is inconsistent across documents.** The `did:wba` spec (`03`) adopts formal
  **RFC 2119** keywords (e.g. *"the last path segment **MUST** be the `e1_` binding public key
  fingerprint segment"*). The Agent Description spec (`07`) instead uses **"Required"/"Optional"
  designations in field tables**, not MUST/SHOULD/MAY. So requirement strength is signalled
  differently per doc — a consistency gap worth avoiding.
- **Bilingual authoring.** Every artifact is shipped **EN + Chinese** in parallel (`README.md` /
  `README.cn.md`, `CONTRIBUTING.cn.md`, a `chinese/` tree, and `/en/` vs `/zh/` site paths).
- **Published site can lag the repo — a real methodology hazard.** The canonical repo `main` and
  the published spec site **disagree on a core object's format** (see §B): `07` on the site still
  shows full **JSON-LD**, while `07` on `main` has migrated to **plain JSON** and left a
  `### JSON-LD Format` heading with the body literally **"To be supplemented."** Two sources of
  truth drifted apart — the opposite of MCP's "schema is the single source, prose references it."
- **Examples embedded inline.** Normative field tables are immediately followed by a full JSON
  example of the object, so the reader sees the shape in context (same instinct as MCP's inline
  JSON-RPC samples).

---

## B. How schemas & core objects are defined  *(answers user Q1 schema + Q2)*

- **Schema technology: prose field-tables + example JSON, with W3C/JSON-LD standards borrowed for
  identity.** There is **no machine-readable schema artifact** (no `schema.ts`, no `.json` JSON
  Schema, no Protobuf) that is the source of truth. Objects are defined by **descriptive tables**
  (`field | type | Required/Optional | description`) plus a **verbatim JSON example**. Semantics
  are meant to come from **linked data**: the white paper commits to *"RDF (Resource Description
  Framework), JSON-LD (JSON Linked Data), schema.org"* for cross-agent consistency.
- **Organization: one object family per numbered document**, not one file per entity and not one
  monolithic schema. Identity objects live in `03`, naming in `04`, the agent-description object in
  `07`, discovery in `08`, messaging envelopes in `09`.
- **Extensibility is expressed by (a) reusing schema.org vocabulary** (*"a subset of schema.org's
  Product properties can be used to define a specific type"*) and **(b) an open `interfaces[]`
  array** where each interface names its own `protocol` (`YAML`, `JSON-RPC 2.0`, `openrpc`, `MCP`,
  `WebRTC`) and a `url` — i.e. capabilities are *linked out to*, not enumerated in a fixed schema.
- **Versioning of objects:** each object carries `protocolVersion` (`"1.0.0"`) inside the payload,
  decoupled from the document release version (`1.1`).

**Core-object example 1 — DID document (`did:wba`, from spec `03`, verbatim).** This is a standard
**W3C DID document in JSON-LD** (`@context` = W3C DID + security suites); note the ANP-specific
`service` entries (`AgentDescription`, `ANPHandleService`, `ANPMessageService`) that wire identity
to the description/messaging layers, and an embedded Data-Integrity `proof`:
```json
{
  "@context": [
    "https://www.w3.org/ns/did/v1",
    "https://w3id.org/security/data-integrity/v2",
    "https://w3id.org/security/multikey/v1",
    "https://w3id.org/security/suites/x25519-2019/v1"
  ],
  "id": "did:wba:example.com%3A8800:user:alice:e1_<fingerprint>",
  "verificationMethod": [
    {
      "id": "did:wba:example.com%3A8800:user:alice:e1_<fingerprint>#key-1",
      "type": "Multikey",
      "controller": "did:wba:example.com%3A8800:user:alice:e1_<fingerprint>",
      "publicKeyMultibase": "z6Mk..."
    },
    {
      "id": "did:wba:example.com%3A8800:user:alice:e1_<fingerprint>#key-x25519-1",
      "type": "X25519KeyAgreementKey2019",
      "controller": "did:wba:example.com%3A8800:user:alice:e1_<fingerprint>",
      "publicKeyMultibase": "z9hFgmPVfmBZwRvFEyniQDBkz9LmV7gDEqytWyGZLmDXE"
    }
  ],
  "authentication": [
    "did:wba:example.com%3A8800:user:alice:e1_<fingerprint>#key-1"
  ],
  "assertionMethod": [
    "did:wba:example.com%3A8800:user:alice:e1_<fingerprint>#key-1"
  ],
  "keyAgreement": [
    "did:wba:example.com%3A8800:user:alice:e1_<fingerprint>#key-x25519-1"
  ],
  "service": [
    {
      "id": "did:wba:example.com%3A8800:user:alice:e1_<fingerprint>#ad",
      "type": "AgentDescription",
      "serviceEndpoint": "https://agent-network-protocol.com/agents/example/ad.json"
    },
    {
      "id": "did:wba:example.com%3A8800:user:alice:e1_<fingerprint>#handle",
      "type": "ANPHandleService",
      "serviceEndpoint": "https://example.com/.well-known/handle/alice"
    },
    {
      "id": "did:wba:example.com%3A8800:user:alice:e1_<fingerprint>#anp",
      "type": "ANPMessageService",
      "serviceEndpoint": "https://example.com/anp",
      "serviceDid": "did:wba:example.com%3A8800"
    }
  ],
  "proof": {
    "type": "DataIntegrityProof",
    "cryptosuite": "eddsa-jcs-2022",
    "created": "2025-01-01T00:00:00Z",
    "verificationMethod": "did:wba:example.com%3A8800:user:alice:e1_<fingerprint>#key-1",
    "proofPurpose": "assertionMethod",
    "proofValue": "z..."
  }
}
```

**Core-object example 2 — Agent Description, CURRENT repo `main` (spec `07`, verbatim, plain
JSON).** The agent is served as a static `ad.json`. Note `protocolType`/`protocolVersion`, an
`Infomations[]` array (typo preserved from the source), and an open `interfaces[]` list that can
point at *any* interface protocol including `MCP`:
```json
{
  "protocolType": "ANP",
  "protocolVersion": "1.0.0",
  "type": "AgentDescription",
  "url": "https://grand-hotel.com/agents/hotel-assistant/ad.json",
  "name": "Grand Hotel Assistant",
  "did": "did:wba:grand-hotel.com:service:hotel-assistant",
  "owner": {
    "type": "Organization",
    "name": "Grand Hotel Management Group",
    "url": "https://grand-hotel.com"
  },
  "description": "Grand Hotel Assistant is an intelligent hospitality agent providing comprehensive hotel services including room booking, concierge services, guest assistance, and real-time communication capabilities.",
  "created": "2024-12-31T12:00:00Z",
  "securityDefinitions": {
    "didwba_sc": {
      "scheme": "didwba",
      "in": "header",
      "name": "Authorization"
    }
  },
  "security": "didwba_sc",
  "Infomations": [
    {
      "type": "Product",
      "description": "Luxury hotel rooms with premium amenities and personalized services.",
      "url": "https://grand-hotel.com/products/luxury-rooms.json"
    },
    {
      "type": "Information",
      "description": "Complete hotel information including facilities, amenities, location, and policies.",
      "url": "https://grand-hotel.com/info/hotel-basic-info.json"
    }
  ],
  "interfaces": [
    {
      "type": "NaturalLanguageInterface",
      "protocol": "YAML",
      "version": "1.2.2",
      "url": "https://grand-hotel.com/api/nl-interface.yaml",
      "description": "Natural language interface for conversational hotel services and guest assistance."
    },
    {
      "type": "StructuredInterface",
      "protocol": "MCP",
      "version": "1.0",
      "url": "https://grand-hotel.com/api/mcp-interface.json",
      "description": "MCP-compatible interface for seamless integration with MCP-based systems."
    }
  ],
  "proof": {
    "type": "EcdsaSecp256r1Signature2019",
    "created": "2024-12-31T15:00:00Z",
    "proofPurpose": "assertionMethod",
    "verificationMethod": "did:wba:grand-hotel.com:service:hotel-assistant#keys-1",
    "challenge": "1235abcd6789",
    "proofValue": "z58DAdFfa9SkqZMVPxAQpic7ndSayn1PzZs6ZjWp1CktyGesjuTSwRdoWhAfGFCF5bppETSTojQCrfFPP2oumHKtz"
  }
}
```
*(Abridged: the `main` example additionally lists `VideoObject`, `openrpc`, and `WebRTC`
interfaces; fields above are verbatim.)*

**Core-object example 3 — same object, PUBLISHED SITE version (spec `07` on
agentnetworkprotocol.com, verbatim, JSON-LD).** The site still serves the **older linked-data
form**: a `@context` with schema.org `@vocab`, `@type`/`@id`, and ANP-namespaced interface types
(`ad:NaturalLanguageInterface`). This is the object DCP should look at *only* to learn the
**format-migration lesson**, not to copy:
```json
{
  "@context": {
    "@vocab": "https://schema.org/",
    "did": "https://w3id.org/did#",
    "ad": "https://agent-network-protocol.com/ad#"
  },
  "@type": "ad:AgentDescription",
  "@id": "https://agent-network-protocol.com/agents/smartassistant",
  "name": "SmartAssistant",
  "did": "did:wba:example.com:user:alice",
  "owner": {
    "@type": "Organization",
    "name": "Hangzhou Bit Intelligence Technology Co., Ltd.",
    "@id": "https://agent-network-protocol.com"
  },
  "version": "1.0.0",
  "created": "2024-12-31T12:00:00Z",
  "securityDefinitions": {
    "didwba_sc": { "scheme": "didwba", "in": "header", "name": "Authorization" }
  },
  "security": "didwba_sc",
  "interfaces": [
    {
      "@type": "ad:NaturalLanguageInterface",
      "protocol": "YAML",
      "url": "https://agent-network-protocol.com/api/nl-interface.yaml",
      "description": "A YAML file for interacting with the intelligent agent through natural language."
    },
    {
      "@type": "ad:StructuredInterface",
      "protocol": "JSON-RPC 2.0",
      "url": "https://agent-network-protocol.com/api/api-interface.json",
      "description": "A JSON-RPC 2.0 file for interacting with the intelligent agent through APIs."
    }
  ]
}
```
**Finding (uncertain, flagged):** the same numbered spec has **two live incompatible forms** —
JSON-LD on the deployed site vs. plain JSON on `main` with JSON-LD "To be supplemented." Whether
the plain-JSON form is intended to fully replace JSON-LD, or JSON-LD returns as an optional layer,
is **not stated in the source**. The definitional method here is prose-first (tables + example),
which is exactly what lets the two surfaces diverge.

---

## C. How the SDK implements the spec  *(answers user Q3)*

- **Repo / package.** The implementation is `AgentConnect`, published to PyPI as **`anp`**. It is a
  **polyglot monorepo**: parallel language trees `golang/`, `rust/`, `dart/`, `typescript/ts_sdk/`,
  `java/`, plus the Python package `anp/`. So one repo backs many language SDKs (contrast MCP's
  per-language repos).
- **`anp/` package layout mirrors the spec suite** — one submodule per capability document
  (verbatim listing):
  ```
  anp/
  ├── __init__.py
  ├── openanp            # high-level agent-authoring facade (the ergonomic entry point)
  ├── fastanp            # FastAPI integration
  ├── authentication     # did:wba auth
  ├── proof              # verifiable proofs / signatures
  ├── wns                # WNS handle resolution (spec 04)
  ├── meta_protocol      # meta-protocol negotiation (spec 06, draft)
  ├── ap2                # agent payment
  ├── anp_crawler        # discovery / crawling agent descriptions (spec 08)
  ├── direct_e2ee        # end-to-end encryption variants (spec 09) ...
  ├── e2e_encryption
  ├── e2e_encryption_hpke
  ├── e2e_encryption_v2
  ├── utils
  └── unittest
  ```
  The **spec→module mapping is direct** (identity/proof/wns/description/discovery/messaging/payment
  each get a module), so the package tree reads as a table of contents of the protocol suite.
- **Core public surface: a decorator-based facade (`openanp`).** Most users touch
  `AgentConfig`, the class decorator `@anp_agent(...)`, and the method decorator `@interface`.
  Under the hood the SDK **auto-generates the wire artifacts from Python type hints**: the README
  states the framework automatically creates `GET /agent/ad.json` (the Agent Description),
  `GET /agent/interface.json` ("OpenRPC interface from type hints"), and `POST /agent/rpc`
  (JSON-RPC 2.0). So — like MCP's `@mcp.tool()` — **type hints derive the schema; the user writes
  no JSON-LD/OpenRPC by hand.**
- **Transport / I/O.** The facade is **built on FastAPI + Uvicorn (HTTP)**; the user mounts the
  agent's router into a FastAPI app (`app.include_router(...)`). Async-first (`async def`
  interfaces). I/O is isolated at the FastAPI/HTTP edge; identity/proof/e2ee are separate modules.
- **Schema↔code sync.** There is **no generated shared schema**: since the spec has no
  machine-readable source of truth, the SDK's wire output (`ad.json`, OpenRPC) is produced
  *from Python code*, and conformance to the prose spec is maintained by hand. This is the inverse
  of MCP's "canonical schema → SDK types" flow, and is the structural reason spec and code can drift.
- **API surface.** Small high-level surface (`openanp`/`fastanp`) over a broad low-level module set
  (auth, proof, wns, four e2ee variants, ap2, crawler). Optional extras gate heavy deps:
  `pip install "anp[api]"` / `uv sync --extra api` add FastAPI/OpenAI; `--extra dev` adds dev tools.

---

## D. What hello-world looks like  *(answers user Q4)*

**Smallest complete agent (AgentConnect README, `openanp`, verbatim):**
```python
from fastapi import FastAPI
from anp.openanp import AgentConfig, anp_agent, interface

@anp_agent(AgentConfig(
    name="Calculator",
    did="did:wba:example.com:calculator",
    prefix="/agent",
    description="A simple calculator agent",
))
class CalculatorAgent:
    @interface
    async def add(self, a: int, b: int) -> int:
        return a + b

app = FastAPI(title="Calculator Agent")
app.include_router(CalculatorAgent.router())
```

**Install (verbatim):**
```bash
pip install anp
pip install "anp[api]"   # With FastAPI/OpenAI extras
# or, developing from the repo:
uv sync --extra api
```
**Run — server (Terminal 1, verbatim):**
```bash
uvicorn app:app --port 8000
```
**Run — client (Terminal 2, verbatim):**
```bash
uv run python examples/python/openanp_examples/minimal_client.py
```

- **Concept count to first success:** ~4 concepts — `AgentConfig` (incl. a `did:` string),
  the `@anp_agent` class decorator, the `@interface` method decorator, and mounting into FastAPI.
  **~12 lines of real code.** No hand-written Agent Description, OpenRPC, or JSON-RPC — those are
  generated. **But** a `did:` identifier is required even for hello-world (identity is not
  optional), so the conceptual floor is higher than MCP's 6-line tool.
- **Prereqs:** Python + `pip`/`uv`; the `[api]` extra (FastAPI/Uvicorn) to actually serve; a
  second process to run the sample client. First "success" is an HTTP agent exposing
  `/agent/ad.json` + `/agent/rpc`, exercised by the bundled `minimal_client.py`.

---

## E. Adoption path — what got it used  *(answers user Q5)*

- **Distribution.** PyPI `pip install anp` (+ `[api]` extra); multi-language SDKs in one repo
  (`golang/`, `rust/`, `dart/`, `typescript/ts_sdk/`, `java/`) signal cross-platform intent from
  the start. Versioned by `major.minor` document releases (`v1.1`).
- **Docs surfaces.** Three-ish surfaces: the **project site** `agent-network-protocol.com`
  (marketing + docs), the **spec site** `agentnetworkprotocol.com/en/specs/...` (numbered specs,
  EN/ZH), a `blogs/` tree, and per-SDK `README` + `examples/`. Onboarding for the SDK is a
  README quickstart with the copy-paste agent above.
- **Community.** Discord (`discord.gg/sFjBKTY7sB`) and a single maintainer email; `CONTRIBUTING.md`
  present. No visible RFC/working-group process.
- **What plausibly drives adoption:** (1) a **coherent "HTTP of the Agentic Web" narrative** that
  makes the value legible; (2) **standards reuse** — `did:web`/W3C DID, schema.org, JSON-RPC,
  OpenRPC, FastAPI — lowers "is this real?" doubt and lets it ride existing tooling;
  (3) a **decorator quickstart** that hides identity/schema/transport for the happy path;
  (4) breadth — one repo, many languages and capabilities (identity→payment).
- **Friction / blockers (real):** (a) **identity tax** — every agent needs a `did:wba`, key
  material, and (in production) DID-document hosting + proofs, so "hello-world to production" is a
  cliff MCP doesn't have; (b) **no machine-readable schema / no single source of truth**, so
  spec↔SDK and site↔repo can drift — and demonstrably **do** (the `07` JSON-LD-vs-plain-JSON
  split, the `### JSON-LD Format` "To be supplemented" gap, an `Infomations` typo shipped in the
  normative example); (c) **inconsistent normative language** across docs (RFC 2119 in `03`,
  Required/Optional tables in `07`); (d) **single-maintainer governance** raises bus-factor and
  slows the kind of formal versioning MCP/A2A have; (e) the **meta-protocol (`06`) is still draft**,
  so the headline "negotiate protocols in natural language" capability isn't shippable yet.

---

## Methodology takeaways (for Phase 2 / DCP — *method only, NO ANP design semantics; DID/identity
is design and is deliberately excluded*)

1. **Catalogue the spec as sparsely-numbered, self-contained documents (`ANP-03`, `ANP-07`…) with
   a shared house-template header (ID/Status/Version) and a lead white paper.** The sparse numbers
   let docs be added/deprecated without renumbering. → DCP: even though `SPEC.md` is one file,
   give each entity/layer a **stable section ID and a per-section status/version header**, and
   keep a short "overview" preamble that indexes them — so sections can evolve independently and be
   cited precisely.
2. **Pick ONE requirement-strength convention and one source of truth — ANP shows the cost of
   neither.** RFC 2119 in one doc vs. "Required/Optional" tables in another, and a website that
   serves an *older, incompatible* form of the same object than the repo, are avoidable failures.
   → DCP: adopt **RFC 2119 uniformly**, make the **Pydantic models the single source of truth**,
   and **generate** the SPEC field tables + any doc site from them so surfaces cannot diverge.
3. **Never ship a normative example you didn't validate.** ANP's canonical Agent Description
   contains a placeholder section ("To be supplemented") and a field typo (`Infomations`) in the
   *released* v1.1 doc. → DCP: **round-trip every SPEC example through the schema in CI** (parse →
   validate → re-serialize); a failing example example fails the build.
4. **Let type hints generate the wire artifacts; keep the authoring facade decorator-based.** ANP's
   `@anp_agent`/`@interface` derive `ad.json` + OpenRPC + the RPC endpoint from Python signatures —
   the same "types drive schema" ergonomic MCP uses, and the reason its hello-world stays short.
   → DCP: a thin decorator/registration facade where **Python types drive validation and any
   emitted descriptor**, over the transport-agnostic core. (Adopt the *mechanism*, not ANP's HTTP/
   DID wire choices.)
5. **Mirror the spec's table-of-contents in the SDK package tree, one module per spec section.**
   `anp/` maps module→document (`authentication`, `wns`, `proof`, `anp_crawler`…), so the package
   is a legible index of the protocol. → DCP: `src/dcp/` modules should **name-match SPEC layers**
   (dialogue-state / participation / orchestration / delivery) 1:1, as CLAUDE.md §1 already plans.
6. **Keep the hello-world floor genuinely low — don't make foundational machinery mandatory for
   first success.** ANP's `did:` requirement raises the conceptual floor and creates a hello-world→
   production cliff; gating heavy deps behind extras (`anp[api]`) is good, requiring identity to
   run *anything* is not. → DCP: the **canonical hello-world must run with zero external identity/
   infra**; anything heavier (auth, persistence, real transport) is an **opt-in extra**, never a
   prerequisite to see a dialogue run.
