"""M6 — bearer auth + anonymous dev mode (SPEC §1.6 D6; §6 auth/identity)."""

from __future__ import annotations

import pytest

from dcp.errors import AuthError
from dcp.registry import AnonymousAuthenticator, SimpleTokenAuthenticator


def test_simple_token_resolves_to_one_participant() -> None:
    auth = SimpleTokenAuthenticator({"tok-a": "@alice", "tok-b": "@bob"})
    assert auth.authenticate("tok-a") == "@alice"
    assert auth.authenticate("tok-b") == "@bob"


def test_simple_token_rejects_unknown_and_missing() -> None:
    auth = SimpleTokenAuthenticator({"tok-a": "@alice"})
    with pytest.raises(AuthError):
        auth.authenticate("nope")
    with pytest.raises(AuthError):
        auth.authenticate(None)


def test_anonymous_dev_mode_resolves_synthetic_participant() -> None:
    auth = AnonymousAuthenticator()
    # token optional; always the single synthetic local participant
    assert auth.authenticate(None) == auth.authenticate("anything") == "@local"


def test_anonymous_participant_id_is_configurable() -> None:
    assert AnonymousAuthenticator(participant_id="@dev").authenticate(None) == "@dev"
