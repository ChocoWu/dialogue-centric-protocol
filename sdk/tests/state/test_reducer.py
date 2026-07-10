"""M2 — reducer replay: determinism + status/turn/roster derivation (SPEC §3.1; D3)."""

from __future__ import annotations

from datetime import UTC, datetime

from dcp import schema as s
from dcp.state import InstanceHeader, replay
from dcp.state.store import Record

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


def _ev(eid: str, t: s.EventType, **payload: object) -> s.Event:
    return s.Event(event_id=eid, instance_id="dlg_1", type=t, payload=payload, created_at=_TS)


def _seq() -> list[Record]:
    return [
        _ev("e0", s.EventType.INSTANCE_CREATED),
        _ev("e1", s.EventType.PARTICIPANT_JOINED, participant_id="agent.x", tier="speak"),
        _ev("e2", s.EventType.PARTICIPANT_JOINED, participant_id="@founder", tier="own"),
        _ev("e3", s.EventType.ROLES_CAST,
            roles=[{"role_id": "critic", "participant_id": "agent.x"}]),
        _ev("e4", s.EventType.INSTANCE_STARTED),
        _ev("e5", s.EventType.TURN_ASSIGNED, target_role_id="critic"),
        _ev("e6", s.EventType.TURN_ASSIGNED, target_role_id="founder"),
    ]


def test_replay_derives_status_turn_roster() -> None:
    inst = replay(_header(), _seq())
    assert inst.status is s.InstanceStatus.RUNNING
    assert inst.turn == 2
    by_pid = {r.participant_id: r for r in inst.roster}
    assert by_pid["agent.x"].tier is s.AccessTier.SPEAK
    assert by_pid["agent.x"].role_id == "critic"
    assert by_pid["@founder"].tier is s.AccessTier.OWN
    assert inst.budget.turns_used == 2


def test_replay_is_deterministic() -> None:
    assert replay(_header(), _seq()) == replay(_header(), _seq())


def test_gate_open_yields_awaiting_then_running_on_resolve() -> None:
    base = _seq()
    with_gate = [*base, _ev("g_open", s.EventType.GATE_OPENED, gate_id="g1", role_id="founder")]
    assert replay(_header(), with_gate).status is s.InstanceStatus.AWAITING
    resolved = [*with_gate, _ev("g_res", s.EventType.GATE_RESOLVED, gate_id="g1")]
    assert replay(_header(), resolved).status is s.InstanceStatus.RUNNING


def test_open_mic_pending_until_addressed() -> None:
    seq = [
        *_seq(),
        _ev("hi_p", s.EventType.HUMAN_INPUT_PENDING, input_id="hi_1", kind="open_mic",
            content="Q?"),
    ]
    inst = replay(_header(), seq)
    assert inst.pending_inputs[0].addressed is False
    addressed = [*seq, _ev("hi_a", s.EventType.HUMAN_INPUT_ADDRESSED, input_id="hi_1")]
    assert replay(_header(), addressed).pending_inputs[0].addressed is True


def test_termination_overrides_derived_status() -> None:
    seq = [*_seq(), _ev("term", s.EventType.INSTANCE_TERMINATED, status="done", reason="ok")]
    assert replay(_header(), seq).status is s.InstanceStatus.DONE


def test_participant_left_removes_from_roster() -> None:
    seq = [*_seq(), _ev("left", s.EventType.PARTICIPANT_LEFT, participant_id="agent.x")]
    inst = replay(_header(), seq)
    assert "agent.x" not in {r.participant_id for r in inst.roster}
