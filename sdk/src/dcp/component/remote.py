"""Remote component binding (Phase 7C) — the transport-independent core.

One transport, interface-specific proxies (D5): a ``RemoteControlPolicy`` implements the local
``ControlPolicy`` seam by exchanging envelopes with a provider's server. The wire semantics are in
``bindings/remote-component.md``; the HTTP mapping in ``bindings/http-sse.md``. Here we define the
envelopes, the transport interface, an in-process ``LoopbackTransport`` (tests + same-process use),
the ``RemoteComponentClient`` (descriptor verification D20, single-attempt reliability D13), and the
``ControlPolicy`` proxy. Remote **oversight** is excluded (D9); ``RemoteAgent`` is 7C.2.
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
import uuid
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ValidationError

from ..errors import RemoteComponentError
from ..orchestration import OrchestratorAction
from ..orchestration.context import DialogueContext
from ..schema.base import DCPModel
from .agent import AgentDefinition, build_agent_definition
from .manifest import (
    AgentSpec,
    ComponentKind,
    ComponentManifest,
    InterfaceName,
    RemoteAccessMode,
)
from .projection import ContextProjection, ProjectionAudit, project_context
from .resolver import ComponentResolutionPlan

M = TypeVar("M", bound=BaseModel)


# --- envelopes (§2–§4 of the binding) --------------------------------------------------

class RemoteError(DCPModel):
    code: str
    message: str = ""


class RemoteRequest(DCPModel):
    interface: InterfaceName
    interface_version: str
    binding_version: str
    operation: str
    invocation_id: str
    retry_safe: bool = True
    component_id: str | None = None
    payload: dict[str, Any] = {}


class RemoteResponse(DCPModel):
    invocation_id: str
    ok: bool
    result: dict[str, Any] | None = None
    error: RemoteError | None = None


class DescriptorComponent(DCPModel):
    namespace: str
    name: str
    version: str
    kind: ComponentKind


class DescriptorInterface(DCPModel):
    name: InterfaceName
    version: str


class DescriptorBinding(DCPModel):
    protocol: str
    version: str


class Deployment(DCPModel):
    revision: str | None = None
    artifact_digests: list[str] = []
    config_fingerprint: str | None = None


class RemoteDescriptor(DCPModel):
    component: DescriptorComponent
    interface: DescriptorInterface
    binding: DescriptorBinding
    deployment: Deployment | None = None


# --- transport -------------------------------------------------------------------------

class RemoteTransport(Protocol):
    """A transport to one remote component. The HTTP/SSE mapping is one implementation."""

    async def describe(self) -> RemoteDescriptor: ...
    async def health(self) -> bool: ...
    async def invoke(self, request: RemoteRequest) -> RemoteResponse: ...


@runtime_checkable
class StreamingTransport(Protocol):
    """A transport that also streams an operation's output incrementally (7C.2b)."""

    def stream(self, request: RemoteRequest) -> AsyncIterator[str]: ...


class LoopbackTransport:
    """In-process transport: serves one component without a network (tests / same-process hosting).

    ``decide`` handles a control policy (projected payload → ``OrchestratorAction``); ``generate``
    handles an agent operation (payload → a result dict); ``stream`` yields incremental text frames.
    """

    def __init__(self, *, descriptor: RemoteDescriptor,
                 decide: Callable[[dict[str, Any]], OrchestratorAction] | None = None,
                 generate: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
                 stream: Callable[[dict[str, Any]], AsyncIterator[str]] | None = None) -> None:
        self._descriptor = descriptor
        self._decide = decide
        self._generate = generate
        self._stream = stream

    async def describe(self) -> RemoteDescriptor:
        return self._descriptor

    async def health(self) -> bool:
        return True

    async def invoke(self, request: RemoteRequest) -> RemoteResponse:
        if request.operation == "decide" and self._decide is not None:
            return RemoteResponse(invocation_id=request.invocation_id, ok=True,
                                  result=self._decide(request.payload).model_dump(mode="json"))
        if self._generate is not None and request.operation in ("generate", "structured"):
            return RemoteResponse(invocation_id=request.invocation_id, ok=True,
                                  result=self._generate(request.payload))
        return RemoteResponse(
            invocation_id=request.invocation_id, ok=False,
            error=RemoteError(code="unknown_operation", message=request.operation))

    async def stream(self, request: RemoteRequest) -> AsyncIterator[str]:
        if self._stream is None:
            raise RemoteComponentError("loopback transport has no stream handler")
        async for frame in self._stream(request.payload):
            yield frame


