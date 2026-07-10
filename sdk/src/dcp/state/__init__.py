"""Dialogue State layer (SPEC §3.1): the append-only log, its store, and replay/restore (D3)."""

from __future__ import annotations

from ..errors import RegistryError
from ..schema import DialogueInstance
from .reducer import replay
from .store import InstanceHeader, Record, SqlStore, Store


def restore(store: Store, instance_id: str) -> DialogueInstance:
    """Full-replay restore (D3/TBD-28): rebuild an instance from its persisted log.

    The same path serves the orchestrator rehydrating and a late joiner catching up.
    """
    header = store.get_header(instance_id)
    if header is None:
        raise RegistryError(f"unknown instance {instance_id!r}")
    return replay(header, store.load_records(instance_id))


__all__ = ["Store", "SqlStore", "InstanceHeader", "Record", "replay", "restore"]
