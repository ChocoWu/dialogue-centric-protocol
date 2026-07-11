"""Typed exception hierarchy for the DCP SDK.

Every error raised by the SDK derives from :class:`DCPError`, so callers can catch
the whole family or narrow to a specific failure. Terminal dialogue *statuses*
(``done``/``provisional``/``stopped``/``budget``/``error``) are NOT exceptions — they
are outcomes recorded on the instance (see ``schema`` / SPEC §2.10).
"""

from __future__ import annotations


class DCPError(Exception):
    """Base class for all DCP SDK errors."""


class SchemaError(DCPError):
    """A value failed validation against a DCP schema (SPEC §4)."""


class AccessError(DCPError):
    """An operation was denied by the access-control model (D5 / SPEC §1.6)."""


class AuthError(DCPError):
    """Authentication failed or a bearer token could not be resolved (D6)."""


class RegistryError(DCPError):
    """A registry/hosting operation failed (SPEC §3.4) — e.g. template immutability."""


class OrchestrationError(DCPError):
    """The orchestration loop hit an unrecoverable condition (SPEC §1.7 / §3.3)."""


class ProviderError(DCPError):
    """A model provider call failed (SPEC §1.5/§1.7 model binding; D7/D8)."""


class TerminationError(DCPError):
    """An instance could not be terminated cleanly (SPEC §2.10)."""


class PluginError(DCPError):
    """A pluggable component could not be discovered or loaded (dcp.plugins entry points)."""


__all__ = [
    "DCPError",
    "SchemaError",
    "AccessError",
    "AuthError",
    "RegistryError",
    "OrchestrationError",
    "ProviderError",
    "TerminationError",
    "PluginError",
]