# --- descriptor verification (D20) -----------------------------------------------------

def verify_descriptor(
    descriptor: RemoteDescriptor, manifest: ComponentManifest, mode: RemoteAccessMode | None = None
) -> None:
    """Reject a deployment whose identity/interface/binding disagrees with the manifest (D20)."""
    c = manifest.component
    d = descriptor.component
    if (d.namespace, d.name, d.version, d.kind) != (c.namespace, c.name, c.version, c.kind):
        raise RemoteComponentError(
            f"remote descriptor identity {d.namespace}/{d.name}@{d.version} != manifest "
            f"{c.namespace}/{c.name}@{c.version}")
    if descriptor.interface.name is not manifest.interface.name \
            or descriptor.interface.version != manifest.interface.version:
        raise RemoteComponentError("remote descriptor interface != manifest interface")
    if mode is not None and (descriptor.binding.protocol != mode.binding.protocol
                             or descriptor.binding.version != mode.binding.version):
        raise RemoteComponentError("remote descriptor binding != selected mode binding")


# --- client ----------------------------------------------------------------------------

class RemoteComponentClient:
    """Envelopes a transport: verify the descriptor (D20), then invoke single-attempt (D13)."""

    def __init__(self, transport: RemoteTransport, *, manifest: ComponentManifest,
                 mode: RemoteAccessMode | None = None) -> None:
        self._transport = transport
        self._manifest = manifest
        self._mode = mode
        self._binding_version = mode.binding.version if mode else "1.0"

    async def verify(self) -> RemoteDescriptor:
        descriptor = await self._transport.describe()
        verify_descriptor(descriptor, self._manifest, self._mode)
        return descriptor

    async def invoke(self, operation: str, payload: dict[str, Any], *,
                     retry_safe: bool = True) -> dict[str, Any]:
        req = RemoteRequest(
            interface=self._manifest.interface.name,
            interface_version=self._manifest.interface.version,
            binding_version=self._binding_version,
            operation=operation,
            invocation_id=uuid.uuid4().hex,      # caller-owned; single attempt, no auto-retry (D13)
            retry_safe=retry_safe,
            component_id=self._mode.component_id if self._mode else None,
            payload=payload,
        )
        resp = await self._transport.invoke(req)
        if resp.invocation_id != req.invocation_id:      # a misrouted / replayed response
            raise RemoteComponentError("remote response invocation_id did not match the request")
        if not resp.ok:
            err = resp.error
            detail = f"{err.code}: {err.message}" if err else "unknown error"
            raise RemoteComponentError(f"remote {operation!r} failed ({detail})")
        return resp.result or {}

    async def stream(self, operation: str, payload: dict[str, Any], *,
                     retry_safe: bool = True) -> AsyncIterator[str]:
        if not isinstance(self._transport, StreamingTransport):
            raise RemoteComponentError("transport does not support streaming")
        req = RemoteRequest(
            interface=self._manifest.interface.name,
            interface_version=self._manifest.interface.version,
            binding_version=self._binding_version, operation=operation,
            invocation_id=uuid.uuid4().hex, retry_safe=retry_safe,
            component_id=self._mode.component_id if self._mode else None, payload=payload)
        async for frame in self._transport.stream(req):
            yield frame


# --- proxies ---------------------------------------------------------------------------

