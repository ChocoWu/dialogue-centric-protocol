"""Role casting (SPEC §2.4): bind template roles to registered participants.

Precedence (from the draft): explicit binding → role_id matches a participant id →
capability overlap → persona-based fallback. Casting a participant into a role requires that
participant to hold ≥ ``speak`` tier (SPEC §6; enforced via :func:`tiers.assert_castable`).
"""

from __future__ import annotations

from ..errors import AccessError, RegistryError
from ..schema import (
    AccessTier,
    DialogueTemplate,
    Participant,
    Role,
    RoleCastEntry,
    RolesCast,
)
from .tiers import assert_castable


def _words(*parts: str) -> set[str]:
    return {w for part in parts for w in part.lower().split()}


def _choose(
    role: Role,
    by_id: dict[str, Participant],
    used: set[str],
) -> str | None:
    """Resolve one role to a participant id by the SPEC §2.4 precedence, or ``None``."""
    # 1. explicit / reserved binding — authoritative.
    bound = role.binding.participant_id
    if bound is not None:
        p = by_id.get(bound)
        if p is None:
            raise RegistryError(f"role {role.role_id!r} bound to unknown participant {bound!r}")
        if p.kind is not role.kind:
            raise AccessError(f"role {role.role_id!r} ({role.kind}) bound to {p.kind} participant")
        return bound

    available = [
        p for p in by_id.values() if p.kind is role.kind and p.participant_id not in used
    ]

    # 2. role_id matches a registered participant id.
    match = by_id.get(role.role_id)
    if match is not None and match.kind is role.kind and role.role_id not in used:
        return role.role_id

    # 3. capability overlap — most shared words between role and participant descriptions.
    role_words = _words(role.name, role.persona)
    scored: list[tuple[int, str]] = []
    for p in available:
        overlap = len(role_words & _words(p.display_name, p.profile))
        if overlap:
            scored.append((overlap, p.participant_id))
    if scored:
        scored.sort(key=lambda s: (-s[0], s[1]))
        return scored[0][1]

    # 4. persona-based fallback — first available participant of the right kind.
    if available:
        return min(available, key=lambda p: p.participant_id).participant_id
    return None


def cast_roles(
    template: DialogueTemplate,
    participants: list[Participant],
    instance_id: str,
    tiers: dict[str, AccessTier] | None = None,
) -> RolesCast:
    """Cast every template role to a participant, honoring precedence and tier rules.

    ``tiers`` maps participant_id → the tier it will hold in the instance (default ``speak``).
    Raises :class:`AccessError` on a tier/kind violation, :class:`RegistryError` if a role has
    no eligible participant.
    """
    grants = tiers or {}
    by_id = {p.participant_id: p for p in participants}
    used: set[str] = set()
    entries: list[RoleCastEntry] = []
    for role in template.roles:
        pid = _choose(role, by_id, used)
        if pid is None:
            raise RegistryError(f"no eligible {role.kind} participant for role {role.role_id!r}")
        assert_castable(grants.get(pid, AccessTier.SPEAK))
        used.add(pid)
        entries.append(RoleCastEntry(role_id=role.role_id, participant_id=pid))
    return RolesCast(instance_id=instance_id, roles=entries)


__all__ = ["cast_roles"]
