"""M2 — restore = full replay from the store; all N events in order (SPEC §2.9/§6; D3/TBD-28)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dcp import schema as s
from dcp.errors import RegistryError
from dcp.state import InstanceHeader, SqlStore, restore

_TS = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def _header() -> InstanceHeader:
    return InstanceHeader(
        instance_id="dlg_1",
        template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@owner",
        visibility=s.Visibility.PRIVATE,
        dcp_version="0.2.0",
        created_at=_TS,
    )


def _ev(t: s.EventType, n: int) -> s.Event:
    return s.Event(event_id=f"e{n}", instance_id="dlg_1", type=t, payload={"n": n}, created_at=_TS)


def test_restore_returns_all_events_in_order() -> None:
    store = SqlStore()
    store.create_instance(_header())
    appended = [
        _ev(s.EventType.INSTANCE_CREATED, 0),
        _ev(s.EventType.INSTANCE_STARTED, 1),
        _ev(s.EventType.TURN_ASSIGNED, 2),
        _ev(s.EventType.TURN_ASSIGNED, 3),
    ]
    for e in appended:
        store.append("dlg_1", e)
    inst = restore(store, "dlg_1")
    assert inst.events == appended                    # all N, in order
    assert inst.status is s.InstanceStatus.RUNNING
    assert inst.turn == 2


def test_restore_reproduces_messages_in_order() -> None:
    store = SqlStore()
    store.create_instance(_header())
    store.append("dlg_1", _ev(s.EventType.INSTANCE_STARTED, 1))
    for i in range(3):
        store.append("dlg_1", s.Message(
            message_id=f"m{i}", instance_id="dlg_1", turn_id=i, role_id="r",
            participant_id="p", speaker_kind=s.RoleKind.AGENT, content=f"c{i}", created_at=_TS,
        ))
    inst = restore(store, "dlg_1")
    assert [m.message_id for m in inst.messages] == ["m0", "m1", "m2"]


def test_restore_is_deterministic() -> None:
    store = SqlStore()
    store.create_instance(_header())
    for n, t in enumerate([s.EventType.INSTANCE_STARTED, s.EventType.TURN_ASSIGNED]):
        store.append("dlg_1", _ev(t, n))
    assert restore(store, "dlg_1") == restore(store, "dlg_1")


def test_restore_unknown_instance_raises() -> None:
    store = SqlStore()
    with pytest.raises(RegistryError):
        restore(store, "nope")
