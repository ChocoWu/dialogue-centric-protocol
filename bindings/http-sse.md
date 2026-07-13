# DCP Remote Component Binding — HTTP/SSE mapping

**Status:** normative for Phase 7C. Concrete mapping of the transport-independent
[remote-component.md](remote-component.md) onto HTTP + Server-Sent Events. This is an adapter (D6): the semantic core does not depend on it.

## Routes

| Operation | Method + path | Body | Response |
|-----------|---------------|------|----------|
| `describe` | `GET /component` (or `GET /component/{component_id}`) | — | `RemoteDescriptor` JSON |
| `health` | `GET /health` | — | `{"ok": true}` |
| `invoke` | `POST /invoke` | request envelope JSON | response envelope JSON |
| `invoke` (streaming, 7C.2) | `POST /invoke` with `Accept: text/event-stream` | request envelope | SSE `data:` frames; final `event: result` |

## Headers

- `Authorization: Bearer <token>` — the credential the manifest declared via a `credential_slot`, supplied by the **owner** (§ credentials below). Never carried in the manifest.
- `Content-Type: application/json` for request/response envelopes.
- `DCP-Binding-Version: <major.minor>` — the binding protocol version; a server that cannot satisfy it responds `409` with `error.code = "version_mismatch"`.

## Status codes

| Code | Meaning |
|------|---------|
| `200` | `invoke` / `describe` / `health` succeeded (envelope `ok` may still be `false` for app errors) |
| `400` | malformed envelope (`error.code = "bad_request"`) |
| `401` | missing/invalid bearer token |
| `404` | unknown `component_id` |
| `409` | `interface_version` / `binding_version` mismatch (`version_mismatch`) |
| `501` | operation/interface not implemented by this endpoint |

## Streaming (7C.2)

For agent contributions, `POST /invoke` with `Accept: text/event-stream` returns incremental `data:` frames (partial output), then a terminal `event: result` frame carrying the response envelope. 
`Last-Event-ID` MAY be used to resume a dropped stream; per D13 there is no dedupe guarantee, so a resumed stream may repeat frames.

## Credentials

The bearer token is resolved **owner-side** from the `credential_slot` the manifest declares (D22): the owner maps the slot to an env var / keyring entry in their own config; the client reads it and sets the `Authorization` header. 
The token is never logged and never written to a lockfile.

## Reliability

Single-attempt best-effort (D13): the client issues one HTTP request per `invoke` and does **not** auto-retry on timeout. The caller decides whether to start a fresh `invocation_id`.
