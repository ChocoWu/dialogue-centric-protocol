"""Component resolution (Phase 7A) — turn a reference into an inspectable, side-effect-free plan.

Resolution **locates, parses, validates, selects a mode, and plans** — it performs no installs,
downloads, imports of implementation code, or endpoint connections (D11). Those happen later, in
provisioning / materialization (:mod:`dcp.component.delivery`). The output is a
:class:`ComponentResolutionPlan` — exactly what ``dcp inspect`` prints and what a future lockfile
serializes (D17).

Two backends ship today (D16): :class:`ManifestUrlResolver` (a manifest at a ``file://`` path/URL)
and :class:`InstalledResolver` (a component installed via a ``dcp.components`` entry point). Git /
PyPI / HuggingFace *reference* resolvers are still deferred (artifact provisioning — a separate
role, :mod:`dcp.component.artifacts` — is implemented).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Protocol

from pydantic import Field

from ..errors import ResolutionError
from ..plugins import GROUP_COMPONENTS, load_plugin
from ..schema.base import DCPModel
from .manifest import (
    AccessMode,
    AccessModeType,
    ComponentManifest,
    DependencyRef,
    LocalAccessMode,
    RemoteAccessMode,
)

# --- reference parsing -----------------------------------------------------------------

@dataclass(frozen=True)
class ComponentReference:
    """A parsed component reference. ``fragment`` carries a manifest path or digest (D15)."""

    raw: str
    scheme: str            # file | https | installed | git | pypi | hf
    location: str          # scheme-specific remainder
    fragment: str | None = None


_UNSUPPORTED_V1 = {"git", "pypi", "hf"}   # recognized syntaxes whose resolvers arrive in 7B
_MAX_DEPTH = 32                            # dependency-recursion backstop (cycles caught above)


def parse_reference(ref: str) -> ComponentReference:
    """Parse a direct reference string into a :class:`ComponentReference` (D15)."""
    if not ref:
        raise ResolutionError("empty component reference")
    body, _, frag = ref.partition("#")
    fragment = frag or None
    if body.startswith("installed://"):
        return ComponentReference(ref, "installed", body[len("installed://"):], fragment)
    if body.startswith("file://"):
        return ComponentReference(ref, "file", body[len("file://"):], fragment)
    if body.startswith(("http://", "https://")):
        return ComponentReference(ref, "https", body, fragment)
    if body.startswith("git+"):
        return ComponentReference(ref, "git", body, fragment)
    if "://" in body and body.split("://", 1)[0] in _UNSUPPORTED_V1:
        return ComponentReference(ref, body.split("://", 1)[0], body, fragment)
    return ComponentReference(ref, "file", body, fragment)   # bare path


# --- the plan (side-effect-free output) ------------------------------------------------

class ComponentResolutionPlan(DCPModel):
    """The inspectable result of resolution — no side effects have occurred (D11)."""

    reference: str
    manifest: ComponentManifest
    selected_mode: AccessMode
    dependencies: list[ComponentResolutionPlan] = Field(default_factory=list)
    expected_side_effects: list[str] = Field(default_factory=list)
    credential_slots: list[str] = Field(default_factory=list)
    license_prompts: list[str] = Field(default_factory=list)
    compatibility: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# --- resolver backends -----------------------------------------------------------------

class ComponentReferenceResolver(Protocol):
    """Locates a manifest for references it handles. **Side-effect-free** (D11)."""

    def handles(self, ref: ComponentReference) -> bool: ...
    def locate(self, ref: ComponentReference) -> ComponentManifest: ...


def _parse_manifest_text(text: str, *, hint: str = "") -> object:
    h = hint.lower()
    if h.endswith((".yaml", ".yml")):
        return _yaml_load(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _yaml_load(text)


def _yaml_load(text: str) -> object:
    try:
        import yaml
    except ImportError as exc:                              # optional extra
        raise ResolutionError(
            "YAML manifests need the optional dependency: pip install 'dcp[yaml]'") from exc
    return yaml.safe_load(text)


class ManifestUrlResolver:
    """Reads a manifest from a ``file://`` path (or an injected reader for URLs/tests)."""

    def __init__(self, *, reader: Callable[[str], str] | None = None) -> None:
        self._reader = reader

    def handles(self, ref: ComponentReference) -> bool:
        return ref.scheme in ("file", "https")

    def locate(self, ref: ComponentReference) -> ComponentManifest:
        if self._reader is not None:
            text = self._reader(ref.location)
        elif ref.scheme == "file":
            text = Path(ref.location).read_text(encoding="utf-8")
        else:
            raise ResolutionError(
                f"reading {ref.scheme!r} references needs a reader (7A resolves file:// natively)")
        return ComponentManifest.model_validate(_parse_manifest_text(text, hint=ref.location))


