"""Local delivery (Phase 7A) — the instantiate stage that turns a plan into a live object.

Separated from resolution by design (D11): :func:`materialize` performs the side effects resolution
refused — it imports the implementation entrypoint and constructs the runtime object. Provisioning
(``pip install`` a not-yet-present package, downloading artifacts) is a *prior* stage that 7B adds;
in 7A the local implementation is expected to already be importable (e.g. an installed package or
the entry-point plugin path), and :func:`materialize` fails clearly if it is not.

Remote materialization is the ``RemoteComponentClient`` (7C); artifact-backed local models are 7B.
"""

from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from ..errors import ComponentError, ResolutionError
from .agent import build_agent_definition
from .artifacts import ArtifactProvisioner, ProvisionedArtifact
from .manifest import ComponentKind, PackageSource, RemoteAccessMode
from .resolver import ComponentResolutionPlan

#: The runtime methods each executable kind's materialized object must expose (duck-typed).
_REQUIRED_METHODS: dict[ComponentKind, tuple[str, ...]] = {
    ComponentKind.CONTROL_POLICY: ("decide",),
    ComponentKind.OVERSIGHT_POLICY: ("pre", "post"),
    ComponentKind.MODEL_PROVIDER: ("text", "structured"),
}


@dataclass(frozen=True)
class ProvisionReport:
    """Outcome of the provision stage — the package action plus any provisioned artifacts."""

    action: str            # "already-present" | "installed"
    package: str
    spec: str | None = None
    artifacts: tuple[ProvisionedArtifact, ...] = field(default_factory=tuple)


def _module_present(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError:
        return False


def _pip_install(spec: str) -> None:
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", spec], check=True)
    except subprocess.CalledProcessError as exc:      # a failed install → a clean ComponentError
        raise ComponentError(f"pip install {spec!r} failed (exit {exc.returncode})") from exc


def provision(
    plan: ComponentResolutionPlan,
    *,
    runner: Callable[[str], None] | None = None,
    present: Callable[[str], bool] | None = None,
    artifact_provisioner: ArtifactProvisioner | None = None,
) -> ProvisionReport:
    """Install the local implementation and provision its artifacts (the D11 provision stage).

    Idempotent: the package is installed only if its entrypoint module is absent, and artifacts are
    content-addressed so a cached checkpoint is reused. ``runner`` / ``present`` /
    ``artifact_provisioner`` are injectable so tests avoid real pip and network. Non-PyPI sources
    arrive in a later milestone; remote modes are connected, not provisioned.
    """
    mode = plan.selected_mode
    if isinstance(mode, RemoteAccessMode):
        raise ComponentError("remote components are connected, not provisioned (7C)")

    impl = mode.implementation
    module_name = impl.entrypoint.partition(":")[0]
    if (present or _module_present)(module_name):
        action, spec = "already-present", None
    else:
        if impl.source is not PackageSource.PYPI:
            raise ComponentError(f"provisioning source {impl.source.value!r} arrives in a later "
                                 "milestone (7A/7B cover PyPI + already-installed)")
        spec = f"{impl.package}=={impl.version}" if impl.version else impl.package
        (runner or _pip_install)(spec)
        action = "installed"

    artifacts: tuple[ProvisionedArtifact, ...] = ()
    if mode.artifacts:
        prov = artifact_provisioner or ArtifactProvisioner()
        artifacts = tuple(prov.provision(a) for a in mode.artifacts)
    return ProvisionReport(action=action, package=impl.package, spec=spec, artifacts=artifacts)


def _import_entrypoint(entrypoint: str) -> object:
    """Import a ``module:attr`` target. Import failure ⇒ not provisioned (ResolutionError)."""
    module_name, _, attr = entrypoint.partition(":")
    if not module_name or not attr:
        raise ComponentError(f"invalid entrypoint {entrypoint!r} (expected 'module:attr')")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ResolutionError(
            f"entrypoint {entrypoint!r} is not importable — provision the component first "
            f"({exc})") from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ComponentError(f"entrypoint {entrypoint!r}: {attr!r} not found in {module_name!r}") \
            from exc


def _check_interface(kind: ComponentKind, obj: object) -> None:
    missing = [m for m in _REQUIRED_METHODS.get(kind, ()) if not callable(getattr(obj, m, None))]
    if missing:
        raise ComponentError(
            f"materialized {kind.value!r} is missing interface method(s) {missing}")


def materialize(
    plan: ComponentResolutionPlan,
    *,
    artifacts: Sequence[ProvisionedArtifact] = (),
) -> object:
    """Instantiate the local component described by ``plan`` (the D11 instantiate stage).

    Returns the runtime object for executable kinds (a ``ControlPolicy`` / ``OversightPolicy`` /
    ``ModelProvider``), the ``DialogueTemplate`` for ``template``, or an ``AgentDefinition`` for
    ``agent`` (whose entrypoint is its ``ModelProvider``; D2). For an artifact-backed one (e.g. an
    open-weights model) pass the ``artifacts`` from :func:`provision`; the entrypoint is then called
    as a factory with the primary checkpoint path. Remote modes raise — use :func:`connect`.
    """
    mode = plan.selected_mode
    if isinstance(mode, RemoteAccessMode):
        raise ComponentError("remote components materialize via RemoteComponentClient (7C)")

    kind = plan.manifest.component.kind
    target = _import_entrypoint(mode.implementation.entrypoint)

    if kind is ComponentKind.TEMPLATE:
        return _materialize_template(target)

    if artifacts:
        if not callable(target):
            raise ComponentError(f"artifact-backed entrypoint {mode.implementation.entrypoint!r} "
                                 "must be a factory(checkpoint_path)")
        instance = target(str(artifacts[0].path))    # factory(checkpoint_path) → runtime object
    else:
        instance = target() if isinstance(target, type) else target   # class → construct; else use

    if kind is ComponentKind.AGENT:                  # an agent's entrypoint is its ModelProvider
        _check_interface(ComponentKind.MODEL_PROVIDER, instance)
        return build_agent_definition(plan.manifest, instance)   # → AgentDefinition (D2)
    _check_interface(kind, instance)
    return instance


def _materialize_template(target: object) -> object:
    from ..schema import DialogueTemplate

    produced = target() if callable(target) and not isinstance(target, DialogueTemplate) else target
    if not isinstance(produced, DialogueTemplate):
        raise ComponentError("template entrypoint did not resolve to a DialogueTemplate")
    return produced


__all__ = ["materialize", "provision", "ProvisionReport"]
