"""Participant registry (SPEC §1.5/§3.4; D4) — a thin, Store-backed catalog of participants.

Registration establishes *who exists and can be found*; casting (see ``casting``) binds *who
fills a role in a given dialogue*. Unified with the template catalog in the Registry & Hosting
layer (M6).
"""

from __future__ import annotations

from ..schema import Participant
from ..state import Store


class ParticipantRegistry:
    """Server-level catalog of registered participants, persisted via a :class:`Store`."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def register(self, participant: Participant) -> None:
        """Register a participant (raises ``RegistryError`` on duplicate id)."""
        self._store.register_participant(participant)

    def get(self, participant_id: str) -> Participant | None:
        return self._store.get_participant(participant_id)

    def list(self, *, discoverable_only: bool = False) -> list[Participant]:
        """List participants; ``discoverable_only`` keeps only ``discoverable=True`` (D4)."""
        return self._store.list_participants(discoverable_only=discoverable_only)


__all__ = ["ParticipantRegistry"]