class RemoteControlPolicy:
    """A ``ControlPolicy`` whose ``decide`` runs on a remote server (D5).

    Each ``decide`` transmits an owner-controlled context projection (D12). What was sent is kept
    as an audit and surfaced via :meth:`drain_projection_audits` — the runtime drains and records it
    in the dialogue event log (``EventType.CONTEXT_PROJECTED``).
    """

    def __init__(self, client: RemoteComponentClient, *,
                 projection: ContextProjection | None = None,
                 destination: str | None = None,
                 audit_sink: Callable[[ProjectionAudit], None] | None = None) -> None:
        self._client = client
        self._projection = projection
        self._destination = destination
        self._audit_sink = audit_sink
        self._pending_audits: list[dict[str, object]] = []

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        payload, audit = project_context(ctx, self._projection)   # owner-controlled (D12)
        result = await self._client.invoke("decide", payload, retry_safe=True)
        # record only what actually left the boundary — after a successful send, so a failed
        # invoke doesn't leak a stale audit onto a later turn
        if self._audit_sink is not None:
            self._audit_sink(audit)
        self._pending_audits.append({
            "fields": list(audit.fields),
            "payload_digest": audit.payload_digest,
            "byte_size": audit.byte_size,
            "destination": self._destination,
        })
        return OrchestratorAction.model_validate(result)

    def drain_projection_audits(self) -> list[dict[str, object]]:
        """Return and clear the audits of projections sent since the last drain (D12)."""
        audits, self._pending_audits = self._pending_audits, []
        return audits


class RemoteAgent:
    """A ``ModelProvider`` whose contributions run on a remote server (D5) — a drop-in agent.

    ``text`` calls the remote ``generate`` operation; ``structured`` sends a JSON Schema and
    validates the result. ``retry_safe`` reflects the agent's declared state: only a ``stateless``
    agent is safe to re-issue after an ambiguous failure (D13/D20).
    """

    def __init__(self, client: RemoteComponentClient, *, name: str = "remote",
                 retry_safe: bool = True, capabilities: tuple[str, ...] = ()) -> None:
        self.model = name
        self.capabilities = capabilities
        self._client = client
        self._retry_safe = retry_safe

    async def text(self, *, instructions: str, content: str) -> str:
        result = await self._client.invoke(
            "generate", {"instructions": instructions, "content": content},
            retry_safe=self._retry_safe)
        return str(result.get("text", ""))

    async def structured(self, *, instructions: str, content: str, schema: type[M]) -> M:
        payload = {"instructions": instructions, "content": content,
                   "schema": schema.model_json_schema()}
        result = await self._client.invoke("structured", payload, retry_safe=self._retry_safe)
        if "value" not in result:
            raise RemoteComponentError("remote 'structured' response is missing a 'value' field")
        return schema.model_validate(result["value"])

    async def stream_text(self, *, instructions: str, content: str) -> AsyncIterator[str]:
        """Stream a contribution as incremental text frames (7C.2b), if the transport allows it."""
        async for frame in self._client.stream(
                "generate", {"instructions": instructions, "content": content},
                retry_safe=self._retry_safe):
            yield frame


def _build_remote_agent(
    plan: ComponentResolutionPlan, client: RemoteComponentClient
) -> RemoteAgent:
    manifest = plan.manifest
    spec = manifest.spec
    if isinstance(spec, AgentSpec) and spec.state.mode not in ("stateless", "invocation_scoped"):
        raise RemoteComponentError(
            f"v1 remote agent state must be stateless|invocation_scoped, got "
            f"{spec.state.mode!r} (D20)")
    retry_safe = not isinstance(spec, AgentSpec) or spec.state.mode == "stateless"
    name = f"{manifest.component.namespace}/{manifest.component.name}"
    return RemoteAgent(client, name=name, retry_safe=retry_safe,
                       capabilities=tuple(manifest.capabilities))


