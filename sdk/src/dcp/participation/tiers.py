"""Access-tier logic (SPEC §1.6; D5). ``own`` ⊃ ``speak`` ⊃ ``observe``."""

from __future__ import annotations

from ..errors import AccessError
from ..schema import AccessTier

_RANK: dict[AccessTier, int] = {AccessTier.OBSERVE: 0, AccessTier.SPEAK: 1, AccessTier.OWN: 2}


def tier_allows(held: AccessTier, required: AccessTier) -> bool:
    """True iff a participant holding ``held`` also has the authority of ``required``."""
    return _RANK[held] >= _RANK[required]


def can_speak(tier: AccessTier) -> bool:
    """True iff the tier may contribute Messages / be cast into a role (≥ speak)."""
    return tier_allows(tier, AccessTier.SPEAK)


def can_observe(tier: AccessTier) -> bool:
    """Every tier can read the transcript."""
    return True


def assert_castable(tier: AccessTier) -> None:
    """Raise if ``tier`` may not be cast into a speaking role (SPEC §6: observe MUST NOT)."""
    if not can_speak(tier):
        raise AccessError(f"tier {tier.value!r} cannot be cast into a speaking role (needs speak)")


__all__ = ["tier_allows", "can_speak", "can_observe", "assert_castable"]
