"""Phase 7A — the ComponentManifest schema root (PROPOSAL-component-ecosystem.md §3/§4/§11).

Encodes the closed decisions: executable-vs-declarative kinds (D14), identity ≠ kind-specific spec
(D21), interface.name ↔ kind 1:1 (D18), local/remote access modes with the kind×mode matrix,
ArtifactReference requires a digest (D19), credential_slot not env (D22), dependency expected_kind
as a constraint (D23).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dcp.component import (
    ComponentKind,
    ComponentManifest,
    InterfaceName,
    is_executable,
)


def _base(**over: object) -> dict[str, object]:
    """A minimal valid control_policy manifest (local, no artifacts)."""
    doc: dict[str, object] = {
        "schema_version": "1.0",
        "component": {"namespace": "alice", "name": "research-orch", "version": "1.2.0",
                      "kind": "control_policy"},
        "interface": {"name": "dcp.control_policy", "version": "1.0"},
        "access_modes": [{
            "type": "local",
            "implementation": {"type": "python_package", "source": "pypi",
                               "package": "alice-orch", "entrypoint": "alice_orch:Policy"},
        }],
    }
    doc.update(over)
    return doc


# --- happy path -------------------------------------------------------------------------

def test_minimal_control_policy_manifest_parses() -> None:
    m = ComponentManifest.model_validate(_base())
    assert m.component.kind is ComponentKind.CONTROL_POLICY
    assert m.interface.name is InterfaceName.CONTROL_POLICY
    assert m.access_modes[0].type == "local"


def test_round_trips_through_json() -> None:
    m = ComponentManifest.model_validate(_base())
    assert ComponentManifest.model_validate(m.model_dump(mode="json")) == m


def test_unknown_top_level_field_rejected() -> None:
    with pytest.raises(ValidationError):
        ComponentManifest.model_validate(_base(surprise=1))


# --- D14 executable vs declarative -----------------------------------------------------

def test_executable_classification() -> None:
    assert is_executable(ComponentKind.CONTROL_POLICY)
    assert is_executable(ComponentKind.AGENT)
    assert not is_executable(ComponentKind.TEMPLATE)


# --- D18 interface.name must map 1:1 from component.kind -------------------------------

def test_interface_name_must_match_kind() -> None:
    with pytest.raises(ValidationError):
        ComponentManifest.model_validate(
            _base(interface={"name": "dcp.oversight_policy", "version": "1.0"}))


def test_interface_and_binding_versions_are_independent() -> None:
    doc = _base()
    doc["access_modes"] = [{
        "type": "remote",
        "binding": {"protocol": "dcp-http", "version": "2.1"},
        "endpoint": "https://x/dcp",
        "auth": {"type": "bearer", "credential_slot": "access_token"},
    }]
    m = ComponentManifest.model_validate(doc)
    assert m.interface.version == "1.0"
    assert m.access_modes[0].binding.version == "2.1"      # ≠ interface.version


# --- D21 identity ≠ kind-specific spec; spec discriminates on kind ---------------------

def test_agent_spec_carries_provider_and_role_defaults() -> None:
    doc = _base(component={"namespace": "alice", "name": "critic", "version": "1.0.0",
                           "kind": "agent"},
                interface={"name": "dcp.agent_definition", "version": "1.0"},
                spec={"provider": {"ref": "pypi://alice-provider@1.0.0",
                                   "expected_kind": "model_provider"},
                      "role_defaults": {"persona": "be terse", "response_requirement": "required"}})
    m = ComponentManifest.model_validate(doc)
    assert m.spec.kind is ComponentKind.AGENT
    assert m.spec.provider is not None
    assert m.spec.provider.expected_kind is ComponentKind.MODEL_PROVIDER
    assert m.spec.role_defaults is not None and m.spec.role_defaults.persona == "be terse"


def test_spec_defaults_to_empty_for_kinds_without_a_body() -> None:
    m = ComponentManifest.model_validate(_base())          # no `spec` key given
    assert m.spec.kind is ComponentKind.CONTROL_POLICY


def test_spec_kind_mismatch_is_rejected() -> None:
    # explicit spec.kind disagreeing with component.kind
    with pytest.raises(ValidationError):
        ComponentManifest.model_validate(_base(spec={"kind": "agent"}))


def test_agent_only_fields_rejected_on_non_agent_spec() -> None:
    provider = {"ref": "x", "expected_kind": "model_provider"}
    with pytest.raises(ValidationError):
        ComponentManifest.model_validate(_base(spec={"provider": provider}))


# --- kind × access-mode matrix (§3) ----------------------------------------------------

def _artifact() -> dict[str, object]:
    return {"uri": "hf://alice/m@abc", "digest": {"algorithm": "sha256", "value": "deadbeef"}}


def test_template_cannot_carry_artifacts_or_remote() -> None:
    tmpl = _base(component={"namespace": "a", "name": "t", "version": "1.0.0", "kind": "template"},
                 interface={"name": "dcp.dialogue_template", "version": "1.0"})
    ok = ComponentManifest.model_validate(tmpl)            # plain local is fine
    assert ok.component.kind is ComponentKind.TEMPLATE

    with_art = dict(tmpl)
    with_art["access_modes"] = [{
        "type": "local",
        "implementation": {"type": "python_package", "source": "pypi", "package": "t",
                           "entrypoint": "t:make"},
        "artifacts": [_artifact()],
    }]
    with pytest.raises(ValidationError):
        ComponentManifest.model_validate(with_art)


def test_oversight_cannot_be_remote_in_v1() -> None:
    doc = _base(component={"namespace": "a", "name": "ov", "version": "1.0.0",
                           "kind": "oversight_policy"},
                interface={"name": "dcp.oversight_policy", "version": "1.0"})
    doc["access_modes"] = [{
        "type": "remote",
        "binding": {"protocol": "dcp-http", "version": "1.0"},
        "endpoint": "https://x/dcp",
        "auth": {"type": "bearer", "credential_slot": "token"},
    }]
    with pytest.raises(ValidationError):
        ComponentManifest.model_validate(doc)


# --- D19 artifact integrity ------------------------------------------------------------

def test_artifact_requires_a_digest() -> None:
    doc = _base()
    doc["access_modes"] = [{
        "type": "local",
        "implementation": {"type": "python_package", "source": "pypi", "package": "p",
                           "entrypoint": "p:P"},
        "artifacts": [{"uri": "hf://alice/m@abc"}],        # no digest
    }]
    with pytest.raises(ValidationError):
        ComponentManifest.model_validate(doc)


# --- D18 capability namespace ----------------------------------------------------------

def test_capabilities_must_be_namespaced() -> None:
    with pytest.raises(ValidationError):
        ComponentManifest.model_validate(_base(capabilities=["next_speaker"]))   # bare namespace


def test_capabilities_accept_dcp_and_ext_namespaces() -> None:
    m = ComponentManifest.model_validate(
        _base(capabilities=["dcp.control.next_speaker", "ext.alice.long_horizon_plan"]))
    assert len(m.capabilities) == 2


# --- structural guards -----------------------------------------------------------------

def test_at_least_one_access_mode_required() -> None:
    with pytest.raises(ValidationError):
        ComponentManifest.model_validate(_base(access_modes=[]))


def test_access_mode_discriminates_local_vs_remote() -> None:
    m = ComponentManifest.model_validate(_base())
    assert m.access_modes[0].implementation.entrypoint == "alice_orch:Policy"
