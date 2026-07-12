# DCP Remote Component Binding — transport-independent semantics

**Status:** normative for Phase 7C. 
Companion: [http-sse.md](http-sse.md) (the concrete HTTP mapping).
Source contract: [PROPOSAL-component-ecosystem.md](../PROPOSAL-component-ecosystem.md) §7 (D5, D6, D12, D13, D20).

This document defines *what* a remote DCP component exchange means, independent of transport. 
The HTTP/SSE mapping is a separate adapter (D6) — the same rule that keeps the SDK's semantic core free of any transport (SPEC §3.5).

## 1. Model

A **remote component** is a component whose `access_mode` is `remote`: its runtime interface runs on a provider's server, and a **proxy** on the owner's side implements the local interface (`ControlPolicy` / `ModelProvider` / …) by exchanging envelopes with it. 
There is **one binding, with interface-specific proxies** (D5) — remoting must not re-couple the three brains.

Three operations, all addressed to one component (a multi-component endpoint disambiguates by `component_id`):

| Operation | Purpose | Idempotent? |
|-----------|---------|-------------|
| `describe` | return the endpoint's **remote descriptor** (§4) | yes |
| `health` | liveness check | yes |
| `invoke` | run one interface operation (e.g. `decide`) | per the operation's declared semantics (§5) |

## 2. Request envelope

An `invoke` request carries:

- `component_id` — which component at the endpoint (optional for single-component endpoints).
- `interface` — the runtime-interface name (`dcp.control_policy`, …) and `interface_version`.
- `binding_version` — the transport-binding protocol version (distinct from `interface_version`, D18).
- `operation` — the interface operation (`decide`, `text`, …).
- `invocation_id` — a caller-chosen unique id (the unit of ownership; §5).
- `retry_safe` — whether re-issuing this exact `invocation_id` is safe (§5).
- `payload` — the operation input, already **projected by the owner** (§6).

## 3. Response envelope

- `invocation_id` — echoes the request.
- `ok` — success flag.
- `result` — the operation output on success (e.g. a serialized `OrchestratorAction`).
- `error` — `{code, message}` on failure. Codes: `unknown_operation`, `unsupported_interface`,
  `version_mismatch`, `bad_request`, `internal`.

## 4. Remote descriptor & verification (D20)

`describe` returns the **actually deployed** identity — not merely the published manifest:

- `component` — `namespace`, `name`, `version`, `kind`.
- `interface` — `name`, `version`.
- `binding` — `protocol`, `version`.
- `deployment` (optional) — `revision`, `artifact_digests`, `config_fingerprint`.

On `connect`, the proxy MUST verify the descriptor's `component` (namespace/name/version), `interface` (name/version), and `binding` against the **published manifest** and the selected remote access mode.
A mismatch is rejected. The `deployment` fingerprint is recorded for replay/audit; it does not gate `connect`.

## 5. Reliability — single-attempt best-effort (D13)

v1 makes **no exactly-/at-most-once guarantee**:

- One transport attempt per `invoke`. **No automatic retry.**
- After an ambiguous transport failure, **duplicate execution is possible**; the caller MAY start a *new* `invocation_id` explicitly.
- Each operation declares its semantics — `side_effects: none|local|external` and `retry_safe: bool`. `side-effect-free ≠ deterministic ≠ idempotent`: `decide` is normally side-effect-free and retry-safe, but is not guaranteed deterministic.
- `invocation_id` is carried now so a future dedupe/replay contract can be added without a wire break.
- No transparent migration, no distributed transaction. A `version_mismatch` on `interface_version` or `binding_version` MUST be refused, not coerced.

## 6. Owner-controlled context projection (D12)

The manifest's `context_requirements` only *ask*. The **owner** builds the `ContextProjection` that decides what of a `DialogueContext` is transmitted:

```
Full DialogueContext ──(owner ContextProjection)──▶ RemoteComponentContext ──serialize + audit──▶ remote
```

- Fields are individually gated: `transcript` (full|summary|omit) and `roster`
  (full|roles_only|omit) in v1. (Only knobs that actually project are exposed — no no-op fields.)
- What is **recorded** is owner-configurable: the projection *policy* (fields + a payload **digest** + byte size + destination + timestamp) is always recordable; full-payload retention is explicit and subject to the dialogue's privacy/retention policy.
- Remoting a control policy or agent sends dialogue content beyond the owner's boundary — a privacy decision the owner makes, not the component author.

## 7. Security considerations

**The manifest — not the owner — chooses the endpoint.** 
A component you resolve declares its own `endpoint` and requested `credential_slot`, so a hostile manifest could try to make your client send a secret to a server it controls (a confused deputy). 
Mitigations enforced by the SDK:

- Endpoints are `http(s)`-only (schema-validated) — no `file://`/`ftp://` LFI/SSRF via the URL loader.
- An **env-resolved** bearer credential (`$DCP_CRED_<SLOT>`) is attached **only to an `https://` endpoint**. An explicit `--token` is the owner's deliberate choice and is always honored.
- Server-side bearer comparison is constant-time.

**Residual risks the operator owns:** `http://` to internal/metadata IPs is still reachable (no blocklist); resolving+materializing a *local* component runs its code by design (import + optional `pip install`) — review a manifest's `expected_side_effects` before `install`. Prefer components you trust, pinned by digest, over an owner-controlled endpoint.

## 8. Excluded in v1

- Remote **oversight** — delegating governance off the owner's machine (D9). Never selected implicitly; a future opt-in needs declared exposure, a failure policy, and an owner-side fallback.