async def connect(
    plan: ComponentResolutionPlan, transport: RemoteTransport, *,
    projection: ContextProjection | None = None,
) -> RemoteControlPolicy | RemoteAgent | AgentDefinition:
    """Verify a remote deployment against the plan and return an interface-specific proxy (D20).

    ``control_policy`` → ``RemoteControlPolicy``; ``model_provider`` → ``RemoteAgent`` (a provider
    proxy); ``agent`` → an ``AgentDefinition`` (identity + the ``RemoteAgent`` as its provider, D2).
    """
    mode = plan.selected_mode
    if not isinstance(mode, RemoteAccessMode):
        raise RemoteComponentError("connect requires a plan whose selected mode is remote")
    kind = plan.manifest.component.kind
    if kind is ComponentKind.OVERSIGHT_POLICY:
        raise RemoteComponentError("remote oversight is excluded in v1 (D9: governance stays home)")

    client = RemoteComponentClient(transport, manifest=plan.manifest, mode=mode)
    await client.verify()
    if kind is ComponentKind.CONTROL_POLICY:
        return RemoteControlPolicy(client, projection=projection, destination=mode.endpoint)
    if kind is ComponentKind.MODEL_PROVIDER:
        return _build_remote_agent(plan, client)
    if kind is ComponentKind.AGENT:
        return build_agent_definition(plan.manifest, _build_remote_agent(plan, client))
    raise RemoteComponentError(f"remote {kind.value!r} proxy is not supported")


# --- HTTP transport (the concrete binding; bindings/http-sse.md) -----------------------

#: A blocking HTTP call: (method, url, body, headers, timeout) -> (status, body-bytes).
HttpOpener = Callable[[str, str, bytes | None, dict[str, str], float], tuple[int, bytes]]
#: A streaming HTTP call yielding raw response lines (SSE frames).
StreamOpener = Callable[[str, str, bytes | None, dict[str, str], float], AsyncIterator[bytes]]


def _urllib_opener(
    method: str, url: str, body: bytes | None, headers: dict[str, str], timeout: float
) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)   # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310 (scheme is http(s))
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:                # an HTTP error status — caller reads it
        return int(exc.code), exc.read()
    except urllib.error.URLError as exc:                 # unreachable / DNS / TLS
        raise RemoteComponentError(f"remote endpoint unreachable ({exc.reason})") from exc


async def _urllib_stream_opener(
    method: str, url: str, body: bytes | None, headers: dict[str, str], timeout: float
) -> AsyncIterator[bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)   # noqa: S310
    try:
        resp = await asyncio.to_thread(lambda: urllib.request.urlopen(req, timeout=timeout))  # noqa: S310
    except urllib.error.HTTPError as exc:
        raise RemoteComponentError(f"remote stream failed (HTTP {exc.code})") from exc
    except urllib.error.URLError as exc:
        raise RemoteComponentError(f"remote endpoint unreachable ({exc.reason})") from exc
    try:
        while True:
            line = await asyncio.to_thread(resp.readline)
            if not line:
                break
            yield line
    finally:
        resp.close()


class HttpRemoteTransport:
    """A :class:`RemoteTransport` over HTTP (bindings/http-sse.md). Single attempt, no retry (D13).

    ``opener`` is injectable so the client↔server loop is testable in-process (e.g. via Starlette's
    ``TestClient``); the default uses ``urllib``.
    """

    def __init__(self, endpoint: str, *, token: str | None = None,
                 opener: HttpOpener | None = None, stream_opener: StreamOpener | None = None,
                 timeout: float = 30.0) -> None:
        self._base = endpoint.rstrip("/")
        self._token = token
        self._opener = opener or _urllib_opener
        self._stream_opener = stream_opener or _urllib_stream_opener
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        if self._token:                                  # bearer from the owner's credential (D22)
            headers["authorization"] = f"Bearer {self._token}"
        return headers

    async def _call(self, method: str, path: str, body: bytes | None) -> tuple[int, bytes]:
        return await asyncio.to_thread(
            self._opener, method, self._base + path, body, self._headers(), self._timeout)

    async def describe(self) -> RemoteDescriptor:
        status, body = await self._call("GET", "/component", None)
        if status != 200:
            raise RemoteComponentError(f"describe failed (HTTP {status})")
        return RemoteDescriptor.model_validate_json(body)

    async def health(self) -> bool:
        status, _ = await self._call("GET", "/health", None)
        return status == 200

    async def invoke(self, request: RemoteRequest) -> RemoteResponse:
        status, body = await self._call("POST", "/invoke", request.model_dump_json().encode())
        if status == 401:
            raise RemoteComponentError("remote invoke unauthorized (HTTP 401)")
        try:                                              # a 5xx/HTML body isn't an envelope
            return RemoteResponse.model_validate_json(body)
        except ValidationError as exc:
            raise RemoteComponentError(
                f"remote invoke returned a non-envelope response (HTTP {status})") from exc

    async def stream(self, request: RemoteRequest) -> AsyncIterator[str]:
        headers = {**self._headers(), "accept": "text/event-stream"}
        body = request.model_dump_json().encode()
        event: str | None = None
        async for raw in self._stream_opener("POST", self._base + "/invoke", body, headers,
                                             self._timeout):
            line = raw.decode("utf-8").rstrip("\r\n")
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = line[len("data:"):].strip()
                if event == "chunk":
                    yield str(json.loads(data).get("text", ""))
                elif event == "result":
                    return                                # terminal frame — stream complete
            elif line == "":
                event = None                              # SSE frame boundary
        raise RemoteComponentError("remote stream ended before its terminal result frame")


