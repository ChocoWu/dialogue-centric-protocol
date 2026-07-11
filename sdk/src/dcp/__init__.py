"""DCP — Dialogue-centric Protocol, reference Python SDK.

Curated public surface. The behavioral contract is ``SPEC.md`` (v0.2.0-draft); the
Pydantic models in ``dcp.schema`` are the authoritative machine-readable definition
(Normative Content clause).
"""

from __future__ import annotations

from . import (
    authoring,
    config,
    delivery,
    errors,
    orchestration,
    participation,
    plugins,
    presets,
    provider,
    registry,
    schema,
    state,
)
from .authoring import TemplateGenerator
from .config import Config, load_dotenv
from .delivery import HttpSseDelivery, build_app
from .errors import DCPError
from .orchestration import ControlPolicy, DialogueContext, Orchestrator
from .participation import ParticipantRegistry, cast_roles
from .plugins import available_plugins, list_plugins, load_plugin
from .presets import get_preset, list_presets
from .provider import MockProvider, ModelProvider, available_providers, build_provider
from .registry import (
    AnonymousAuthenticator,
    Authenticator,
    Registry,
    SimpleTokenAuthenticator,
)
from .server import Server
from .state import SqlStore, restore

#: Package (distribution) version — PEP 440.
__version__ = "0.2.0.dev0"

#: Wire protocol version echoed on instances/envelopes (SPEC ``dcp_version``).
PROTOCOL_VERSION = "0.2.0"

__all__ = [
    "__version__",
    "PROTOCOL_VERSION",
    "Config",
    "load_dotenv",
    "DCPError",
    "SqlStore",
    "restore",
    "ParticipantRegistry",
    "cast_roles",
    "ModelProvider",
    "MockProvider",
    "build_provider",
    "available_providers",
    "Orchestrator",
    "ControlPolicy",
    "DialogueContext",
    "Registry",
    "Authenticator",
    "SimpleTokenAuthenticator",
    "AnonymousAuthenticator",
    "TemplateGenerator",
    "Server",
    "list_plugins",
    "available_plugins",
    "load_plugin",
    "list_presets",
    "get_preset",
    "HttpSseDelivery",
    "build_app",
    "config",
    "errors",
    "schema",
    "state",
    "participation",
    "provider",
    "orchestration",
    "registry",
    "delivery",
    "authoring",
    "plugins",
    "presets",
]
