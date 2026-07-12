"""M6 — hosting ops: instantiate / grant / join / leave / restore (SPEC §2.3, §2.5, §6)."""

from __future__ import annotations

import pytest

from dcp import schema as s
from dcp.errors import AccessError, RegistryError
from dcp.registry import Registry
from dcp.state import SqlStore


def _reg(*, visibility: s.Visibility | None = None) -> Registry:
    reg = Registry(SqlStore())
    reg.register_template(s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done"),
        default_visibility=visibility,
        roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                      response_requirement=s.ResponseRequirement.REQUIRED)],
    ))
    return reg


def _ref() -> s.TemplateRef:
    return s.TemplateRef(template_id="t", version="1.0.0")


def test_instantiate_sets_owner_and_created_status() -> None:
    reg = _reg()
    inst = reg.instantiate(_ref(), owner="@owner", instance_id="dlg")
    assert inst.owner == "@owner"
    assert inst.status is s.InstanceStatus.CREATED
    # owner is on the roster at own tier
    own = next(r for r in inst.roster if r.participant_id == "@owner")
    assert own.tier is s.AccessTier.OWN


def test_instantiate_records_brief_and_it_replays() -> None:
    # The per-run task input is owner-supplied at instantiate and must survive replay (D3).
    reg = _reg()
    brief = {"product": "B2B analytics", "constraints": ["avoid -ly"]}
    inst = reg.instantiate(_ref(), owner="@owner", instance_id="dlg", brief=brief)
    assert inst.brief == brief
    assert reg.restore("dlg").brief == brief          # round-trips through the log


def test_instantiate_brief_defaults_to_empty() -> None:
    reg = _reg()
    inst = reg.instantiate(_ref(), owner="@owner", instance_id="dlg")
    assert inst.brief == {}


def test_instantiate_records_goal_override_and_it_replays() -> None:
    reg = _reg()
    inst = reg.instantiate(_ref(), owner="@owner", instance_id="dlg", goal="Name this product")
    assert inst.goal == "Name this product"
    assert reg.restore("dlg").goal == "Name this product"   # round-trips through the log


def test_instantiate_goal_defaults_to_empty() -> None:
    reg = _reg()
    assert reg.instantiate(_ref(), owner="@owner", instance_id="dlg").goal == ""


def test_instantiate_records_termination_override_and_it_replays() -> None:
    reg = _reg()
    override = s.TerminationPolicy(condition="founder approves", max_turns=12, token_budget=5000)
    inst = reg.instantiate(_ref(), owner="@owner", instance_id="dlg", termination=override)
    assert inst.termination_policy == override
    assert reg.restore("dlg").termination_policy == override   # round-trips through the log


def test_instantiate_termination_defaults_to_none() -> None:
    reg = _reg()
    assert reg.instantiate(_ref(), owner="@owner", instance_id="dlg").termination_policy is None


def test_instantiate_default_visibility_is_private() -> None:
    reg = _reg()  # template has no default_visibility
    inst = reg.instantiate(_ref(), owner="@owner", instance_id="dlg")
    assert inst.visibility is s.Visibility.PRIVATE


def test_instantiate_unknown_template_fails() -> None:
    reg = _reg()
    with pytest.raises(RegistryError):
        reg.instantiate(s.TemplateRef(template_id="t", version="9.9.9"), owner="@o")


def test_public_join_admits_as_observe() -> None:
    reg = _reg(visibility=s.Visibility.PUBLIC)
    reg.instantiate(_ref(), owner="@owner", instance_id="dlg")
    inst = reg.join("dlg", participant_id="@guest")
    guest = next(r for r in inst.roster if r.participant_id == "@guest")
    assert guest.tier is s.AccessTier.OBSERVE


def test_private_join_without_grant_is_rejected() -> None:
    reg = _reg(visibility=s.Visibility.PRIVATE)
    reg.instantiate(_ref(), owner="@owner", instance_id="dlg")
    with pytest.raises(AccessError):
        reg.join("dlg", participant_id="@intruder")


def test_private_join_with_grant_admits_at_granted_tier() -> None:
    reg = _reg(visibility=s.Visibility.PRIVATE)
    reg.instantiate(_ref(), owner="@owner", instance_id="dlg")
    reg.grant_access("dlg", grantor="@owner", participant_id="@guest", tier=s.AccessTier.SPEAK)
    inst = reg.join("dlg", participant_id="@guest")
    guest = next(r for r in inst.roster if r.participant_id == "@guest")
    assert guest.tier is s.AccessTier.SPEAK


def test_non_owner_cannot_grant() -> None:
    reg = _reg(visibility=s.Visibility.PRIVATE)
    reg.instantiate(_ref(), owner="@owner", instance_id="dlg")
    with pytest.raises(AccessError):
        reg.grant_access("dlg", grantor="@nobody", participant_id="@x", tier=s.AccessTier.SPEAK)


def test_join_replays_full_history_to_joiner() -> None:
    reg = _reg(visibility=s.Visibility.PUBLIC)
    reg.instantiate(_ref(), owner="@owner", instance_id="dlg")
    # joiner's returned instance is a full replay including prior events (D3)
    inst = reg.join("dlg", participant_id="@guest")
    types_ = [e.type for e in inst.events]
    assert s.EventType.INSTANCE_CREATED in types_
    assert types_.count(s.EventType.PARTICIPANT_JOINED) == 2       # owner + guest


def test_leave_removes_from_roster() -> None:
    reg = _reg(visibility=s.Visibility.PUBLIC)
    reg.instantiate(_ref(), owner="@owner", instance_id="dlg")
    reg.join("dlg", participant_id="@guest")
    reg.leave("dlg", participant_id="@guest")
    inst = reg.restore("dlg")
    assert all(r.participant_id != "@guest" for r in inst.roster)


def test_registry_authenticate_delegates() -> None:
    reg = Registry(SqlStore())      # default anonymous dev mode
    assert reg.authenticate(None) == "@local"
