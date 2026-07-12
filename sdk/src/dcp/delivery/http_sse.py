"""HTTP API + SSE binding for the Registry (SPEC §3.5; A3).

REST endpoints wrap the Registry & Hosting ops (register/instantiate/join/leave/restore); an SSE
endpoint streams an instance's event log with **replay-then-tail** semantics (SPEC §2.9, D3): a
subscriber first receives the full history, then live events as they are appended. Starlette is
confined to this module — the semantic core imports nothing here.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import ValidationError
from sse_starlette.sse import EventSourceResponse
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ..errors import AccessError, RegistryError
from ..registry import Registry
from ..schema import (
    DialogueInstance,
    DialogueTemplate,
    Participant,
    TemplateRef,
    TerminationPolicy,
    Visibility,
    is_resumable,
)

#: Poll interval (seconds) while tailing the log for newly appended events.
_TAIL_POLL_SECONDS = 0.25


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def _instance_view(inst: DialogueInstance) -> dict[str, Any]:
    """Instance JSON plus the derived ``resumable`` hint (SPEC §2.9, D3)."""
    view = inst.model_dump(mode="json")
    view["resumable"] = is_resumable(inst.status)
    return view


async def _body(request: Request) -> dict[str, Any]:
    data = await request.json()
    if not isinstance(data, dict):
        raise ValueError("request body must be a JSON object")
    return data


def build_app(registry: Registry) -> Starlette:
    """Build a Starlette app exposing ``registry`` over HTTP + SSE."""

    async def register_template(request: Request) -> Response:
        try:
            template = DialogueTemplate.model_validate(await _body(request))
        except (ValidationError, ValueError) as exc:
            return _error(422, str(exc))
        try:
            registry.register_template(template)
        except RegistryError as exc:                     # immutability conflict (SPEC §2.1)
            return _error(409, str(exc))
        return JSONResponse(template.model_dump(mode="json"), status_code=201)

    async def list_templates(request: Request) -> Response:
        return JSONResponse([t.model_dump(mode="json") for t in registry.list_templates()])

    async def get_template(request: Request) -> Response:
        template = registry.get_template(
            request.path_params["template_id"], request.path_params["version"]
        )
        if template is None:
            return _error(404, "unknown template")
        return JSONResponse(template.model_dump(mode="json"))

    async def generate_template(request: Request) -> Response:
        try:
            data = await _body(request)
            query = data["query"]
        except (ValueError, KeyError) as exc:
            return _error(422, f"invalid generate request: {exc}")
        try:
            draft = await registry.generate_template(query, constraints=data.get("constraints"))
        except RegistryError as exc:                     # capability not enabled (SPEC §2.2)
            return _error(501, str(exc))
        return JSONResponse(draft.model_dump(mode="json"))     # a DRAFT — not yet registered

    async def server_info(request: Request) -> Response:
        return JSONResponse(registry.server_info().model_dump(mode="json"))

    async def register_participant(request: Request) -> Response:
        try:
            participant = Participant.model_validate(await _body(request))
        except (ValidationError, ValueError) as exc:
            return _error(422, str(exc))
        try:
            registry.register_participant(participant)
        except RegistryError as exc:
            return _error(409, str(exc))
        return JSONResponse(participant.model_dump(mode="json"), status_code=201)

    async def list_participants(request: Request) -> Response:
        flag = request.query_params.get("discoverable", "").lower() in ("true", "1", "yes")
        parts = registry.list_participants(discoverable_only=flag)
        return JSONResponse([p.model_dump(mode="json") for p in parts])

    async def get_participant(request: Request) -> Response:
        participant = registry.get_participant(request.path_params["participant_id"])
        if participant is None:
            return _error(404, "unknown participant")
        return JSONResponse(participant.model_dump(mode="json"))

    async def instantiate(request: Request) -> Response:
        try:
            data = await _body(request)
            ref = TemplateRef(template_id=data["template_id"], version=data["version"])
            owner = data["owner"]
        except (ValidationError, ValueError, KeyError) as exc:
            return _error(422, f"invalid instantiate request: {exc}")
        visibility = Visibility(data["visibility"]) if data.get("visibility") else None
        brief = data.get("brief")
        if brief is not None and not isinstance(brief, dict):
            return _error(422, "invalid instantiate request: 'brief' must be an object")
        goal = data.get("goal")
        if goal is not None and not isinstance(goal, str):
            return _error(422, "invalid instantiate request: 'goal' must be a string")
        try:
            termination = (
                TerminationPolicy.model_validate(data["termination_policy"])
                if data.get("termination_policy") is not None else None)
        except (ValidationError, ValueError) as exc:
            return _error(422, f"invalid instantiate request: 'termination_policy' {exc}")
        try:
            inst = registry.instantiate(
                ref, owner=owner, visibility=visibility, goal=goal, brief=brief,
                termination=termination)
        except RegistryError as exc:                     # unknown template
            return _error(404, str(exc))
        return JSONResponse(_instance_view(inst), status_code=201)

    async def list_instances(request: Request) -> Response:
        caller = request.query_params.get("caller")
        insts = registry.list_instances(caller=caller)
        return JSONResponse([_instance_view(i) for i in insts])

    async def get_instance(request: Request) -> Response:
        try:
            inst = registry.restore(request.path_params["instance_id"])
        except RegistryError as exc:
            return _error(404, str(exc))
        return JSONResponse(_instance_view(inst))

    async def join(request: Request) -> Response:
        instance_id = request.path_params["instance_id"]
        try:
            participant_id = (await _body(request))["participant_id"]
        except (ValueError, KeyError) as exc:
            return _error(422, f"invalid join request: {exc}")
        try:
            inst = registry.join(instance_id, participant_id=participant_id)
        except AccessError as exc:                       # visibility/grant denial (SPEC §2.5)
            return _error(403, str(exc))
        except RegistryError as exc:
            return _error(404, str(exc))
        return JSONResponse(_instance_view(inst))

    async def leave(request: Request) -> Response:
        instance_id = request.path_params["instance_id"]
        try:
            participant_id = (await _body(request))["participant_id"]
        except (ValueError, KeyError) as exc:
            return _error(422, f"invalid leave request: {exc}")
        registry.leave(instance_id, participant_id=participant_id)
        return JSONResponse({"instance_id": instance_id, "left": participant_id})

    async def events(request: Request) -> Response:
        instance_id = request.path_params["instance_id"]
        try:
            registry.restore(instance_id)                # existence check up front → clean 404
        except RegistryError as exc:
            return _error(404, str(exc))
        tail = request.query_params.get("tail", "true").lower() not in ("false", "0", "no")

        async def stream() -> Any:
            cursor = 0
            while True:
                log = registry.restore(instance_id).events
                for event in log[cursor:]:
                    yield {"event": event.type.value, "data": event.model_dump_json()}
                cursor = len(log)
                if not tail:                             # finite stream: stop once caught up
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(_TAIL_POLL_SECONDS)

        return EventSourceResponse(stream())

    routes = [
        Route("/", server_info, methods=["GET"]),
        Route("/templates", register_template, methods=["POST"]),
        Route("/templates", list_templates, methods=["GET"]),
        Route("/templates/generate", generate_template, methods=["POST"]),
        Route("/templates/{template_id}/versions/{version}", get_template, methods=["GET"]),
        Route("/participants", register_participant, methods=["POST"]),
        Route("/participants", list_participants, methods=["GET"]),
        Route("/participants/{participant_id}", get_participant, methods=["GET"]),
        Route("/instances", instantiate, methods=["POST"]),
        Route("/instances", list_instances, methods=["GET"]),
        Route("/instances/{instance_id}", get_instance, methods=["GET"]),
        Route("/instances/{instance_id}/join", join, methods=["POST"]),
        Route("/instances/{instance_id}/leave", leave, methods=["POST"]),
        Route("/instances/{instance_id}/events", events, methods=["GET"]),
    ]
    return Starlette(routes=routes)


class HttpSseDelivery:
    """HTTP + SSE delivery binding over a Registry (SPEC §3.5). Implements :class:`Delivery`."""

    def __init__(self, registry: Registry) -> None:
        self._registry = registry
        self._app = build_app(registry)

    def asgi(self) -> Starlette:
        return self._app

    def run(self, host: str = "127.0.0.1", port: int = 8000) -> None:  # pragma: no cover
        """Serve the app with uvicorn (blocking). Not exercised by the hermetic test suite."""
        import uvicorn

        uvicorn.run(self._app, host=host, port=port)


__all__ = ["build_app", "HttpSseDelivery"]
