"""M0 — package, error hierarchy, and config smoke tests."""

from __future__ import annotations

import os

import dcp
from dcp import config, errors


def test_package_metadata() -> None:
    assert dcp.__version__ == "0.2.0.dev0"
    assert dcp.PROTOCOL_VERSION == "0.2.0"


def test_error_hierarchy() -> None:
    for exc in (
        errors.SchemaError,
        errors.AccessError,
        errors.AuthError,
        errors.RegistryError,
        errors.OrchestrationError,
        errors.ProviderError,
        errors.TerminationError,
    ):
        assert issubclass(exc, errors.DCPError)


def test_config_defaults() -> None:
    cfg = config.Config.from_env(env={})
    assert cfg.model_provider == "openai"          # locked default
    assert cfg.model is None
    assert cfg.database_url == "sqlite:///./dcp.db"


def test_config_from_env_overrides() -> None:
    cfg = config.Config.from_env(
        env={
            "DCP_MODEL_PROVIDER": "anthropic",
            "DCP_MODEL": "claude-opus-4-8",
            "DCP_DATABASE_URL": "postgresql://x/y",
        }
    )
    assert cfg.model_provider == "anthropic"
    assert cfg.model == "claude-opus-4-8"
    assert cfg.database_url == "postgresql://x/y"


def test_api_key_resolution_by_provider() -> None:
    env = {"OPENAI_API_KEY": "sk-o", "ANTHROPIC_API_KEY": "sk-a"}
    assert config.Config.api_key_for("openai", env) == "sk-o"
    assert config.Config.api_key_for("anthropic", env) == "sk-a"
    assert config.Config.api_key_for("mock", env) is None        # no key needed
    assert config.Config.api_key_for("unknown", env) is None
    assert config.Config.api_key_for("openai", {}) is None       # unset


def test_load_dotenv(tmp_path: object) -> None:
    p = tmp_path / ".env"  # type: ignore[operator]
    p.write_text('# a full-line comment\n\nDCP_TEST_ONLY_VAR="from-dotenv"\n', encoding="utf-8")
    assert "DCP_TEST_ONLY_VAR" not in os.environ
    try:
        config.load_dotenv(p)
        assert os.environ["DCP_TEST_ONLY_VAR"] == "from-dotenv"
        # does not override an already-set var unless override=True
        os.environ["DCP_TEST_ONLY_VAR"] = "kept"
        config.load_dotenv(p)
        assert os.environ["DCP_TEST_ONLY_VAR"] == "kept"
        config.load_dotenv(p, override=True)
        assert os.environ["DCP_TEST_ONLY_VAR"] == "from-dotenv"
    finally:
        os.environ.pop("DCP_TEST_ONLY_VAR", None)
