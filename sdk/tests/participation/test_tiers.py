"""M3 — access-tier logic (SPEC §1.6/§6; D5)."""

from __future__ import annotations

import pytest

from dcp import participation as part
from dcp.errors import AccessError
from dcp.schema import AccessTier


def test_tier_ordering() -> None:
    assert part.tier_allows(AccessTier.OWN, AccessTier.SPEAK)
    assert part.tier_allows(AccessTier.OWN, AccessTier.OBSERVE)
    assert part.tier_allows(AccessTier.SPEAK, AccessTier.OBSERVE)
    assert not part.tier_allows(AccessTier.OBSERVE, AccessTier.SPEAK)
    assert not part.tier_allows(AccessTier.SPEAK, AccessTier.OWN)


def test_can_speak_and_observe() -> None:
    assert part.can_speak(AccessTier.OWN) and part.can_speak(AccessTier.SPEAK)
    assert not part.can_speak(AccessTier.OBSERVE)
    for t in AccessTier:
        assert part.can_observe(t)


def test_assert_castable_rejects_observe() -> None:
    part.assert_castable(AccessTier.OWN)
    part.assert_castable(AccessTier.SPEAK)
    with pytest.raises(AccessError):
        part.assert_castable(AccessTier.OBSERVE)
