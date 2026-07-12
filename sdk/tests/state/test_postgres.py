"""Phase 6.4 — the SqlStore works on real Postgres (skipped unless DCP_TEST_POSTGRES_URL is set).

CI runs this against an ephemeral Postgres service (see .github/workflows/ci.yml); it proves the
advertised Postgres path — not just SQLite — actually round-trips.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from dcp import schema as s
from dcp.state import InstanceHeader, SqlStore, metadata, restore

_PG = os.getenv("DCP_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not _PG, reason="set DCP_TEST_POSTGRES_URL to run Postgres tests")

_TS = datetime(2026, 7, 12, tzinfo=UTC)


def _fresh_store() -> SqlStore:
    from sqlalchemy import create_engine
    engine = create_engine(_PG)           # type: ignore[arg-type]
    metadata.drop_all(engine)             # clean slate for a deterministic run
    metadata.create_all(engine)
    return SqlStore(_PG, create_tables=False)  # type: ignore[arg-type]


def _msg(mid: str, turn: int) -> s.Message:
    return s.Message(message_id=mid, instance_id="dlg", turn_id=turn, role_id="a",
                     participant_id="a", speaker_kind=s.RoleKind.AGENT, content="hi",
                     created_at=_TS)


def _event(eid: str) -> s.Event:
    return s.Event(event_id=eid, instance_id="dlg", type=s.EventType.INSTANCE_STARTED,
                   payload={}, created_at=_TS)


def test_store_roundtrips_on_postgres() -> None:
    store = _fresh_store()
    store.create_instance(InstanceHeader(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@o", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0", created_at=_TS))
    store.append("dlg", _event("e0"))
    store.append("dlg", _msg("m1", 1))

    # ordered log preserved across message/event on Postgres
    records = store.load_records("dlg")
    assert [type(r).__name__ for r in records] == ["Event", "Message"]

    store.register_participant(s.Participant(
        participant_id="a", kind=s.RoleKind.AGENT, display_name="A", discoverable=True))
    store.register_template(s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done"),
        roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                      response_requirement=s.ResponseRequirement.REQUIRED)]))
    store.add_grant(s.AccessGrant(instance_id="dlg", participant_id="a", tier=s.AccessTier.SPEAK,
                                  granted_by="@o", granted_at=_TS))

    assert store.get_participant("a") is not None
    assert store.get_template("t", "1.0.0") is not None
    assert store.get_grant("dlg", "a") is not None
    assert [p.participant_id for p in store.list_participants(discoverable_only=True)] == ["a"]

    inst = restore(store, "dlg")
    assert inst.status is s.InstanceStatus.RUNNING and len(inst.messages) == 1
