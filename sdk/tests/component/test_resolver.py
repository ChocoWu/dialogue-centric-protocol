"""Phase 7A — the resolution pipeline (PROPOSAL §5): side-effect-free resolve → plan → materialize.

Proves D11 (resolve does no install/import), mode selection, dependency DAG + cycle rejection (D17),
`expected_kind` constraints (D23), and the §10 acceptance loop: an installed third-party
ControlPolicy manifest → resolved from a URL/entry point → inspectable plan → materialized into a
live policy that the existing Orchestrator can drive.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib.metadata import EntryPoint

import pytest

from dcp import schema as s
from dcp.component import (
    ComponentManifest,
    ComponentResolutionPlan,
    InstalledResolver,
    ManifestUrlResolver,
    materialize,
    parse_reference,
    resolve,
)
from dcp.errors import ResolutionError
from dcp.orchestration import DialogueContext, OrchestratorAction
from dcp.plugins import GROUP_COMPONENTS
from dcp.schema import TerminationStatus

_TS = datetime(2026, 7, 12, tzinfo=UTC)


# --- a real, importable ControlPolicy used as the "installed" component -----------------

class AcceptancePolicy:
    """A model-free ControlPolicy: first unspoken role, else stop (the materialization target)."""

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        spoken = {m.role_id for m in ctx.messages}
        for role in ctx.roles:
            if role.role_id not in spoken:
                return OrchestratorAction(action="select_speaker", target_role_id=role.role_id)
        return OrchestratorAction(action="stop", status=TerminationStatus.DONE)


def _manifest_dict(**over: object) -> dict[str, object]:
    doc: dict[str, object] = {
        "schema_version": "1.0",
        "component": {"namespace": "alice", "name": "rr", "version": "1.0.0",
                      "kind": "control_policy"},
        "interface": {"name": "dcp.control_policy", "version": "1.0"},
        "access_modes": [{
            "type": "local",
            "implementation": {"type": "python_package", "source": "pypi", "package": "alice-rr",
                               "entrypoint": f"{__name__}:AcceptancePolicy"},
        }],
    }
    doc.update(over)
    return doc


def _installed_manifest() -> ComponentManifest:   # entry-point target for InstalledResolver
    return ComponentManifest.model_validate(_manifest_dict())


_SOURCE = [EntryPoint("alice/rr", f"{__name__}:_installed_manifest", GROUP_COMPONENTS)]


# --- reference parsing (D15) -----------------------------------------------------------

def test_parse_reference_schemes() -> None:
    assert parse_reference("installed://alice/rr").scheme == "installed"
    assert parse_reference("file:///x/dcp-component.yaml").scheme == "file"
    assert parse_reference("https://h/dcp-component.yaml").scheme == "https"
    assert parse_reference("git+https://h/r.git@v1#m.yaml").fragment == "m.yaml"
    assert parse_reference("bare/path.json").scheme == "file"


# --- resolve is side-effect-free (D11) -------------------------------------------------

def test_resolve_from_installed_entry_point() -> None:
    plan = resolve("installed://alice/rr", resolvers=[InstalledResolver(source=_SOURCE)])
    assert isinstance(plan, ComponentResolutionPlan)
    assert plan.manifest.component.name == "rr"
    assert plan.selected_mode.type == "local"


def test_resolve_from_a_manifest_url_reader() -> None:
    reader = ManifestUrlResolver(reader=lambda _loc: json.dumps(_manifest_dict()))
    plan = resolve("file:///anywhere/dcp-component.json", resolvers=[reader])
    assert plan.manifest.component.namespace == "alice"


def test_plan_lists_expected_side_effects_but_performs_none() -> None:
    # If resolve imported the entrypoint we'd see it; instead the import is only a *planned* effect.
    plan = resolve("installed://alice/rr", resolvers=[InstalledResolver(source=_SOURCE)])
    joined = " ".join(plan.expected_side_effects)
    assert "provision: install pypi:alice-rr" in joined
    assert f"instantiate: import {__name__}:AcceptancePolicy" in joined


def test_no_resolver_handles_reference() -> None:
    with pytest.raises(ResolutionError):
        resolve("installed://alice/rr", resolvers=[ManifestUrlResolver()])


def test_unsupported_scheme_is_a_clear_error() -> None:
    with pytest.raises(ResolutionError):
        resolve("pypi://alice-rr@1.0.0")     # 7B resolver


# --- mode selection --------------------------------------------------------------------

def _dual_mode_manifest() -> ComponentManifest:
    doc = _manifest_dict()
    doc["access_modes"] = [
        doc["access_modes"][0],                                     # type: ignore[index]
        {"type": "remote", "binding": {"protocol": "dcp-http", "version": "1.0"},
         "endpoint": "https://x/dcp", "auth": {"type": "bearer", "credential_slot": "token"}},
    ]
    return ComponentManifest.model_validate(doc)


def test_mode_preference_and_explicit_mode() -> None:
    src = [EntryPoint("alice/dual", f"{__name__}:_dual_mode_manifest", GROUP_COMPONENTS)]
    r = [InstalledResolver(source=src)]
    assert resolve("installed://alice/dual", resolvers=r).selected_mode.type == "local"   # first
    assert resolve("installed://alice/dual", resolvers=r,
                   mode_preference=["remote", "local"]).selected_mode.type == "remote"
    remote = resolve("installed://alice/dual", resolvers=r, mode="remote")
    assert remote.credential_slots == ["token"]
    assert remote.warnings and "owner boundary" in remote.warnings[0]


def test_explicit_mode_absent_raises() -> None:
    r = [InstalledResolver(source=_SOURCE)]
    with pytest.raises(ResolutionError):
        resolve("installed://alice/rr", resolvers=r, mode="remote")   # rr has only a local mode


# --- dependencies: DAG, cycle rejection (D17), expected_kind constraint (D23) -----------

def test_dependency_expected_kind_mismatch_is_rejected() -> None:
    # rr is a control_policy, but the parent declares expected_kind=oversight_policy → reject (D23)
    parent = _manifest_dict(dependencies=[{"ref": "installed://alice/rr",
                                           "expected_kind": "oversight_policy"}])
    src = [EntryPoint("alice/parent", f"{__name__}:_installed_manifest", GROUP_COMPONENTS),
           EntryPoint("alice/rr", f"{__name__}:_installed_manifest", GROUP_COMPONENTS)]

    def _parent() -> ComponentManifest:
        return ComponentManifest.model_validate(parent)

    src[0] = EntryPoint("alice/parent", f"{__name__}:_p_bad", GROUP_COMPONENTS)
    globals()["_p_bad"] = _parent
    with pytest.raises(ResolutionError):
        resolve("installed://alice/parent", resolvers=[InstalledResolver(source=src)])


def test_dependency_cycle_is_rejected() -> None:
    def _self_dep() -> ComponentManifest:
        return ComponentManifest.model_validate(
            _manifest_dict(dependencies=[{"ref": "installed://alice/cyc",
                                          "expected_kind": "control_policy"}]))

    globals()["_self_dep"] = _self_dep
    src = [EntryPoint("alice/cyc", f"{__name__}:_self_dep", GROUP_COMPONENTS)]
    with pytest.raises(ResolutionError):
        resolve("installed://alice/cyc", resolvers=[InstalledResolver(source=src)])


# --- materialize (the instantiate stage) + the §10 acceptance loop ----------------------

def test_materialize_returns_a_working_control_policy() -> None:
    plan = resolve("installed://alice/rr", resolvers=[InstalledResolver(source=_SOURCE)])
    policy = materialize(plan)
    assert isinstance(policy, AcceptancePolicy)      # imported + constructed here, not at resolve
    assert callable(policy.decide)


async def test_materialized_policy_drives_the_orchestrator() -> None:
    from dcp.orchestration import Orchestrator
    from dcp.provider import MockProvider
    from dcp.state import InstanceHeader, SqlStore

    plan = resolve("installed://alice/rr", resolvers=[InstalledResolver(source=_SOURCE)])
    policy = materialize(plan)

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
        owner="@owner", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0", created_at=_TS))
    orch = Orchestrator(
        store=store, template=template, instance_id="dlg",
        cast={"a": "a", "b": "b"}, participants={
            "a": s.Participant(participant_id="a", kind=s.RoleKind.AGENT, display_name="A"),
            "b": s.Participant(participant_id="b", kind=s.RoleKind.AGENT, display_name="B")},
        provider=MockProvider(texts=["hi", "hi", "hi", "hi"]),
        agent_providers={"a": MockProvider(texts=["from a"]),
                         "b": MockProvider(texts=["from b"])},
        control_policy=policy)   # ← the materialized third-party orchestrator
    inst = await orch.run()
    assert inst.status in (s.InstanceStatus.DONE, s.InstanceStatus.PROVISIONAL)
    assert inst.turn >= 2                                 # both roles spoke under the custom policy
