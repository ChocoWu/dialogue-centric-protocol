"""Owner-controlled context projection (Phase 7C, D12).

Remoting a control policy or agent sends dialogue content beyond the owner's boundary. The manifest
may *ask* for context (``context_requirements``), but the **owner** decides what is actually
transmitted — that decision is this :class:`ContextProjection`. :func:`project_context` applies it
to a read-only ``DialogueContext`` and also returns a :class:`ProjectionAudit` (fields + payload
digest + byte size) so the transmission is recordable without necessarily keeping the full payload.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from ..orchestration.context import DialogueContext
from ..schema.base import DCPModel


class ContextProjection(DCPModel):
    """What of a ``DialogueContext`` may leave the owner's boundary. Owner-set, per-field (D12)."""

    transcript: Literal["full", "summary", "omit"] = "full"
    roster: Literal["full", "roles_only", "omit"] = "roles_only"
    # (participant_profiles / event_history are not projected in v1 — the payload carries no profile
    #  or event data — so they are omitted rather than advertised as no-op knobs.)


@dataclass(frozen=True)
class ProjectionAudit:
    """A recordable summary of what was transmitted — policy + digest, not the payload itself."""

    fields: tuple[str, ...]
    payload_digest: str          # sha256 of the serialized payload
    byte_size: int


def _summarize(messages: tuple[Any, ...]) -> str:
    return " | ".join(f"{m.role_id}: {m.content[:80]}" for m in messages[-6:])


def project_context(
    ctx: DialogueContext, projection: ContextProjection | None = None
) -> tuple[dict[str, Any], ProjectionAudit]:
    """Project ``ctx`` to a transmittable payload + an audit record (D12)."""
    proj = projection or ContextProjection()
    payload: dict[str, Any] = {
        "instance_id": ctx.instance_id,
        "goal": ctx.goal,
        "topic": ctx.topic,
        "termination_condition": ctx.termination_condition,
        "max_turns": ctx.max_turns,
        "orchestration_mode": ctx.orchestration_mode.value,
        "status": ctx.status.value,
        "turn": ctx.turn,
        "last_speaker": ctx.last_speaker,
        "rejected_this_turn": sorted(ctx.rejected_this_turn),
        "roles": [{"role_id": r.role_id, "name": r.name, "kind": r.kind.value,
                   "response_requirement": r.response_requirement.value} for r in ctx.roles],
    }

    if proj.transcript == "full":
        payload["transcript"] = [{"role_id": m.role_id, "content": m.content} for m in ctx.messages]
    elif proj.transcript == "summary":
        payload["transcript_summary"] = _summarize(ctx.messages)

    if proj.roster == "full":
        payload["roster"] = [{"participant_id": r.participant_id, "role_id": r.role_id,
                              "tier": r.tier.value} for r in ctx.roster]
    elif proj.roster == "roles_only":
        payload["roster_roles"] = [r.role_id for r in ctx.roster if r.role_id]

    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    audit = ProjectionAudit(
        fields=tuple(payload.keys()),
        payload_digest=hashlib.sha256(blob).hexdigest(),
        byte_size=len(blob),
    )
    return payload, audit


__all__ = ["ContextProjection", "ProjectionAudit", "project_context"]