class InstalledResolver:
    """Resolves a component already installed via a ``dcp.components`` entry point (D1)."""

    def __init__(self, *, source: Iterable[EntryPoint] | None = None) -> None:
        self._source = source

    def handles(self, ref: ComponentReference) -> bool:
        return ref.scheme == "installed"

    def locate(self, ref: ComponentReference) -> ComponentManifest:
        obj = load_plugin(GROUP_COMPONENTS, ref.location, source=self._source)
        manifest = obj() if callable(obj) and not isinstance(obj, ComponentManifest) else obj
        if not isinstance(manifest, ComponentManifest):
            raise ResolutionError(
                f"installed component {ref.location!r} did not resolve to a ComponentManifest")
        return manifest


def default_resolvers() -> tuple[ComponentReferenceResolver, ...]:
    """The 7A resolver set: local manifest files + installed components."""
    return (ManifestUrlResolver(), InstalledResolver())


# --- planning (orchestrates the backends; recursive over the dependency DAG) ------------

def resolve(
    ref: str | ComponentReference,
    *,
    resolvers: Sequence[ComponentReferenceResolver] | None = None,
    mode: AccessModeType | str | None = None,
    mode_preference: Sequence[AccessModeType | str] | None = None,
    _seen: tuple[str, ...] = (),
) -> ComponentResolutionPlan:
    """Resolve ``ref`` into a side-effect-free :class:`ComponentResolutionPlan` (D11).

    Recurses over declared dependencies (a DAG; cycles are rejected — D17) and verifies each
    dependency against its ``expected_kind`` / ``interface_constraint`` (D23).
    """
    backends = tuple(resolvers) if resolvers is not None else default_resolvers()
    parsed = ref if isinstance(ref, ComponentReference) else parse_reference(ref)
    if parsed.raw in _seen:
        raise ResolutionError(f"dependency cycle detected at {parsed.raw!r}")
    if len(_seen) >= _MAX_DEPTH:                             # backstop for non-identical-ref cycles
        raise ResolutionError(f"dependency graph exceeds max depth {_MAX_DEPTH}")

    backend = next((b for b in backends if b.handles(parsed)), None)
    if backend is None:
        raise ResolutionError(
            f"no resolver handles {parsed.raw!r} (scheme {parsed.scheme!r}); "
            "git/pypi/hf resolvers arrive in 7B")

    manifest = backend.locate(parsed)                       # side-effect-free
    selected = _select_mode(manifest, mode, mode_preference)

    seen = (*_seen, parsed.raw)
    deps: list[ComponentResolutionPlan] = []
    for dep in manifest.dependencies:
        dep_plan = resolve(dep.ref, resolvers=backends, mode=dep.mode_constraint, _seen=seen)
        _check_dependency(dep, dep_plan.manifest)
        deps.append(dep_plan)

    return ComponentResolutionPlan(
        reference=parsed.raw,
        manifest=manifest,
        selected_mode=selected,
        dependencies=deps,
        expected_side_effects=_side_effects(selected),
        credential_slots=_credential_slots(selected),
        license_prompts=_license_prompts(manifest, selected),
        compatibility=_compatibility(manifest),
        warnings=_warnings(selected),
    )


