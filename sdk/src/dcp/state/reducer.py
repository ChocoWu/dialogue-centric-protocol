"""Deterministic replay of the append-only log into instance state (D3; SPEC §3.1/§2.9).

``replay(header, records)`` folds an instance's ordered ``messages + events`` into a fully
derived :class:`~dcp.schema.DialogueInstance`. All authoritative runtime state
(status/turn/roster/gates/pending/budget) is reconstructed here — nothing lives only in memory.
"""

from __future__ import annotations

from ..schema import (
    AccessTier,
    Budget,
    DialogueInstance,
    Event,
    EventType,
    Gate,
    InstanceStatus,
    Message,
    PendingInput,
    RosterEntry,
    TerminationStatus,
)
from .store import InstanceHeader, Record


def _s(payload: dict[str, object], key: str, default: str = "") -> str:
    v = payload.get(key, default)
    return v if isinstance(v, str) else default


def replay(header: InstanceHeader, records: list[Record]) -> DialogueInstance:
    """Reconstruct a DialogueInstance from its header + ordered log (full replay, TBD-28)."""
    started = False
    turn = 0
    terminal: InstanceStatus | None = None
    roster: dict[str, RosterEntry] = {}
    gates: dict[str, Gate] = {}
    pending: dict[str, PendingInput] = {}
    messages: list[Message] = []
    events: list[Event] = []

    def upsert(pid: str, *, tier: AccessTier | None = None, role_id: str | None = None) -> None:
        cur = roster.get(pid)
        roster[pid] = RosterEntry(
            participant_id=pid,
            tier=tier if tier is not None else (cur.tier if cur else AccessTier.SPEAK),
            role_id=role_id if role_id is not None else (cur.role_id if cur else None),
        )

    for record in records:
        if isinstance(record, Message):
            messages.append(record)
            continue
        events.append(record)
        p = record.payload
        match record.type:
            case EventType.INSTANCE_STARTED:
                started = True
            case EventType.TURN_ASSIGNED:
                started = True
                turn += 1
            case EventType.ROLES_CAST:
                cast_list = p.get("roles", [])
                if isinstance(cast_list, list):
                    for item in cast_list:
                        if isinstance(item, dict):
                            upsert(_s(item, "participant_id"), role_id=_s(item, "role_id") or None)
            case EventType.PARTICIPANT_JOINED:
                tier = _s(p, "tier", AccessTier.OBSERVE.value)
                upsert(_s(p, "participant_id"), tier=AccessTier(tier))
            case EventType.PARTICIPANT_LEFT:
                roster.pop(_s(p, "participant_id"), None)
            case EventType.TIER_CHANGED:
                new_tier = AccessTier(_s(p, "tier", AccessTier.OBSERVE.value))
                upsert(_s(p, "participant_id"), tier=new_tier)
            case EventType.GATE_OPENED:
                gid = _s(p, "gate_id")
                gates[gid] = Gate(gate_id=gid, role_id=_s(p, "role_id"))
            case EventType.GATE_RESOLVED:
                gates.pop(_s(p, "gate_id"), None)
            case EventType.HUMAN_INPUT_PENDING:
                iid = _s(p, "input_id")
                pending[iid] = PendingInput(
                    input_id=iid,
                    kind=_s(p, "kind", "optional"),
                    content=_s(p, "content") or None,
                    from_participant=_s(p, "from_participant") or None,
                )
            case EventType.HUMAN_INPUT_ADDRESSED:
                iid = _s(p, "input_id")
                if iid in pending:
                    pending[iid] = pending[iid].model_copy(update={"addressed": True})
            case EventType.INSTANCE_TERMINATED:
                terminal = InstanceStatus(TerminationStatus(_s(p, "status", "error")).value)
            case _:
                pass  # non-state-affecting event (oversight, registry, etc.)

    if terminal is not None:
        status = terminal
    elif gates:
        status = InstanceStatus.AWAITING
    elif started:
        status = InstanceStatus.RUNNING
    else:
        status = InstanceStatus.CREATED

    return DialogueInstance(
        instance_id=header.instance_id,
        template_ref=header.template_ref,
        owner=header.owner,
        visibility=header.visibility,
        dcp_version=header.dcp_version,
        status=status,
        turn=turn,
        roster=list(roster.values()),
        messages=messages,
        events=events,
        open_gates=list(gates.values()),
        pending_inputs=list(pending.values()),
        budget=Budget(turns_used=turn),
    )


__all__ = ["replay"]
