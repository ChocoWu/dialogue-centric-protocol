"""Phase 7C — remote binding core: envelope, descriptor verification, reliability, proxy.

Uses ``LoopbackTransport`` (in-process, no network). The acceptance loop drives a real Orchestrator
with a ``RemoteControlPolicy`` whose ``decide`` runs "remotely".
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from dcp import schema as s
from dcp.component import (
    ComponentManifest,
    LoopbackTransport,
    RemoteComponentClient,
    RemoteControlPolicy,
    RemoteDescriptor,
    connect,
    resolve,
    verify_descriptor,
)
from dcp.component.manifest import RemoteAccessMode
from dcp.component.remote import RemoteError, RemoteRequest, RemoteResponse
from dcp.errors import RemoteComponentError
from dcp.orchestration import OrchestratorAction
from dcp.schema import TerminationStatus
from dcp.state import InstanceHeader

_TS = datetime(2026, 7, 12, tzinfo=UTC)


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


def _descriptor(**over: Any) -> RemoteDescriptor:
    base: dict[str, Any] = {
        "component": {"namespace": "alice", "name": "orch", "version": "1.0.0",
                      "kind": "control_policy"},
        "interface": {"name": "dcp.control_policy", "version": "1.0"},
        "binding": {"protocol": "dcp-http", "version": "1.0"},
    }
    base.update(over)
    return RemoteDescriptor.model_validate(base)


# --- envelope round-trip ---------------------------------------------------------------

def test_envelopes_round_trip() -> None:
    req = RemoteRequest(interface="dcp.control_policy", interface_version="1.0",  # type: ignore[arg-type]
                        binding_version="1.0", operation="decide", invocation_id="x",
                        payload={"k": 1})
    assert RemoteRequest.model_validate(req.model_dump()) == req
    resp = RemoteResponse(invocation_id="x", ok=False, error=RemoteError(code="bad_request"))
    assert RemoteResponse.model_validate(resp.model_dump()) == resp


# --- descriptor verification (D20) -----------------------------------------------------

def test_verify_descriptor_accepts_a_matching_deployment() -> None:
    verify_descriptor(_descriptor(), _manifest(), _mode(_manifest()))   # no raise


def test_verify_descriptor_rejects_a_version_drift() -> None:
    drifted = _descriptor(component={"namespace": "alice", "name": "orch", "version": "2.0.0",
                                     "kind": "control_policy"})
    with pytest.raises(RemoteComponentError):
        verify_descriptor(drifted, _manifest(), _mode(_manifest()))


def test_verify_descriptor_rejects_a_binding_mismatch() -> None:
    bad = _descriptor(binding={"protocol": "dcp-http", "version": "2.0"})
    with pytest.raises(RemoteComponentError):
        verify_descriptor(bad, _manifest(), _mode(_manifest()))


def _mode(manifest: ComponentManifest) -> RemoteAccessMode:
    mode = manifest.access_modes[0]
    assert isinstance(mode, RemoteAccessMode)
    return mode


# --- reliability (D13): a failed invoke raises, no retry -------------------------------

async def test_invoke_failure_raises_and_does_not_retry() -> None:
    calls: list[str] = []

    class _Failing:
        async def describe(self) -> RemoteDescriptor:
            return _descriptor()

        async def health(self) -> bool:
            return True

        async def invoke(self, request: RemoteRequest) -> RemoteResponse:
            calls.append(request.invocation_id)
            return RemoteResponse(invocation_id=request.invocation_id, ok=False,
                                  error=RemoteError(code="internal", message="boom"))

    client = RemoteComponentClient(_Failing(), manifest=_manifest(), mode=_mode(_manifest()))
    with pytest.raises(RemoteComponentError):
        await client.invoke("decide", {})
    assert len(calls) == 1                              # single attempt, no auto-retry


# --- connect guards --------------------------------------------------------------------
# (remote oversight is unreachable here — the manifest schema already forbids oversight+remote, D9;
#  see test_manifest.test_oversight_cannot_be_remote_in_v1.)

def _fixed_resolver(manifest: ComponentManifest) -> Any:
    class _Fixed:
        def handles(self, ref: Any) -> bool:
            return True

        def locate(self, ref: Any) -> ComponentManifest:
            return manifest

    return _Fixed()


async def test_connect_requires_a_remote_mode() -> None:
    local = ComponentManifest.model_validate({
        "schema_version": "1.0",
        "component": {"namespace": "a", "name": "p", "version": "1.0.0", "kind": "control_policy"},
        "interface": {"name": "dcp.control_policy", "version": "1.0"},
        "access_modes": [{"type": "local", "implementation": {
            "type": "python_package", "source": "pypi", "package": "p", "entrypoint": "p:P"}}],
    })
    plan = resolve("installed://a/p", resolvers=[_fixed_resolver(local)])
    with pytest.raises(RemoteComponentError):
        await connect(plan, LoopbackTransport(descriptor=_descriptor(),
                                              decide=lambda _p: OrchestratorAction(action="stop")))


async def test_connect_model_provider_returns_a_remote_agent() -> None:
    from dcp.component import RemoteAgent

    provider = ComponentManifest.model_validate({
        "schema_version": "1.0",
        "component": {"namespace": "a", "name": "prov", "version": "1.0.0",
                      "kind": "model_provider"},
        "interface": {"name": "dcp.model_provider", "version": "1.0"},
        "access_modes": [{"type": "remote", "binding": {"protocol": "dcp-http", "version": "1.0"},
                          "endpoint": "https://x/dcp"}],
    })
    plan = resolve("installed://a/prov", resolvers=[_fixed_resolver(provider)], mode="remote")
    proxy = await connect(plan, LoopbackTransport(
        descriptor=_descriptor(component={"namespace": "a", "name": "prov", "version": "1.0.0",
                                          "kind": "model_provider"},
                               interface={"name": "dcp.model_provider", "version": "1.0"}),
        decide=lambda _p: OrchestratorAction(action="stop")))
    assert isinstance(proxy, RemoteAgent) and proxy._retry_safe is True   # no state ⇒ retry-safe


# --- the acceptance loop: a RemoteControlPolicy drives the Orchestrator -----------------

async def test_remote_policy_drives_the_orchestrator() -> None:
    from dcp.orchestration import Orchestrator
    from dcp.provider import MockProvider
    from dcp.state import SqlStore

    def _remote_decide(payload: dict[str, Any]) -> OrchestratorAction:
        # the "remote orchestrator" works on the projected payload (the wire contract)
        spoken = {m["role_id"] for m in payload.get("transcript", [])}
        for role in payload["roles"]:
            if role["role_id"] not in spoken:
                return OrchestratorAction(action="select_speaker", target_role_id=role["role_id"])
        return OrchestratorAction(action="stop", status=TerminationStatus.DONE)

    class _Fixed:
        def handles(self, ref: Any) -> bool:
            return True

        def locate(self, ref: Any) -> ComponentManifest:
            return _manifest()

    plan = resolve("installed://alice/orch", resolvers=[_Fixed()], mode="remote")
    policy = await connect(plan, LoopbackTransport(descriptor=_descriptor(), decide=_remote_decide))
    assert isinstance(policy, RemoteControlPolicy)

    def _agent(rid: str) -> s.Role:
        return s.Role(role_id=rid, name=rid, kind=s.RoleKind.AGENT,
                      response_requirement=s.ResponseRequirement.REQUIRED)

    template = s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done", max_turns=6),
        roles=[_agent("a"), _agent("b")])
    store = SqlStore()
    store.create_instance(InstanceHeader(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@o", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0", created_at=_TS))
    ps = {r: s.Participant(participant_id=r, kind=s.RoleKind.AGENT, display_name=r.upper())
          for r in ("a", "b")}
    orch = Orchestrator(
        store=store, template=template, instance_id="dlg", cast={"a": "a", "b": "b"},
        participants=ps,
        provider=MockProvider(texts=["x", "x", "x", "x"]),
        agent_providers={"a": MockProvider(texts=["from a"]),
                         "b": MockProvider(texts=["from b"])},
        control_policy=policy)   # ← the remote orchestrator, over the loopback transport
    inst = await orch.run()
    assert inst.status in (s.InstanceStatus.DONE, s.InstanceStatus.PROVISIONAL)
    assert inst.turn >= 2

    # D12: every context transmitted off-box is recorded in the event log
    projected = [e for e in inst.events if e.type is s.EventType.CONTEXT_PROJECTED]
    assert projected, "no CONTEXT_PROJECTED events were logged"
    audit = projected[0].payload
    assert len(audit["payload_digest"]) == 64                  # sha256 of what was sent
    assert audit["destination"] == "https://alice.example/dcp"
    assert "roles" in audit["fields"]


async def test_local_policy_logs_no_projection() -> None:
    # a plain (non-remote) policy doesn't implement the audit seam → no CONTEXT_PROJECTED events
    from dcp.orchestration import FlowPolicy, RecordsContextProjection

    assert not isinstance(FlowPolicy(), RecordsContextProjection)
