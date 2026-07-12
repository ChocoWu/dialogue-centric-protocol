"""M4+ — provider advertisement for ServerInfo (SPEC §1.11; no keys leaked)."""

from __future__ import annotations

from dcp.provider import SUPPORTED_PROVIDERS, available_providers


def test_lists_all_supported_providers() -> None:
    infos = available_providers(env={})
    assert {i.provider for i in infos} == set(SUPPORTED_PROVIDERS)


def test_mock_is_always_configured_real_providers_follow_env() -> None:
    infos = {i.provider: i.configured for i in available_providers(env={"OPENAI_API_KEY": "sk-x"})}
    assert infos["mock"] is True
    assert infos["openai"] is True          # key present
    assert infos["anthropic"] is False      # key absent


def test_no_keys_means_only_mock_configured() -> None:
    infos = {i.provider: i.configured for i in available_providers(env={})}
    assert infos == {"mock": True, "openai": False, "anthropic": False,
                     "local": False, "transformers": False}


def test_local_is_configured_by_endpoint_not_a_key() -> None:
    infos = {i.provider: i.configured
             for i in available_providers(env={"DCP_BASE_URL": "http://localhost:11434/v1"})}
    assert infos["local"] is True and infos["mock"] is True
