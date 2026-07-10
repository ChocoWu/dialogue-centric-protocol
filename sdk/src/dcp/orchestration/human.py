"""Human intervention gateway (SPEC §2.8). How the orchestrator solicits human input.

A ``HumanReply`` with ``content is None`` means no response within the window (timeout). The
Delivery layer (M7) will provide a real gateway; ``ScriptedHumanGateway`` drives tests.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from ..schema import HumanPolicy, Role


class HumanReply(BaseModel):
    """A human's response. ``content is None`` == timeout / no response."""

    content: str | None = None
    decision: str | None = None   # for gates: "approve" | "reject" | "revise"


class HumanGateway(Protocol):
    """Solicits input from the human filling ``role`` (SPEC §2.8)."""

    async def request(
        self, *, role: Role, policy: HumanPolicy | None, blocking: bool
    ) -> HumanReply: ...


class ScriptedHumanGateway:
    """Test gateway: returns a scripted reply per ``role_id``; unknown roles time out."""

    def __init__(self, replies: dict[str, HumanReply] | None = None) -> None:
        self._replies = dict(replies or {})

    async def request(
        self, *, role: Role, policy: HumanPolicy | None, blocking: bool
    ) -> HumanReply:
        return self._replies.get(role.role_id, HumanReply(content=None))


__all__ = ["HumanReply", "HumanGateway", "ScriptedHumanGateway"]
