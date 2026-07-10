"""Registry & Hosting layer (SPEC §3.4): template/participant catalogs, hosting ops, and auth."""

from __future__ import annotations

from .auth import (
    LOCAL_PARTICIPANT,
    AnonymousAuthenticator,
    Authenticator,
    SimpleTokenAuthenticator,
)
from .hosting import Registry

__all__ = [
    "Registry",
    "Authenticator",
    "SimpleTokenAuthenticator",
    "AnonymousAuthenticator",
    "LOCAL_PARTICIPANT",
]
