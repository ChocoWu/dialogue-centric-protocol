"""M2 — SqlStore round-trip + append-only invariants on SQLite :memory: (SPEC §3.1; A2/D3/D4)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dcp import schema as s
from dcp.errors import RegistryError
from dcp.state import InstanceHeader, SqlStore

_TS = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def _header(iid: str = "dlg_1") -> InstanceHeader:
    return InstanceHeader(
        instance_id=iid,
        template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@owner",
        visibility=s.Visibility.PRIVATE,
        dcp_version="0.2.0",
        created_at=_TS,
    )


def _ev(iid: str, t: s.EventType, **payload: object) -> s.Event:
    return s.Event(event_id=f"e{abs(hash((iid, t, tuple(payload))))}", instance_id=iid,
                   type=t, payload=payload, created_at=_TS)


def _msg(iid: str, mid: str, turn: int) -> s.Message:
    return s.Message(message_id=mid, instance_id=iid, turn_id=turn, role_id="r", participant_id="p",
                     speaker_kind=s.RoleKind.AGENT, content="hi", created_at=_TS)


def test_create_and_get_header() -> None:
    store = SqlStore()
    store.create_instance(_header())
    got = store.get_header("dlg_1")
    assert got == _header()
    assert store.get_header("missing") is None
    assert store.list_instances() == ["dlg_1"]


def test_duplicate_instance_rejected() -> None:
    store = SqlStore()
    store.create_instance(_header())
    with pytest.raises(RegistryError):
        store.create_instance(_header())


def test_append_only_preserves_order_and_kind() -> None:
    store = SqlStore()
    store.create_instance(_header())
    store.append("dlg_1", _ev("dlg_1", s.EventType.INSTANCE_CREATED))
    store.append("dlg_1", _msg("dlg_1", "m1", 1))
    store.append("dlg_1", _ev("dlg_1", s.EventType.TURN_ASSIGNED))
    store.append("dlg_1", _msg("dlg_1", "m2", 2))
    recs = store.load_records("dlg_1")
    assert [type(r).__name__ for r in recs] == ["Event", "Message", "Event", "Message"]
    assert [r.message_id for r in recs if isinstance(r, s.Message)] == ["m1", "m2"]
    # re-loading is stable (append-only, no reorder)
    assert store.load_records("dlg_1") == recs


def test_records_are_scoped_per_instance() -> None:
    store = SqlStore()
    store.create_instance(_header("a"))
    store.create_instance(_header("b"))
    store.append("a", _msg("a", "ma", 1))
    store.append("b", _msg("b", "mb", 1))
    assert [r.message_id for r in store.load_records("a") if isinstance(r, s.Message)] == ["ma"]
    assert [r.message_id for r in store.load_records("b") if isinstance(r, s.Message)] == ["mb"]


def test_participant_registry() -> None:
    store = SqlStore()
    agent = s.Participant(
        participant_id="agent.x", kind=s.RoleKind.AGENT, display_name="X", discoverable=True,
        model_binding=s.ModelBinding(provider="openai", model="gpt-x"),
    )
    human = s.Participant(
        participant_id="@u", kind=s.RoleKind.HUMAN, display_name="U", discoverable=False
    )
    store.register_participant(agent)
    store.register_participant(human)
    assert store.get_participant("agent.x") == agent
    assert store.get_participant("nope") is None
    assert {p.participant_id for p in store.list_participants()} == {"agent.x", "@u"}
    discoverable = store.list_participants(discoverable_only=True)
    assert [p.participant_id for p in discoverable] == ["agent.x"]
    with pytest.raises(RegistryError):
        store.register_participant(agent)
