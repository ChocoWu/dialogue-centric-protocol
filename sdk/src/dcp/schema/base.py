"""Shared Pydantic base models for DCP schema (SPEC §4, §1.10 extension rule)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DCPModel(BaseModel):
    """Base for all DCP entities/records.

    ``extra="forbid"`` implements SPEC §1.10: unknown top-level fields MUST be rejected.
    Openness where wanted is expressed *explicitly* via a typed ``metadata`` field, never
    by tolerating arbitrary extra keys.
    """

    model_config = ConfigDict(extra="forbid")


class FrozenDCPModel(DCPModel):
    """Immutable variant for append-only records (Message, Event — SPEC §1.8/§1.9)."""

    model_config = ConfigDict(extra="forbid", frozen=True)


__all__ = ["DCPModel", "FrozenDCPModel"]
