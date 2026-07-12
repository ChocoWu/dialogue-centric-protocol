"""Plugin discovery via Python entry points (Phase 6.1d) — the *sharing* mechanism.

Third-party packages contribute pluggable DCP components — control policies, oversight policies,
templates, and model providers (a packaged "agent") — by declaring **entry points**, and DCP
discovers what is installed. This is how "bring your own orchestrator / verification / template /
agent" becomes ``pip install ...`` + resolve-by-name, with no hosted code-upload service (the
standard, secure packaging path).

A contributing package declares, in its ``pyproject.toml``::

    [project.entry-points."dcp.control_policies"]
    round_robin = "my_pkg.policies:RoundRobinPolicy"

    [project.entry-points."dcp.oversight_policies"]
    grounding = "my_pkg.oversight:GroundingOversight"

    [project.entry-points."dcp.templates"]
    research_companion = "my_pkg.templates:research_companion"   # a DialogueTemplate or factory

    [project.entry-points."dcp.providers"]
    my_agent = "my_pkg.provider:MyProvider"      # a ModelProvider class/factory (resolved by name)

Then :func:`list_plugins` enumerates them (metadata only, no import), :func:`load_plugin` imports
one by name, and :func:`available_plugins` feeds ``server_info`` (SPEC §1.11) so a server can
advertise what it offers.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import Any

from .errors import PluginError
from .schema import DialogueTemplate

#: Entry-point group for pluggable control policies (the orchestrator "brain", 6.1b).
GROUP_CONTROL_POLICIES = "dcp.control_policies"
#: Entry-point group for pluggable oversight policies (pre/post verification, 6.1c).
GROUP_OVERSIGHT_POLICIES = "dcp.oversight_policies"
#: Entry-point group for shareable dialogue templates.
GROUP_TEMPLATES = "dcp.templates"
#: Entry-point group for shareable model providers (a packaged agent, resolved by name).
GROUP_PROVIDERS = "dcp.providers"
#: All DCP entry-point groups.
GROUPS = (GROUP_CONTROL_POLICIES, GROUP_OVERSIGHT_POLICIES, GROUP_TEMPLATES, GROUP_PROVIDERS)


@dataclass(frozen=True)
class PluginInfo:
    """A discovered plugin — metadata only; the target is **not** imported until loaded."""

    group: str
    name: str
    value: str        # "module:attr" reference


def _entry_points(group: str, source: Iterable[EntryPoint] | None) -> list[EntryPoint]:
    if source is not None:                              # injectable for tests / embedding
        return [ep for ep in source if ep.group == group]
    return list(entry_points(group=group))


def list_plugins(
    group: str | None = None, *, source: Iterable[EntryPoint] | None = None
) -> list[PluginInfo]:
    """Enumerate installed DCP plugins (all groups, or one), sorted; nothing is imported."""
    groups = [group] if group is not None else list(GROUPS)
    infos = [
        PluginInfo(group=g, name=ep.name, value=ep.value)
        for g in groups
        for ep in _entry_points(g, source)
    ]
    return sorted(infos, key=lambda p: (p.group, p.name))


def available_plugins(*, source: Iterable[EntryPoint] | None = None) -> dict[str, list[str]]:
    """Map each non-empty group to its installed plugin names (for ``server_info``, SPEC §1.11)."""
    result: dict[str, list[str]] = {}
    for g in GROUPS:
        names = sorted(ep.name for ep in _entry_points(g, source))
        if names:
            result[g] = names
    return result


def load_plugin(group: str, name: str, *, source: Iterable[EntryPoint] | None = None) -> Any:
    """Import and return the object a plugin points to (a class, factory, or value)."""
    for ep in _entry_points(group, source):
        if ep.name == name:
            try:
                return ep.load()
            except Exception as exc:                    # import/attr errors → typed PluginError
                raise PluginError(f"failed to load plugin {name!r} ({ep.value!r}): {exc}") from exc
    raise PluginError(f"no plugin named {name!r} in group {group!r}")


def load_control_policy(name: str, *, source: Iterable[EntryPoint] | None = None) -> Any:
    """Load a control-policy plugin (a ``ControlPolicy`` class/instance/factory)."""
    return load_plugin(GROUP_CONTROL_POLICIES, name, source=source)


def load_oversight_policy(name: str, *, source: Iterable[EntryPoint] | None = None) -> Any:
    """Load an oversight-policy plugin (an ``OversightPolicy`` class/instance/factory)."""
    return load_plugin(GROUP_OVERSIGHT_POLICIES, name, source=source)


def load_model_provider(name: str, *, source: Iterable[EntryPoint] | None = None) -> Any:
    """Load a model-provider plugin (a ``ModelProvider`` class, factory, or instance)."""
    return load_plugin(GROUP_PROVIDERS, name, source=source)


def load_template(
    name: str, *, source: Iterable[EntryPoint] | None = None
) -> DialogueTemplate:
    """Load a template plugin, resolving a ``DialogueTemplate`` instance or a 0-arg factory."""
    obj = load_plugin(GROUP_TEMPLATES, name, source=source)
    if isinstance(obj, DialogueTemplate):
        return obj
    if callable(obj):
        produced = obj()
        if isinstance(produced, DialogueTemplate):
            return produced
    raise PluginError(f"template plugin {name!r} did not resolve to a DialogueTemplate")


__all__ = [
    "GROUP_CONTROL_POLICIES",
    "GROUP_OVERSIGHT_POLICIES",
    "GROUP_TEMPLATES",
    "GROUP_PROVIDERS",
    "GROUPS",
    "PluginInfo",
    "list_plugins",
    "available_plugins",
    "load_plugin",
    "load_control_policy",
    "load_oversight_policy",
    "load_model_provider",
    "load_template",
]
