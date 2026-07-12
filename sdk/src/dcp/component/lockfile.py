"""Lockfile (Phase 7B, D17) — a reproducible record of a resolved component.

A :class:`ComponentResolutionPlan` already captures the full, side-effect-free resolution: the
manifest, selected mode, dependency graph, and artifact digests. Serializing it to a lockfile
(``dcp-components.lock``) lets a later build re-provision the *same* bytes without re-resolving
mutable references (git tags, HF revisions) — the reproducibility guarantee behind D15/D17/D19.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from ..schema.base import DCPModel
from .resolver import ComponentResolutionPlan


class Lockfile(DCPModel):
    """A versioned wrapper around a resolved plan."""

    lock_version: Literal["1.0"] = "1.0"
    plan: ComponentResolutionPlan


def build_lock(plan: ComponentResolutionPlan) -> Lockfile:
    return Lockfile(plan=plan)


def write_lock(plan: ComponentResolutionPlan, path: str | Path) -> Path:
    """Serialize ``plan`` to a lockfile at ``path`` and return it."""
    p = Path(path)
    p.write_text(build_lock(plan).model_dump_json(indent=2), encoding="utf-8")
    return p


def read_lock(path: str | Path) -> ComponentResolutionPlan:
    """Load the resolved plan recorded in a lockfile."""
    return Lockfile.model_validate_json(Path(path).read_text(encoding="utf-8")).plan


__all__ = ["Lockfile", "build_lock", "write_lock", "read_lock"]
