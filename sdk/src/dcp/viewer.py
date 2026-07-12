"""Human-readable replay of a dialogue (Phase 6.4).

Renders the append-only log as a **timeline** — the transcript interleaved with the orchestrator's
control decisions and pre/post oversight verdicts — so you see not just *what* was said but *why*
the orchestrator selected, recovered, revised, escalated, suspended, or stopped. It reads the raw
ordered records (which preserve the true message↔event ordering that the split ``DialogueInstance``
loses), for debugging custom policies/oversight and for audit/trust.
"""

from __future__ import annotations

from .schema import Event, EventType, Message
from .state import Record, Store, restore

_SKIP = {EventType.CONTRIBUTION_RECORDED}   # redundant — the Message line already shows it


def _fmt_message(m: Message) -> str:
    decision = m.metadata.get("decision")
    tag = f"  [{decision}]" if decision else ""
    return f"  > [t{m.turn_id}] {m.role_id}: {m.content}{tag}"


def _fmt_event(e: Event) -> str | None:
    if e.type in _SKIP:
        return None
    p = e.payload
    match e.type:
        case EventType.TURN_ASSIGNED:
            detail = f"turn {p.get('turn')} -> {p.get('target_role_id')}"
        case EventType.PRE_ACTION_VERIFIED:
            rec = " (recovered)" if p.get("recovered") else ""
            detail = (f"pre {p.get('role_id')}: readiness={p.get('readiness')} "
                      f"-> {p.get('recommended_action')}{rec}")
        case EventType.POST_ACTION_VERIFIED:
            esc = " (escalated)" if p.get("escalated") else ""
            detail = f"post: verdict={p.get('verdict')} -> {p.get('outcome')}{esc}"
        case EventType.REVISION_REQUESTED:
            detail = f"revision requested: {p.get('role_id')}"
        case EventType.VERIFICATION_REQUESTED:
            detail = f"verification requested (verifier={p.get('verifier_role_id')})"
        case EventType.CONTEXT_INJECTED:
            detail = f"context injected -> {p.get('target_role_id')}"
        case EventType.GATE_OPENED:
            detail = f"gate opened ({p.get('role_id')})"
        case EventType.GATE_RESOLVED:
            detail = "gate resolved"
        case EventType.INSTANCE_SUSPENDED:
            detail = f"suspended: {p.get('reason')}"
        case EventType.INSTANCE_TERMINATED:
            detail = f"terminated: {p.get('status')} — {p.get('reason')}"
        case EventType.ROLES_CAST:
            roles = p.get("roles")
            items = roles if isinstance(roles, list) else []
            pairs = ", ".join(f"{r.get('role_id')}<-{r.get('participant_id')}"
                              for r in items if isinstance(r, dict))
            detail = f"roles cast: {pairs}"
        case EventType.PARTICIPANT_JOINED:
            detail = f"joined {p.get('participant_id')} ({p.get('tier')})"
        case EventType.PARTICIPANT_LEFT:
            detail = f"left {p.get('participant_id')}"
        case EventType.HUMAN_INPUT_PENDING:
            detail = f"human input pending ({p.get('kind')}) from {p.get('from_participant')}"
        case EventType.HUMAN_INPUT_ADDRESSED:
            detail = f"human input addressed by {p.get('addressed_by')}"
        case _:
            detail = e.type.value.replace("_", " ")
    return f"  · {detail}"


def _fmt(record: Record) -> str | None:
    return _fmt_message(record) if isinstance(record, Message) else _fmt_event(record)


def render_timeline(store: Store, instance_id: str) -> str:
    """Render an instance's full log as a readable timeline (raises if the instance is unknown)."""
    inst = restore(store, instance_id)                 # status/turn (+ existence check)
    records = store.load_records(instance_id)          # the true ordered log
    header = [
        f"instance {inst.instance_id}  status={inst.status.value}  "
        f"owner={inst.owner}  turn={inst.turn}",
        f"template {inst.template_ref.template_id}@{inst.template_ref.version}",
        "",
    ]
    body = [line for r in records if (line := _fmt(r)) is not None]
    return "\n".join(header + body)


__all__ = ["render_timeline"]
