"""Phase 7C.1b — hosting a component over HTTP + the HttpRemoteTransport client loop.

Hermetic: the client's ``opener`` is bridged to Starlette's in-process ``TestClient`` — real HTTP
semantics (status codes, headers, JSON) without a socket.
"""

from __future__ import annotations

from typing import Any

import pytest
from starlette.testclient import TestClient

from dcp import schema as s
from dcp.component import (
    ComponentManifest,
    ComponentServer,
    HttpRemoteTransport,
    connect,
    resolve,
)
from dcp.component.remote import Deployment, RemoteRequest
from dcp.errors import RemoteComponentError
from dcp.orchestration import OrchestratorAction
from dcp.schema import TerminationStatus


def _manifest() -> ComponentManifest:
    return ComponentManifest.model_validate({
        "schema_version": "1.0",
        "component": {"namespace": "alice", "name": "orch", "version": "1.0.0",
                      "kind": "control_policy"},
        "interface": {"name": "dcp.control_policy", "version": "1.0"},
        "access_modes": [{
            "type": "remote",
            "binding": {"protocol": "dcp-http", "version": "1.0"},
            "endpoint": "https://alice.example/dcp",
            "auth": {"type": "bearer", "credential_slot": "token"},
        }],
    })


def _decide(payload: dict[str, Any]) -> OrchestratorAction:
    spoken = {m["role_id"] for m in payload.get("transcript", [])}
    for role in payload["roles"]:
        if role["role_id"] not in spoken:
            return OrchestratorAction(action="select_speaker", target_role_id=role["role_id"])
    return OrchestratorAction(action="stop", status=TerminationStatus.DONE)


def _opener(client: TestClient):  # type: ignore[no-untyped-def]
    def open_(method: str, url: str, body: bytes | None, headers: dict[str, str], timeout: float):
        path = url.split("dcp", 1)[-1] or "/"       # strip the fake base, keep the route path
        r = client.request(method, path, content=body, headers=headers)
        return r.status_code, r.content
    return open_


def _server(**kw: Any) -> ComponentServer:
    return ComponentServer(_manifest(), decide=_decide, **kw)


# --- server (direct, via TestClient) ---------------------------------------------------

def test_describe_returns_the_descriptor() -> None:
    client = TestClient(_server().asgi())
    body = client.get("/component").json()
    assert body["component"]["name"] == "orch"
    assert body["interface"]["name"] == "dcp.control_policy"
    assert body["binding"] == {"protocol": "dcp-http", "version": "1.0"}


def test_health_ok() -> None:
    assert TestClient(_server().asgi()).get("/health").json() == {"ok": True}


def test_invoke_runs_the_handler() -> None:
    client = TestClient(_server().asgi())
    req = RemoteRequest(interface="dcp.control_policy", interface_version="1.0",  # type: ignore[arg-type]
                        binding_version="1.0", operation="decide", invocation_id="i1",
                        payload={"roles": [{"role_id": "a"}], "transcript": []})
    body = client.post("/invoke", json=req.model_dump(mode="json")).json()
    assert body["ok"] is True
    assert body["result"]["action"] == "select_speaker"
    assert body["result"]["target_role_id"] == "a"


def test_invoke_version_mismatch_is_409() -> None:
    client = TestClient(_server().asgi())
    req = RemoteRequest(interface="dcp.control_policy", interface_version="9.9",  # type: ignore[arg-type]
                        binding_version="1.0", operation="decide", invocation_id="i", payload={})
    r = client.post("/invoke", json=req.model_dump(mode="json"))
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_mismatch"


def test_invoke_requires_bearer_when_configured() -> None:
    client = TestClient(_server(token="secret").asgi())
    req = RemoteRequest(interface="dcp.control_policy", interface_version="1.0",  # type: ignore[arg-type]
                        binding_version="1.0", operation="decide", invocation_id="i",
                        payload={"roles": [], "transcript": []})
    assert client.post("/invoke", json=req.model_dump(mode="json")).status_code == 401
    ok = client.post("/invoke", json=req.model_dump(mode="json"),
                     headers={"authorization": "Bearer secret"})
    assert ok.status_code == 200


# --- client ↔ server over HttpRemoteTransport ------------------------------------------

async def test_http_transport_describe_and_invoke() -> None:
    client = TestClient(_server().asgi())
    transport = HttpRemoteTransport("https://alice.example/dcp", opener=_opener(client))
    desc = await transport.describe()
    assert desc.component.name == "orch"
    req = RemoteRequest(interface="dcp.control_policy", interface_version="1.0",  # type: ignore[arg-type]
                        binding_version="1.0", operation="decide", invocation_id="i",
                        payload={"roles": [{"role_id": "a"}], "transcript": []})
    resp = await transport.invoke(req)
    assert resp.ok and resp.result["target_role_id"] == "a"


async def test_http_transport_unauthorized_raises() -> None:
    client = TestClient(_server(token="secret").asgi())
    transport = HttpRemoteTransport("https://alice.example/dcp", opener=_opener(client))  # no token
    req = RemoteRequest(interface="dcp.control_policy", interface_version="1.0",  # type: ignore[arg-type]
                        binding_version="1.0", operation="decide", invocation_id="i", payload={})
    with pytest.raises(RemoteComponentError):
        await transport.invoke(req)


async def test_connect_over_http_verifies_and_drives_a_decision() -> None:
    tc = TestClient(_server(deployment=Deployment(revision="sha256:abc")).asgi())
    plan = resolve("installed://alice/orch",
                   resolvers=[_FixedResolver(_manifest())], mode="remote")
    transport = HttpRemoteTransport("https://alice.example/dcp", opener=_opener(tc))
    policy = await connect(plan, transport)                 # verifies the descriptor (D20)

    action = await policy.decide(_context())                # a real remote round-trip over HTTP
    assert action.action == "select_speaker" and action.target_role_id == "a"


# --- helpers ---------------------------------------------------------------------------

class _FixedResolver:
    def __init__(self, manifest: ComponentManifest) -> None:
        self._m = manifest

    def handles(self, ref: Any) -> bool:
        return True

    def locate(self, ref: Any) -> ComponentManifest:
        return self._m


def _context() -> Any:
    from dcp.orchestration import DialogueContext
    from dcp.provider import MockProvider

    template = s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done"),
        roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                      response_requirement=s.ResponseRequirement.REQUIRED)])
    inst = s.DialogueInstance(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@o", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0",
        status=s.InstanceStatus.RUNNING, turn=0, roster=[], messages=[], events=[],
        open_gates=[], pending_inputs=[], budget=s.Budget(turns_used=0))
    return DialogueContext.from_instance(inst, template, MockProvider())
