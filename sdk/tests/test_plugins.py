"""Phase 6.1d — plugin discovery via entry points (the sharing mechanism).

The entry-point ``source`` is injected so the round-trip (discover → load → real object) is proven
without installing a package into the venv. Targets point at real importable objects.
"""

from __future__ import annotations

from importlib.metadata import EntryPoint

import pytest

from dcp import schema as s
from dcp.errors import PluginError
from dcp.orchestration import DefaultOversight, FlowPolicy
from dcp.plugins import (
    GROUP_CONTROL_POLICIES,
    GROUP_OVERSIGHT_POLICIES,
    GROUP_TEMPLATES,
    available_plugins,
    list_plugins,
    load_control_policy,
    load_plugin,
    load_template,
)
from dcp.registry import Registry
from dcp.state import SqlStore


def _make_template() -> s.DialogueTemplate:  # a 0-arg template factory (entry-point target)
    return s.DialogueTemplate(
        template_id="ex", version="1.0.0", title="Example",
        termination_policy=s.TerminationPolicy(condition="done"),
        roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                      response_requirement=s.ResponseRequirement.REQUIRED)])


# `__name__` makes the target robust to pytest's import mode (module is already in sys.modules).
_SOURCE = [
    EntryPoint("flow", "dcp.orchestration.policy:FlowPolicy", GROUP_CONTROL_POLICIES),
    EntryPoint("passthrough", "dcp.orchestration.oversight:DefaultOversight",
               GROUP_OVERSIGHT_POLICIES),
    EntryPoint("example", f"{__name__}:_make_template", GROUP_TEMPLATES),
]


def test_list_plugins_is_metadata_only_and_sorted() -> None:
    infos = list_plugins(source=_SOURCE)
    assert [(p.group, p.name) for p in infos] == [
        (GROUP_CONTROL_POLICIES, "flow"),
        (GROUP_OVERSIGHT_POLICIES, "passthrough"),
        (GROUP_TEMPLATES, "example"),
    ]
    assert infos[0].value == "dcp.orchestration.policy:FlowPolicy"   # not imported, just the ref


def test_list_plugins_filters_by_group() -> None:
    infos = list_plugins(GROUP_CONTROL_POLICIES, source=_SOURCE)
    assert [p.name for p in infos] == ["flow"]


def test_available_plugins_maps_group_to_names() -> None:
    assert available_plugins(source=_SOURCE) == {
        GROUP_CONTROL_POLICIES: ["flow"],
        GROUP_OVERSIGHT_POLICIES: ["passthrough"],
        GROUP_TEMPLATES: ["example"],
    }


def test_load_resolves_the_real_object() -> None:
    assert load_plugin(GROUP_CONTROL_POLICIES, "flow", source=_SOURCE) is FlowPolicy
    assert load_control_policy("flow", source=_SOURCE) is FlowPolicy
    assert load_plugin(GROUP_OVERSIGHT_POLICIES, "passthrough", source=_SOURCE) is DefaultOversight


def test_load_unknown_name_raises() -> None:
    with pytest.raises(PluginError):
        load_plugin(GROUP_CONTROL_POLICIES, "nope", source=_SOURCE)


def test_load_bad_target_raises_plugin_error() -> None:
    bad = [EntryPoint("broken", "no.such.module:Thing", GROUP_CONTROL_POLICIES)]
    with pytest.raises(PluginError):
        load_plugin(GROUP_CONTROL_POLICIES, "broken", source=bad)


def test_load_template_resolves_a_factory() -> None:
    tmpl = load_template("example", source=_SOURCE)
    assert isinstance(tmpl, s.DialogueTemplate)
    assert tmpl.template_id == "ex"


def test_load_template_rejects_a_non_template() -> None:
    # points at a control policy class, not a template → validation error
    bad = [EntryPoint("wrong", "dcp.orchestration.policy:FlowPolicy", GROUP_TEMPLATES)]
    with pytest.raises(PluginError):
        load_template("wrong", source=bad)


def test_server_info_carries_a_plugins_field() -> None:
    info = Registry(SqlStore()).server_info(env={})
    assert isinstance(info.plugins, dict)                # empty when nothing is installed
