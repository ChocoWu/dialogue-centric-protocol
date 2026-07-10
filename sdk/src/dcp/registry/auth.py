"""Bearer-token authentication (SPEC §1.6, D6).

Auth answers *who you are* (a `participant_id`); access tiers (``dcp.participation.tiers``) answer
*what you may do*. Verification is behind a pluggable :class:`Authenticator`; DCP ships a simple
token map for production wiring and an **anonymous dev mode** so the local hello-world needs no key.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..errors import AuthError

#: The synthetic participant id used by :class:`AnonymousAuthenticator` (dev mode).
LOCAL_PARTICIPANT = "@local"


@runtime_checkable
class Authenticator(Protocol):
    """Resolves a bearer token to exactly one ``participant_id`` (SPEC §1.6). I/O edge."""

    def authenticate(self, token: str | None) -> str: ...


class SimpleTokenAuthenticator:
    """Verifier over an in-memory ``token -> participant_id`` map (built-in production stand-in)."""

    def __init__(self, tokens: dict[str, str]) -> None:
        self._tokens = dict(tokens)

    def authenticate(self, token: str | None) -> str:
        if token is None:
            raise AuthError("missing bearer token")
        pid = self._tokens.get(token)
        if pid is None:
            raise AuthError("unknown bearer token")
        return pid


class AnonymousAuthenticator:
    """Dev mode (SPEC §1.6): token optional; every request is one synthetic local participant."""

    def __init__(self, participant_id: str = LOCAL_PARTICIPANT) -> None:
        self._participant_id = participant_id

    def authenticate(self, token: str | None = None) -> str:
        return self._participant_id


__all__ = [
    "Authenticator",
    "SimpleTokenAuthenticator",
    "AnonymousAuthenticator",
    "LOCAL_PARTICIPANT",
]
