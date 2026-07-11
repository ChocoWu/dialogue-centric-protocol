"""Value objects for DCP schema (SPEC §4). Small composites reused by entities.

Field-level constraints here are the interim contract; exhaustive constraints are TBD-18
(pinned during this authoring). ``[TBD-18]`` items are marked where they remain loose.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field, StringConstraints

from .base import DCPModel
from .enums import AccessTier, OnTimeout, OrchestrationMode

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
#: Semantic-version string (SPEC Versioning). ``[TBD-18]`` pre-release/build suffixes deferred.
SemVer = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]


class ModelBinding(DCPModel):
    """Which model backs a consumer (D7/D8; SPEC §4.5b). No credential field —
    the API key is resolved from the environment by ``provider`` (D8 / TBD-30)."""

    provider: NonEmptyStr          # "openai" | "anthropic" | "mock" | ...
    model: NonEmptyStr


class TerminationPolicy(DCPModel):
    """Template termination policy (SPEC §4.1)."""

    condition: str
    max_turns: Annotated[int, Field(ge=1)] | None = None
    token_budget: Annotated[int, Field(ge=1)] | None = None


class Edge(DCPModel):
    """A flow edge — an allowed succession between roles (SPEC §2.6; TBD-11).

    ``condition`` is free-text guidance (not machine-evaluated): at a branch it is shown to the
    orchestrator's model to help it choose among the allowed next roles.
    """

    from_role: NonEmptyStr
    to_role: NonEmptyStr
    condition: str | None = None


class Flow(DCPModel):
    """A succession graph — may be non-linear (branches, loops) (SPEC §2.6).

    The **initial/default** order, not a rigid script: advisory under ``mode=plan`` (a hint), and
    guiding under ``mode=flow`` (succession is constrained to the edges; deterministic when a role
    has one outgoing edge, model-chosen among the allowed roles at a branch). Either way the
    oversight loop may adapt the realized path (e.g. switch to an alternative when a candidate isn't
    ready).
    """

    entry: NonEmptyStr
    edges: list[Edge] = []


class HumanPolicy(DCPModel):
    """Per-role wait window + timeout behavior for waited human roles (SPEC §2.8; TBD-14)."""

    wait_window_seconds: int | None = None
    on_timeout: OnTimeout = OnTimeout.FINALIZE_PROVISIONAL


class Budget(DCPModel):
    """Instance budget: consumed vs. limits (SPEC §4.2)."""

    turns_used: int = 0
    tokens_used: int = 0
    max_turns: int | None = None
    token_budget: int | None = None


class RoleBinding(DCPModel):
    """A Role's intended participant (SPEC §1.4). Empty => cast by capability/persona."""

    participant_id: NonEmptyStr | None = None


class Orchestration(DCPModel):
    """Template orchestration settings (SPEC §2.6). Optional model_binding is the
    template-level orchestrator default (D8); env/instance may override."""

    mode: OrchestrationMode = OrchestrationMode.PLAN
    model_binding: ModelBinding | None = None


class Gate(DCPModel):
    """An open human gate on an instance (SPEC §2.8). Minimal; TBD-18/8 refine."""

    gate_id: NonEmptyStr
    role_id: NonEmptyStr


class PendingInput(DCPModel):
    """A queued asynchronous human input (SPEC §2.6/§2.8 concurrency model, TBD-25)."""

    input_id: NonEmptyStr
    kind: str                       # "optional" | "open_mic" | "gate_response" (TBD-18)
    content: str | None = None
    from_participant: NonEmptyStr | None = None
    addressed: bool = False


class AccessGrant(DCPModel):
    """A participant's access tier on an instance (SPEC §1.6/§4.5; D5)."""

    instance_id: NonEmptyStr
    participant_id: NonEmptyStr
    tier: AccessTier
    granted_by: NonEmptyStr
    granted_at: datetime


class TemplateRef(DCPModel):
    """Reference to a registered template version (SPEC §4.2)."""

    template_id: NonEmptyStr
    version: SemVer


class RosterEntry(DCPModel):
    """An instance roster row: a participant, its tier, and (if cast) its role (SPEC §4.2)."""

    participant_id: NonEmptyStr
    tier: AccessTier
    role_id: NonEmptyStr | None = None


class Capabilities(DCPModel):
    """Server capability flags (SPEC §1.10/§1.11; D9). Typed + extensible via new MINOR fields."""

    auto_generate: bool = False        # §2.2 template auto-generation
    verifier_routing: bool = False     # §1.7 request_verification routing


class ProviderInfo(DCPModel):
    """One advertised model provider (SPEC §1.11). ``configured`` never exposes the credential."""

    provider: NonEmptyStr
    configured: bool


class ServerInfo(DCPModel):
    """What a DCP server advertises about itself (SPEC §1.11; D9)."""

    dcp_version: SemVer
    capabilities: Capabilities = Field(default_factory=Capabilities)
    model_providers: list[ProviderInfo] = Field(default_factory=list)
    #: Installed plugins by entry-point group → names (dcp.plugins; 6.1d).
    plugins: dict[str, list[str]] = Field(default_factory=dict)


__all__ = [
    "NonEmptyStr",
    "SemVer",
    "ModelBinding",
    "TerminationPolicy",
    "Edge",
    "Flow",
    "HumanPolicy",
    "Budget",
    "RoleBinding",
    "Orchestration",
    "Gate",
    "PendingInput",
    "AccessGrant",
    "TemplateRef",
    "RosterEntry",
    "Capabilities",
    "ProviderInfo",
    "ServerInfo",
]
