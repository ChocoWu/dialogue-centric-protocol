"""Component hosting (Phase 7C) — serve a component over HTTP so others can connect.

The provider side of the remote binding: a small Starlette app exposing ``GET /component`` (the
descriptor, D20), ``GET /health``, and ``POST /invoke`` (bindings/http-sse.md). It hosts a
per-operation dispatch of **payload handlers** — the wire contract is the projected payload, not the
local ``DialogueContext`` type (a control policy's ``decide``) nor a Python signature (an agent's
``generate`` / ``structured``). Bearer auth is optional; the token is supplied by the owner, never
carried in a manifest (D22).
"""

from __future__ import annotations

import hmac
import json
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any

from pydantic import BaseModel, ValidationError
from sse_starlette.sse import EventSourceResponse
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ..orchestration import OrchestratorAction
from .manifest import ComponentManifest
from .remote import (
    Deployment,
    RemoteError,
    RemoteRequest,
    RemoteResponse,
    descriptor_from_manifest,
)

#: A hosted operation: the request payload → a JSON-able result (a dict or a pydantic model).
OperationHandler = Callable[[dict[str, Any]], Any]
#: A hosted streaming operation: the request payload → incremental text frames (7C.2b).
StreamHandler = Callable[[dict[str, Any]], AsyncIterator[str]]
#: A hosted control operation (convenience): the projected payload → an OrchestratorAction.
DecideHandler = Callable[[dict[str, Any]], OrchestratorAction]


def _serialize(result: Any) -> dict[str, Any]:
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    if isinstance(result, Mapping):
        return dict(result)
    raise TypeError(f"operation handler returned a non-serializable result: {type(result)!r}")


class ComponentServer:
    """Hosts one component's runtime operations behind the HTTP binding.

    Pass ``operations={name: handler}`` (each handler: payload → dict|model), or the ``decide=``
    convenience for a control policy. An agent hosts ``generate`` (and optionally ``structured``).
    """

    def __init__(self, manifest: ComponentManifest, *,
                 operations: Mapping[str, OperationHandler] | None = None,
                 stream_operations: Mapping[str, StreamHandler] | None = None,
                 decide: DecideHandler | None = None,
                 deployment: Deployment | None = None, token: str | None = None) -> None:
        ops: dict[str, OperationHandler] = dict(operations or {})
        if decide is not None:
            ops["decide"] = decide
        self._stream_operations = dict(stream_operations or {})
        if not ops and not self._stream_operations:
            raise ValueError("ComponentServer needs at least one operation (decide=/operations=)")
        self._manifest = manifest
        self._operations = ops
        self._token = token
        self._descriptor = descriptor_from_manifest(manifest, deployment=deployment)

    def _authorized(self, request: Request) -> bool:
        if self._token is None:
            return True
        return hmac.compare_digest(request.headers.get("authorization", ""),
                                   f"Bearer {self._token}")     # constant-time

    async def _component(self, request: Request) -> JSONResponse:
        return JSONResponse(self._descriptor.model_dump(mode="json"))

    async def _health(self, request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def _invoke(self, request: Request) -> Response:
        if not self._authorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        try:
            req = RemoteRequest.model_validate(await request.json())
        except (ValidationError, ValueError):
            return JSONResponse(
                RemoteResponse(invocation_id="", ok=False,
                               error=RemoteError(code="bad_request")).model_dump(mode="json"),
                status_code=400)
        if req.interface_version != self._manifest.interface.version:
            return self._enveloped(req.invocation_id, "version_mismatch",
                                   f"interface {req.interface_version} != "
                                   f"{self._manifest.interface.version}", 409)
        wants_stream = "text/event-stream" in request.headers.get("accept", "")
        if wants_stream and req.operation in self._stream_operations:
            return EventSourceResponse(self._sse(req))
        handler = self._operations.get(req.operation)
        if handler is None:
            return self._enveloped(req.invocation_id, "unknown_operation", req.operation, 501)
        try:
            result = _serialize(handler(req.payload))
        except Exception as exc:                        # a handler raise → a clean error envelope
            return self._enveloped(req.invocation_id, "internal", str(exc), 500)
        return JSONResponse(RemoteResponse(invocation_id=req.invocation_id, ok=True,
                                           result=result).model_dump(mode="json"))

    async def _sse(self, req: RemoteRequest) -> AsyncIterator[dict[str, str]]:
        """Stream ``chunk`` frames of partial text, then a terminal ``result`` envelope (D13)."""
        chunks: list[str] = []
        async for frame in self._stream_operations[req.operation](req.payload):
            chunks.append(frame)
            yield {"event": "chunk", "data": json.dumps({"text": frame})}
        envelope = RemoteResponse(invocation_id=req.invocation_id, ok=True,
                                  result={"text": "".join(chunks)})
        yield {"event": "result", "data": envelope.model_dump_json()}

    @staticmethod
    def _enveloped(invocation_id: str, code: str, message: str, status: int) -> JSONResponse:
        return JSONResponse(
            RemoteResponse(invocation_id=invocation_id, ok=False,
                           error=RemoteError(code=code, message=message)).model_dump(mode="json"),
            status_code=status)

    def asgi(self) -> Starlette:
        return Starlette(routes=[
            Route("/component", self._component),
            Route("/health", self._health),
            Route("/invoke", self._invoke, methods=["POST"]),
        ])


def serve_component(manifest: ComponentManifest, *,
                    operations: Mapping[str, OperationHandler] | None = None,
                    stream_operations: Mapping[str, StreamHandler] | None = None,
                    decide: DecideHandler | None = None,
                    deployment: Deployment | None = None, token: str | None = None) -> Starlette:
    """Build the ASGI app that hosts ``manifest``'s component (run with uvicorn)."""
    return ComponentServer(manifest, operations=operations, stream_operations=stream_operations,
                           decide=decide, deployment=deployment, token=token).asgi()


__all__ = ["ComponentServer", "serve_component", "OperationHandler", "StreamHandler",
           "DecideHandler"]
