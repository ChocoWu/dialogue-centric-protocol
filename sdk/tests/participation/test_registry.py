"""M3 — participant registry over the Store (SPEC §1.5/§3.4; D4)."""

from __future__ import annotations

import pytest

from dcp import schema as s
from dcp.errors import RegistryError
from dcp.participation import ParticipantRegistry
from dcp.state import SqlStore


def _reg() -> ParticipantRegistry:
    return ParticipantRegistry(SqlStore())


def test_register_get_list() -> None:
    reg = _reg()
    a = s.Participant(participant_id="agent.x", kind=s.RoleKind.AGENT, display_name="X",
                      discoverable=True)
    h = s.Participant(participant_id="@u", kind=s.RoleKind.HUMAN, display_name="U")
    reg.register(a)
    reg.register(h)
    assert reg.get("agent.x") == a
    assert reg.get("missing") is None
    assert {p.participant_id for p in reg.list()} == {"agent.x", "@u"}


def test_discoverable_filter() -> None:
    reg = _reg()
    reg.register(s.Participant(participant_id="pub", kind=s.RoleKind.AGENT, display_name="P",
                               discoverable=True))
    reg.register(s.Participant(participant_id="hidden", kind=s.RoleKind.AGENT, display_name="H",
                               discoverable=False))
    assert [p.participant_id for p in reg.list(discoverable_only=True)] == ["pub"]


def test_duplicate_registration_raises() -> None:
    reg = _reg()
    p = s.Participant(participant_id="dup", kind=s.RoleKind.HUMAN, display_name="D")
    reg.register(p)
    with pytest.raises(RegistryError):
        reg.register(p)
