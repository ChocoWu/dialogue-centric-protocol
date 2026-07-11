"""Phase 6.2a — the built-in preset template library."""

from __future__ import annotations

import pytest

from dcp import presets
from dcp import schema as s
from dcp.errors import RegistryError
from dcp.registry import Registry
from dcp.state import SqlStore

_NAMES = presets.list_presets()


def test_lists_the_expected_presets() -> None:
    assert _NAMES == ["brainstorm", "debate", "design_review", "red_team_review",
                      "research_companion"]


@pytest.mark.parametrize("name", _NAMES)
def test_each_preset_is_a_valid_template(name: str) -> None:
    tmpl = presets.get_preset(name)
    assert isinstance(tmpl, s.DialogueTemplate)
    assert tmpl.roles, "a template needs at least one role"
    assert tmpl.termination_policy.condition
    # round-trips through the schema (validity)
    assert s.DialogueTemplate.model_validate_json(tmpl.model_dump_json()) == tmpl


@pytest.mark.parametrize("name", _NAMES)
def test_each_preset_registers_and_instantiates(name: str) -> None:
    reg = Registry(SqlStore())
    tmpl = presets.get_preset(name)
    reg.register_template(tmpl)
    inst = reg.instantiate(s.TemplateRef(template_id=tmpl.template_id, version=tmpl.version),
                           owner="@owner")
    assert inst.status is s.InstanceStatus.CREATED


def test_template_ids_are_unique() -> None:
    ids = [presets.get_preset(n).template_id for n in _NAMES]
    assert len(ids) == len(set(ids))


def test_human_roles_have_a_policy_default() -> None:
    # every preset that seats a human provides human_policy_defaults (so waits can't hang)
    for name in _NAMES:
        tmpl = presets.get_preset(name)
        if any(r.kind is s.RoleKind.HUMAN for r in tmpl.roles):
            assert tmpl.human_policy_defaults is not None, name


def test_factories_return_fresh_instances() -> None:
    a, b = presets.design_review(), presets.design_review()
    assert a == b and a is not b                 # equal content, distinct objects (mutation-safe)


def test_unknown_preset_raises() -> None:
    with pytest.raises(RegistryError):
        presets.get_preset("does-not-exist")


_FLOW_PRESETS = ["design_review", "debate", "red_team_review", "research_companion"]


@pytest.mark.parametrize("name", _FLOW_PRESETS)
def test_flow_presets_are_flow_mode_with_a_valid_graph(name: str) -> None:
    tmpl = presets.get_preset(name)
    assert tmpl.orchestration.mode is s.OrchestrationMode.FLOW   # flow ⇒ FLOW mode
    assert tmpl.flow is not None
    role_ids = {r.role_id for r in tmpl.roles}
    assert tmpl.flow.entry in role_ids
    for edge in tmpl.flow.edges:
        assert edge.from_role in role_ids and edge.to_role in role_ids


@pytest.mark.parametrize("name", _FLOW_PRESETS)
def test_flow_presets_are_non_linear(name: str) -> None:
    # at least one role has two or more outgoing edges (a branch/loop), i.e. not a straight line
    flow = presets.get_preset(name).flow
    assert flow is not None
    out_degree: dict[str, int] = {}
    for edge in flow.edges:
        out_degree[edge.from_role] = out_degree.get(edge.from_role, 0) + 1
    assert max(out_degree.values()) >= 2, f"{name} flow is linear"


def test_brainstorm_stays_emergent() -> None:
    tmpl = presets.get_preset("brainstorm")
    assert tmpl.flow is None
    assert tmpl.orchestration.mode is s.OrchestrationMode.PLAN
