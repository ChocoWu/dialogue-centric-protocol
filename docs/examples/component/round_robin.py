"""The component: a model-free round-robin orchestrator, in two shapes.

- ``RoundRobinPolicy`` is a local :class:`~dcp.orchestration.ControlPolicy` (``decide(ctx)``) —
  what ``materialize`` returns for the ``local`` delivery mode.
- ``decide`` is the same logic as a **remote** wire handler (``decide(payload)``) — what a
  ``ComponentServer`` hosts for the ``remote`` mode. The remote contract is the *projected payload*
  (a dict), not the local ``DialogueContext`` type.

The manifest ``dcp-component.json`` points its ``local`` entrypoint at ``RoundRobinPolicy`` and a
server hosts ``decide``; both drive the identical dialogue (see ``run_local.py`` / ``run_remote.py``).
"""

from __future__ import annotations

from typing import Any

from dcp.orchestration import DialogueContext, OrchestratorAction
from dcp.schema import TerminationStatus


class RoundRobinPolicy:
    """Each role speaks once, in template order, then stop — using no model at all."""

    async def decide(self, ctx: DialogueContext) -> OrchestratorAction:
        spoken = {m.role_id for m in ctx.messages}
        for role in ctx.roles:
            if role.role_id not in spoken:
                return OrchestratorAction(action="select_speaker", target_role_id=role.role_id)
        return OrchestratorAction(action="stop", status=TerminationStatus.DONE)


def decide(payload: dict[str, Any]) -> OrchestratorAction:
    """The same rule as a remote handler: it reads the projected payload, not a DialogueContext."""
    spoken = {m["role_id"] for m in payload.get("transcript", [])}
    for role in payload["roles"]:
        if role["role_id"] not in spoken:
            return OrchestratorAction(action="select_speaker", target_role_id=role["role_id"])
    return OrchestratorAction(action="stop", status=TerminationStatus.DONE)