def _select_mode(
    manifest: ComponentManifest,
    mode: AccessModeType | str | None,
    preference: Sequence[AccessModeType | str] | None,
) -> AccessMode:
    modes = manifest.access_modes
    if mode is not None:
        want = AccessModeType(mode)
        for m in modes:
            if m.type == want:
                return m
        raise ResolutionError(f"component has no access mode of type {want.value!r}")
    for want_raw in preference or ():
        want = AccessModeType(want_raw)
        for m in modes:
            if m.type == want:
                return m
    return modes[0]


def _check_dependency(dep: DependencyRef, resolved: ComponentManifest) -> None:
    if resolved.component.kind is not dep.expected_kind:
        raise ResolutionError(
            f"dependency {dep.ref!r} resolved to kind {resolved.component.kind.value!r}, "
            f"expected {dep.expected_kind.value!r}")
    want = dep.interface_constraint
    if want is not None and resolved.interface.name is not want.name:
        raise ResolutionError(
            f"dependency {dep.ref!r} interface {resolved.interface.name.value!r} != "
            f"required {want.name.value!r}")


def _side_effects(mode: AccessMode) -> list[str]:
    if isinstance(mode, RemoteAccessMode):
        return [f"connect: {mode.endpoint}"]
    impl = mode.implementation
    pin = f"=={impl.version}" if impl.version else ""
    effects = [f"provision: install {impl.source.value}:{impl.package}{pin}"]
    for art in mode.artifacts:
        size = f" (~{art.size_bytes} bytes)" if art.size_bytes is not None else ""
        effects.append(f"download artifact {art.uri}{size}")
    effects.append(f"instantiate: import {impl.entrypoint}")
    return effects


def _credential_slots(mode: AccessMode) -> list[str]:
    if isinstance(mode, RemoteAccessMode) and mode.auth is not None:
        return [mode.auth.credential_slot]
    return []


def _license_prompts(manifest: ComponentManifest, mode: AccessMode) -> list[str]:
    out: list[str] = []
    if manifest.metadata.license:
        out.append(f"component license: {manifest.metadata.license}")
    if isinstance(mode, LocalAccessMode):
        out += [f"artifact license: {a.license}" for a in mode.artifacts if a.license]
    return out


def _compatibility(manifest: ComponentManifest) -> list[str]:
    req = manifest.requirements
    if req is None:
        return []
    notes = []
    if req.dcp:
        notes.append(f"requires dcp {req.dcp}")
    if req.python:
        notes.append(f"requires python {req.python}")
    return notes


def _warnings(mode: AccessMode) -> list[str]:
    if isinstance(mode, RemoteAccessMode):
        return ["remote mode transmits dialogue context beyond the owner boundary "
                "(the owner controls the projection — D12)"]
    return []


ComponentResolutionPlan.model_rebuild()


def render_plan(plan: ComponentResolutionPlan, *, indent: str = "") -> str:
    """A human-readable rendering of a plan — what ``dcp inspect`` prints. No side effects."""
    c = plan.manifest.component
    lines = [
        f"{indent}component: {c.namespace}/{c.name} @ {c.version}  ({c.kind.value})",
        f"{indent}interface: {plan.manifest.interface.name.value} "
        f"{plan.manifest.interface.version}",
        f"{indent}mode:      {plan.selected_mode.type.value}",
    ]

    def _section(title: str, rows: list[str]) -> None:
        lines.append(f"{indent}{title}:")
        if rows:
            lines.extend(f"{indent}  - {r}" for r in rows)
        else:
            lines.append(f"{indent}  (none)")

    _section("side effects", plan.expected_side_effects)
    _section("credentials", plan.credential_slots)
    _section("licenses", plan.license_prompts)
    _section("compatibility", plan.compatibility)
    _section("warnings", plan.warnings)
    if plan.dependencies:
        lines.append(f"{indent}dependencies:")
        for dep in plan.dependencies:
            lines.append(render_plan(dep, indent=indent + "  "))
    return "\n".join(lines)


__all__ = [
    "ComponentReference",
    "parse_reference",
    "ComponentResolutionPlan",
    "ComponentReferenceResolver",
    "ManifestUrlResolver",
    "InstalledResolver",
    "default_resolvers",
    "resolve",
    "render_plan",
]
