"""Participation layer (SPEC §3.2): casting, access tiers, and the participant registry."""

from __future__ import annotations

from .casting import cast_roles
from .registry import ParticipantRegistry
from .tiers import assert_castable, can_observe, can_speak, tier_allows

__all__ = [
    "cast_roles",
    "ParticipantRegistry",
    "tier_allows",
    "can_speak",
    "can_observe",
    "assert_castable",
]
