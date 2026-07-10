"""M3 — role casting precedence + tier/kind rules (SPEC §2.4/§6)."""

from __future__ import annotations

import pytest

from dcp import schema as s
from dcp.errors import AccessError, RegistryError
from dcp.participation import cast_roles


def _p(pid: str, kind: s.RoleKind, profile: str = "") -> s.Participant:
    return s.Participant(participant_id=pid, kind=kind, display_name=pid, profile=profile)


def _tmpl(*roles: s.Role) -> s.DialogueTemplate:
    return s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done"), roles=list(roles),
    )


def _role(role_id: str, kind: s.RoleKind, *, persona: str = "", bind: str | None = None) -> s.Role:
    return s.Role(
        role_id=role_id, name=role_id, kind=kind, persona=persona,
        binding=s.RoleBinding(participant_id=bind),
    )


def test_precedence_explicit_binding_wins() -> None:
    tmpl = _tmpl(_role("critic", s.RoleKind.AGENT, bind="agent.b"))
    ps = [_p("critic", s.RoleKind.AGENT), _p("agent.b", s.RoleKind.AGENT)]
    cast = cast_roles(tmpl, ps, "dlg")
    # explicit binding beats the role_id==participant_id match
    assert cast.roles[0].participant_id == "agent.b"


def test_precedence_role_id_match() -> None:
    tmpl = _tmpl(_role("critic", s.RoleKind.AGENT))
    ps = [_p("other", s.RoleKind.AGENT, profile="critic technical"), _p("critic", s.RoleKind.AGENT)]
    cast = cast_roles(tmpl, ps, "dlg")
    assert cast.roles[0].participant_id == "critic"       # id-match beats capability overlap


def test_precedence_capability_overlap() -> None:
    tmpl = _tmpl(_role("r1", s.RoleKind.AGENT, persona="identify technical risks"))
    ps = [
        _p("a.market", s.RoleKind.AGENT, profile="marketing and growth"),
        _p("a.tech", s.RoleKind.AGENT, profile="technical reviewer for risks"),
    ]
    cast = cast_roles(tmpl, ps, "dlg")
    assert cast.roles[0].participant_id == "a.tech"


def test_precedence_persona_fallback() -> None:
    tmpl = _tmpl(_role("r1", s.RoleKind.AGENT, persona="zzz"))
    ps = [_p("a.2", s.RoleKind.AGENT), _p("a.1", s.RoleKind.AGENT)]
    cast = cast_roles(tmpl, ps, "dlg")
    assert cast.roles[0].participant_id == "a.1"          # first available by id


def test_kind_is_respected() -> None:
    tmpl = _tmpl(_role("founder", s.RoleKind.HUMAN))
    ps = [_p("agent.x", s.RoleKind.AGENT), _p("@founder", s.RoleKind.HUMAN)]
    cast = cast_roles(tmpl, ps, "dlg")
    assert cast.roles[0].participant_id == "@founder"


def test_observe_tier_cannot_be_cast() -> None:
    tmpl = _tmpl(_role("critic", s.RoleKind.AGENT))
    ps = [_p("critic", s.RoleKind.AGENT)]
    with pytest.raises(AccessError):
        cast_roles(tmpl, ps, "dlg", tiers={"critic": s.AccessTier.OBSERVE})


def test_unfillable_role_raises() -> None:
    tmpl = _tmpl(_role("founder", s.RoleKind.HUMAN))
    ps = [_p("agent.x", s.RoleKind.AGENT)]                # no human available
    with pytest.raises(RegistryError):
        cast_roles(tmpl, ps, "dlg")


def test_bound_participant_kind_mismatch_raises() -> None:
    tmpl = _tmpl(_role("critic", s.RoleKind.AGENT, bind="@human"))
    ps = [_p("@human", s.RoleKind.HUMAN)]
    with pytest.raises(AccessError):
        cast_roles(tmpl, ps, "dlg")
