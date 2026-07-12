"""Phase 7C.2a — RemoteAgent: a ModelProvider proxy that contributes turns remotely.

Uses ``LoopbackTransport``/``ComponentServer`` in-process. The acceptance loop runs a real dialogue
whose agent is remote; the descriptor is verified on connect (D20) and the declared ``state`` gates
retry-safety (D13/D20).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel
from starlette.testclient import TestClient

from dcp import schema as s
from dcp.component import (
    ComponentManifest,
    ComponentServer,
    HttpRemoteTransport,
    LoopbackTransport,
    RemoteAgent,
    connect,
    resolve,
)
from dcp.component.remote import OrchestratorAction, RemoteComponentClient
from dcp.errors import RemoteComponentError

_TS = datetime(2026, 7, 12, tzinfo=UTC)


def _manifest(*, state_mode: str = "stateless") -> ComponentManifest:
    return ComponentManifest.model_validate({
        "schema_version": "1.0",
        "component": {"namespace": "alice", "name": "scout", "version": "1.0.0", "kind": "agent"},
        "interface": {"name": "dcp.agent_definition", "version": "1.0"},
        "capabilities": ["dcp.agent.search"],
        "spec": {"state": {"mode": state_mode}},
        "access_modes": [{
            "type": "remote",
            "binding": {"protocol": "dcp-http", "version": "1.0"},
            "endpoint": "https://alice.example/scout",
            "auth": {"type": "bearer", "credential_slot": "token"},
        }],
    })


def _descriptor() -> Any:
    from dcp.component.remote import descriptor_from_manifest
    return descriptor_from_manifest(_manifest())


class _FixedResolver:
    def __init__(self, m: ComponentManifest) -> None:
        self._m = m

    def handles(self, ref: Any) -> bool:
        return True

    def locate(self, ref: Any) -> ComponentManifest:
        return self._m


# --- RemoteAgent implements the ModelProvider interface --------------------------------

async def test_remote_agent_text_calls_generate() -> None:
    class _T:
        async def describe(self) -> Any:
            return _descriptor()

        async def health(self) -> bool:
            return True

        async def invoke(self, request: Any) -> Any:
            from dcp.component.remote import RemoteResponse
            assert request.operation == "generate"
            return RemoteResponse(invocation_id=request.invocation_id, ok=True,
                                  result={"text": f"scouted: {request.payload['content']}"})

    agent = RemoteAgent(RemoteComponentClient(_T(), manifest=_manifest()))
    out = await agent.text(instructions="search", content="quantum error correction")
    assert out == "scouted: quantum error correction"


async def test_remote_agent_structured_validates_the_schema() -> None:
    class _Finding(BaseModel):
        title: str

    class _T:
        async def describe(self) -> Any:
            return _descriptor()

        async def health(self) -> bool:
            return True

        async def invoke(self, request: Any) -> Any:
            from dcp.component.remote import RemoteResponse
            assert "schema" in request.payload            # the JSON Schema is sent
            return RemoteResponse(invocation_id=request.invocation_id, ok=True,
                                  result={"value": {"title": "a paper"}})

    agent = RemoteAgent(RemoteComponentClient(_T(), manifest=_manifest()))
    got = await agent.structured(instructions="i", content="c", schema=_Finding)
    assert got == _Finding(title="a paper")


# --- state gates retry-safety (D13/D20) ------------------------------------------------

def _plan(m: ComponentManifest) -> Any:
    return resolve("installed://alice/scout", resolvers=[_FixedResolver(m)], mode="remote")


async def test_connect_agent_stateless_is_retry_safe() -> None:
    from dcp.component import AgentDefinition

    agent = await connect(_plan(_manifest(state_mode="stateless")),
                          LoopbackTransport(descriptor=_descriptor(),
                                            decide=lambda _p: OrchestratorAction(action="stop")))
    assert isinstance(agent, AgentDefinition)                  # D2: an agent → a definition
    assert isinstance(agent.provider, RemoteAgent)
    assert agent.provider._retry_safe is True and agent.capabilities == ("dcp.agent.search",)


async def test_connect_agent_invocation_scoped_is_not_retry_safe() -> None:
    from dcp.component import AgentDefinition

    agent = await connect(_plan(_manifest(state_mode="invocation_scoped")),
                          LoopbackTransport(descriptor=_descriptor(),
                                            decide=lambda _p: OrchestratorAction(action="stop")))
    assert isinstance(agent, AgentDefinition)
    assert isinstance(agent.provider, RemoteAgent) and agent.provider._retry_safe is False


async def test_connect_rejects_dialogue_scoped_agent_in_v1() -> None:
    with pytest.raises(RemoteComponentError):
        await connect(_plan(_manifest(state_mode="dialogue_scoped")),
                      LoopbackTransport(descriptor=_descriptor(),
                                        decide=lambda _p: OrchestratorAction(action="stop")))


# --- server hosts generate/structured --------------------------------------------------

def test_server_hosts_generate_operation() -> None:
    def generate(payload: dict[str, Any]) -> dict[str, str]:
        return {"text": payload["content"].upper()}

    server = ComponentServer(_manifest(), operations={"generate": generate})
    client = TestClient(server.asgi())
    from dcp.component.remote import RemoteRequest
    req = RemoteRequest(interface="dcp.agent_definition", interface_version="1.0",  # type: ignore[arg-type]
                        binding_version="1.0", operation="generate", invocation_id="i",
                        payload={"content": "hi"})
    body = client.post("/invoke", json=req.model_dump(mode="json")).json()
    assert body["ok"] and body["result"] == {"text": "HI"}


# --- the acceptance loop: a remote agent contributes turns in a real dialogue -----------

async def test_remote_agent_contributes_in_a_dialogue() -> None:
    from dcp.orchestration import Orchestrator
    from dcp.provider import MockProvider
    from dcp.state import InstanceHeader, SqlStore

    def generate(payload: dict[str, Any]) -> dict[str, str]:
        return {"text": "remote contribution"}

    tc = TestClient(ComponentServer(_manifest(), operations={"generate": generate}).asgi())
    transport = HttpRemoteTransport("https://alice.example/scout", opener=_opener(tc))
    from dcp.component import AgentDefinition
    agent = await connect(_plan(_manifest()), transport)
    assert isinstance(agent, AgentDefinition)          # drops into agent_providers via delegation

    role = s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                  response_requirement=s.ResponseRequirement.REQUIRED)
    template = s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done", max_turns=2), roles=[role])
    store = SqlStore()
    store.create_instance(InstanceHeader(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@o", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0", created_at=_TS))
    orch = Orchestrator(
        store=store, template=template, instance_id="dlg", cast={"a": "a"},
        participants={"a": s.Participant(participant_id="a", kind=s.RoleKind.AGENT,
                                          display_name="A")},
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"}]),
        agent_providers={"a": agent})   # ← the remote agent as this participant's provider
    inst = await orch.run()
    assert [m.content for m in inst.messages] == ["remote contribution"]


def _opener(client: TestClient):  # type: ignore[no-untyped-def]
    def open_(method: str, url: str, body: bytes | None, headers: dict[str, str], timeout: float):
        path = url.split("scout", 1)[-1] or "/"
        r = client.request(method, path, content=body, headers=headers)
        return r.status_code, r.content
    return open_
