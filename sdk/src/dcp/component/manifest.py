"""ComponentManifest — the machine-readable contract for a shareable DCP component (Phase 7A).

The manifest is what A publishes and B reads (PROPOSAL-component-ecosystem.md §4). It is *not* a
wire/SPEC entity; it describes a component's identity, runtime interface, kind-specific spec,
delivery (access) modes, artifact dependencies, and requirements — so the pipeline (§5) can locate,
plan, provision, and instantiate it.

Design decisions encoded here (see the proposal's decision log):
- **D14** kinds split *executable* (materialize to a runtime interface) vs *declarative* (template).
- **D21** identity (`component`) is separate from the kind-specific `spec` (a discriminated union).
- **D18** `interface.name` is namespaced and validated 1:1 against `component.kind`; capabilities
  are namespaced + advisory; `interface.version` ≠ `binding.version`.
- **D19** every `ArtifactReference` carries an immutable digest.
- **D22** remote auth names a logical `credential_slot`, never a user env var.
- **D23** a dependency's `expected_kind` *constrains* the resolved manifest, not a declaration.
- §3 kind × access-mode matrix (templates carry no weights/remote; oversight is not remote in v1).
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator, model_validator

from ..schema.base import DCPModel
from ..schema.enums import ResponseRequirement, Visibility

# --- shared constrained strings --------------------------------------------------------

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
#: SemVer for component versions (major.minor.patch).
SemVer = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]
#: Contract version for an interface or binding (major.minor) — independent axes (D18).
ContractVersion = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+$")]
#: A lowercase-hex sha256 digest (D19) — hex-only so it can't be used as a traversal path segment.
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
#: A remote endpoint — http(s) only (no ``file://`` / ``ftp://`` SSRF/LFI surface via urllib).
HttpUrl = Annotated[str, StringConstraints(pattern=r"^https?://.+")]

_CAPABILITY_RE = re.compile(r"^(dcp|ext)\.[a-z0-9_]+(\.[a-z0-9_]+)*$")


# --- enums -----------------------------------------------------------------------------

class ComponentKind(StrEnum):
    """What a component *is* — its ecosystem classification and materialization target (D14)."""

    CONTROL_POLICY = "control_policy"
    OVERSIGHT_POLICY = "oversight_policy"
    MODEL_PROVIDER = "model_provider"
    AGENT = "agent"
    TEMPLATE = "template"


class InterfaceName(StrEnum):
    """The runtime-interface contract a component instantiates to (D18). Namespaced."""

    CONTROL_POLICY = "dcp.control_policy"
    OVERSIGHT_POLICY = "dcp.oversight_policy"
    MODEL_PROVIDER = "dcp.model_provider"
    AGENT_DEFINITION = "dcp.agent_definition"
    DIALOGUE_TEMPLATE = "dcp.dialogue_template"


class AccessModeType(StrEnum):
    LOCAL = "local"
    REMOTE = "remote"


class PackageSource(StrEnum):
    PYPI = "pypi"
    GIT = "git"
    FILE = "file"


#: Executable kinds materialize to a runtime interface; the rest are declarative (D14).
EXECUTABLE_KINDS = frozenset({
    ComponentKind.CONTROL_POLICY, ComponentKind.OVERSIGHT_POLICY,
    ComponentKind.MODEL_PROVIDER, ComponentKind.AGENT,
})

#: The controlled 1:1 map interface.name ← component.kind (D18).
ALLOWED_INTERFACE_BY_KIND: dict[ComponentKind, InterfaceName] = {
    ComponentKind.CONTROL_POLICY: InterfaceName.CONTROL_POLICY,
    ComponentKind.OVERSIGHT_POLICY: InterfaceName.OVERSIGHT_POLICY,
    ComponentKind.MODEL_PROVIDER: InterfaceName.MODEL_PROVIDER,
    ComponentKind.AGENT: InterfaceName.AGENT_DEFINITION,
    ComponentKind.TEMPLATE: InterfaceName.DIALOGUE_TEMPLATE,
}


def is_executable(kind: ComponentKind) -> bool:
    """True iff ``kind`` materializes to a runtime interface (vs a declarative definition, D14)."""
    return kind in EXECUTABLE_KINDS


# --- identity / metadata / interface ---------------------------------------------------

class ComponentIdentity(DCPModel):
    """Identity block ONLY — no kind-specific fields (D21)."""

    namespace: NonEmptyStr
    name: NonEmptyStr
    version: SemVer
    kind: ComponentKind


class Author(DCPModel):
    name: NonEmptyStr
    contact: str | None = None


class ComponentMetadata(DCPModel):
    description: str = ""
    license: str | None = None
    visibility: Visibility = Visibility.PUBLIC
    authors: list[Author] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class InterfaceDeclaration(DCPModel):
    """The runtime-interface contract. ``version`` is independent of any binding version (D18)."""

    name: InterfaceName
    version: ContractVersion
    config_schema: str | None = None


# --- artifacts (D19) -------------------------------------------------------------------

class Digest(DCPModel):
    algorithm: Literal["sha256"] = "sha256"
    value: Sha256Hex             # hex-only: also prevents cache-path traversal (D19)


class ArtifactRequirements(DCPModel):
    gpu_memory: str | None = None
    disk: str | None = None


class ArtifactReference(DCPModel):
    """A resource a component depends on — never executable; always integrity-checked (D3/D19)."""

    uri: NonEmptyStr
    digest: Digest                                # required: cache key + supply-chain integrity
    size_bytes: Annotated[int, Field(ge=0)] | None = None
    format: str | None = None
    requirements: ArtifactRequirements | None = None
    license: str | None = None


# --- access modes (discriminated on `type`) --------------------------------------------

class PackageImplementation(DCPModel):
    """A local, importable implementation (the entry-point path becomes one such mode, D1)."""

    type: Literal["python_package"] = "python_package"
    source: PackageSource
    package: NonEmptyStr
    version: str | None = None
    entrypoint: NonEmptyStr                       # "module:attr"

    @model_validator(mode="after")
    def _pypi_package_is_a_bare_name(self) -> PackageImplementation:
        # a pypi source must be a plain distribution name — not a URL/VCS/path pip would install
        if self.source is PackageSource.PYPI and not re.match(
                r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$", self.package):
            raise ValueError(f"pypi package must be a bare distribution name, got {self.package!r}")
        return self


class LocalAccessMode(DCPModel):
    type: Literal[AccessModeType.LOCAL] = AccessModeType.LOCAL
    implementation: PackageImplementation
    artifacts: list[ArtifactReference] = Field(default_factory=list)


class Binding(DCPModel):
    protocol: NonEmptyStr                         # e.g. "dcp-http"
    version: ContractVersion                      # transport protocol version ≠ interface.version


class RemoteAuth(DCPModel):
    """Declares *which* credential is needed by a logical slot; the owner maps it (D22)."""

    type: NonEmptyStr = "bearer"
    credential_slot: NonEmptyStr                  # a slot name, NOT an env var
    user_supplied: bool = True


class ContextRequirements(DCPModel):
    """What a remote component *asks* for; the owner still controls the projection (D12)."""

    required: list[str] = Field(default_factory=list)
    optional: list[str] = Field(default_factory=list)


class RemoteAccessMode(DCPModel):
    type: Literal[AccessModeType.REMOTE] = AccessModeType.REMOTE
    binding: Binding
    endpoint: HttpUrl                             # http(s) only — no file://, ftp://, … via urllib
    component_id: NonEmptyStr | None = None       # which component at a multi-component endpoint
    auth: RemoteAuth | None = None
    context_requirements: ContextRequirements | None = None


AccessMode = Annotated[LocalAccessMode | RemoteAccessMode, Field(discriminator="type")]


# --- dependencies (D17/D23) ------------------------------------------------------------

class InterfaceConstraint(DCPModel):
    name: InterfaceName
    version: str                                  # a range spec, e.g. ">=1.0,<2.0"


class DependencyRef(DCPModel):
    """A pinned dependency. ``expected_kind`` is a constraint on the resolved manifest, not a
    declaration by the parent (D23)."""

    ref: NonEmptyStr
    expected_kind: ComponentKind
    interface_constraint: InterfaceConstraint | None = None
    mode_constraint: AccessModeType | None = None


# --- kind-specific spec (discriminated on `kind`, D21) ---------------------------------

class RoleDefaults(DCPModel):
    """Non-authoritative suggestions materialized into a Role before runtime (D8)."""

    persona: str = ""
    response_requirement: ResponseRequirement | None = None


class ControlPolicySpec(DCPModel):
    kind: Literal[ComponentKind.CONTROL_POLICY] = ComponentKind.CONTROL_POLICY


class OversightPolicySpec(DCPModel):
    kind: Literal[ComponentKind.OVERSIGHT_POLICY] = ComponentKind.OVERSIGHT_POLICY


class ModelProviderSpec(DCPModel):
    kind: Literal[ComponentKind.MODEL_PROVIDER] = ComponentKind.MODEL_PROVIDER


class TemplateSpec(DCPModel):
    kind: Literal[ComponentKind.TEMPLATE] = ComponentKind.TEMPLATE


class AgentState(DCPModel):
    """Declared, machine-checkable state of a (possibly remote) agent (D20)."""

    mode: Literal["stateless", "invocation_scoped", "dialogue_scoped", "external"] = "stateless"
    retention: Literal["none", "session", "duration"] = "none"
    reset_supported: bool = False


class AgentSpec(DCPModel):
    kind: Literal[ComponentKind.AGENT] = ComponentKind.AGENT
    provider: DependencyRef | None = None         # a model_provider dependency
    role_defaults: RoleDefaults | None = None
    state: AgentState = Field(default_factory=AgentState)


ComponentSpec = Annotated[
    ControlPolicySpec | OversightPolicySpec | ModelProviderSpec | TemplateSpec | AgentSpec,
    Field(discriminator="kind"),
]


# --- requirements ----------------------------------------------------------------------

class ComponentRequirements(DCPModel):
    dcp: str | None = None
    python: str | None = None


# --- the manifest ----------------------------------------------------------------------

class ComponentManifest(DCPModel):
    """A versioned, deliverable DCP component (PROPOSAL §4). ``extra="forbid"`` like DCP schema."""

    schema_version: Literal["1.0"] = "1.0"
    component: ComponentIdentity
    metadata: ComponentMetadata = Field(default_factory=ComponentMetadata)
    interface: InterfaceDeclaration
    capabilities: list[str] = Field(default_factory=list)
    spec: ComponentSpec
    dependencies: list[DependencyRef] = Field(default_factory=list)
    access_modes: list[AccessMode] = Field(min_length=1)
    requirements: ComponentRequirements | None = None

    @field_validator("capabilities")
    @classmethod
    def _capabilities_namespaced(cls, caps: list[str]) -> list[str]:
        bad = [c for c in caps if not _CAPABILITY_RE.match(c)]
        if bad:
            raise ValueError(f"capabilities must be namespaced (dcp.* / ext.<author>.*): {bad}")
        return caps

    @model_validator(mode="before")
    @classmethod
    def _inject_spec_kind(cls, data: object) -> object:
        """Let authors omit ``spec``/``spec.kind``: seed the discriminator from the identity."""
        if isinstance(data, dict):
            kind = (data.get("component") or {}).get("kind") if isinstance(
                data.get("component"), dict) else None
            if kind is not None:
                spec = data.get("spec")
                if spec is None:
                    data = {**data, "spec": {"kind": kind}}
                elif isinstance(spec, dict) and "kind" not in spec:
                    data = {**data, "spec": {**spec, "kind": kind}}
        return data

    @model_validator(mode="after")
    def _cross_field_rules(self) -> ComponentManifest:
        kind = self.component.kind

        # D18 — interface.name maps 1:1 from kind
        if self.interface.name is not ALLOWED_INTERFACE_BY_KIND[kind]:
            raise ValueError(
                f"interface.name {self.interface.name!r} is not valid for kind {kind!r} "
                f"(expected {ALLOWED_INTERFACE_BY_KIND[kind]!r})")

        # D21 — spec must match the identity's kind (author-supplied spec.kind guard)
        if self.spec.kind is not kind:
            raise ValueError(f"spec.kind {self.spec.kind!r} != component.kind {kind!r}")

        # §3 kind × access-mode matrix
        for mode in self.access_modes:
            if isinstance(mode, RemoteAccessMode):
                if kind is ComponentKind.OVERSIGHT_POLICY:
                    raise ValueError("oversight_policy has no remote mode in v1 (D9: governance "
                                     "stays owner-side)")
                if kind is ComponentKind.TEMPLATE:
                    raise ValueError("template is declarative and has no remote mode")
            elif isinstance(mode, LocalAccessMode) and mode.artifacts:
                if kind is ComponentKind.TEMPLATE:
                    raise ValueError("template carries no model artifacts")
        return self


__all__ = [
    "ComponentKind",
    "InterfaceName",
    "AccessModeType",
    "PackageSource",
    "EXECUTABLE_KINDS",
    "ALLOWED_INTERFACE_BY_KIND",
    "is_executable",
    "ComponentIdentity",
    "Author",
    "ComponentMetadata",
    "InterfaceDeclaration",
    "Digest",
    "ArtifactRequirements",
    "ArtifactReference",
    "PackageImplementation",
    "LocalAccessMode",
    "Binding",
    "RemoteAuth",
    "ContextRequirements",
    "RemoteAccessMode",
    "AccessMode",
    "InterfaceConstraint",
    "DependencyRef",
    "RoleDefaults",
    "ControlPolicySpec",
    "OversightPolicySpec",
    "ModelProviderSpec",
    "TemplateSpec",
    "AgentState",
    "AgentSpec",
    "ComponentSpec",
    "ComponentRequirements",
    "ComponentManifest",
]