def descriptor_from_manifest(
    manifest: ComponentManifest, *, deployment: Deployment | None = None
) -> RemoteDescriptor:
    """Build the remote descriptor a server advertises for ``manifest`` (D20)."""
    remote = next((m for m in manifest.access_modes if isinstance(m, RemoteAccessMode)), None)
    protocol, version = (remote.binding.protocol, remote.binding.version) if remote \
        else ("dcp-http", "1.0")
    c = manifest.component
    return RemoteDescriptor(
        component=DescriptorComponent(namespace=c.namespace, name=c.name, version=c.version,
                                      kind=c.kind),
        interface=DescriptorInterface(name=manifest.interface.name,
                                      version=manifest.interface.version),
        binding=DescriptorBinding(protocol=protocol, version=version),
        deployment=deployment,
    )


def resolve_credential(mode: RemoteAccessMode, *, token: str | None = None,
                       env: Mapping[str, str] | None = None) -> str | None:
    """Resolve the bearer owner-side: an explicit ``token`` else ``$DCP_CRED_<SLOT>`` (D22).

    Security: an env credential is auto-attached **only to an ``https://`` endpoint**. Because the
    manifest — not the owner — chooses the endpoint, auto-sending a secret to a plaintext (or
    attacker-chosen) ``http://`` endpoint would be a confused-deputy leak. An explicit ``token`` is
    the owner's deliberate choice and is always honored.
    """
    if token:
        return token
    if mode.auth is None or not mode.endpoint.startswith("https://"):
        return None
    e = os.environ if env is None else env
    return e.get(f"DCP_CRED_{mode.auth.credential_slot.upper()}")


def http_transport(plan: ComponentResolutionPlan, *, token: str | None = None,
                   opener: HttpOpener | None = None) -> HttpRemoteTransport:
    """Build an :class:`HttpRemoteTransport` for a plan's remote mode (endpoint + credential)."""
    mode = plan.selected_mode
    if not isinstance(mode, RemoteAccessMode):
        raise RemoteComponentError("http_transport requires a plan whose selected mode is remote")
    return HttpRemoteTransport(mode.endpoint, token=resolve_credential(mode, token=token),
                               opener=opener)


__all__ = [
    "RemoteError",
    "RemoteRequest",
    "RemoteResponse",
    "DescriptorComponent",
    "DescriptorInterface",
    "DescriptorBinding",
    "Deployment",
    "RemoteDescriptor",
    "RemoteTransport",
    "StreamingTransport",
    "LoopbackTransport",
    "verify_descriptor",
    "RemoteComponentClient",
    "RemoteControlPolicy",
    "RemoteAgent",
    "connect",
    "HttpOpener",
    "StreamOpener",
    "HttpRemoteTransport",
    "descriptor_from_manifest",
    "resolve_credential",
    "http_transport",
]
