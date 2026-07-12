"""Environment-driven configuration (locked env-var names, owner decision 2026-07-09).

Locked names:
  DCP_MODEL_PROVIDER  default "openai"  (also "anthropic" | "mock")
  DCP_MODEL           per-provider model-id override (no hardcoded default)
  OPENAI_API_KEY      OpenAI credential
  ANTHROPIC_API_KEY   Anthropic credential
  DCP_DATABASE_URL    default "sqlite:///./dcp.db"

Per D8, this holds only the *orchestrator/global default* model settings; each agent
participant may carry its own ``model_binding`` (SPEC §1.5). API keys are resolved here
from the environment by provider and are never stored in a schema object.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL_PROVIDER = "openai"
DEFAULT_DATABASE_URL = "sqlite:///./dcp.db"

# Provider name -> the env var holding its API key.
_PROVIDER_KEY_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "local": "DCP_LOCAL_API_KEY",  # optional; most local servers ignore it
    "transformers": "",  # in-process HF model — no key
    "mock": "",  # no key needed
}


def load_dotenv(path: str | Path = ".env", *, override: bool = False) -> None:
    """Load simple ``KEY=VALUE`` lines from a .env file into ``os.environ``.

    Deliberately dependency-free and minimal: ignores blank lines and ``#`` comments,
    strips one layer of surrounding quotes, and (unless ``override``) does not clobber
    variables already set in the environment. Missing file is a no-op.
    """
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Config:
    """Resolved DCP configuration (orchestrator/global defaults)."""

    model_provider: str = DEFAULT_MODEL_PROVIDER
    model: str | None = None
    database_url: str = DEFAULT_DATABASE_URL
    base_url: str | None = None      # OpenAI-compatible endpoint for the `local` provider (6.3a)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        """Build config from a mapping (defaults to ``os.environ``)."""
        e = os.environ if env is None else env
        return cls(
            model_provider=e.get("DCP_MODEL_PROVIDER", DEFAULT_MODEL_PROVIDER),
            model=e.get("DCP_MODEL") or None,
            database_url=e.get("DCP_DATABASE_URL", DEFAULT_DATABASE_URL),
            base_url=e.get("DCP_BASE_URL") or None,
        )

    @staticmethod
    def api_key_for(provider: str, env: Mapping[str, str] | None = None) -> str | None:
        """Resolve the API key for a provider from the environment (D8 / TBD-30).

        Returns ``None`` for providers that need no key (``mock``) or when the key is
        unset. Unknown providers also return ``None``.
        """
        e = os.environ if env is None else env
        var = _PROVIDER_KEY_ENV.get(provider)
        if not var:
            return None
        return e.get(var) or None


__all__ = [
    "Config",
    "load_dotenv",
    "DEFAULT_MODEL_PROVIDER",
    "DEFAULT_DATABASE_URL",
]
