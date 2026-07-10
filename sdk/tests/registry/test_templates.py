"""M6 — TemplateCatalog: registration + immutability per (id, version) (SPEC §2.1, §6)."""

from __future__ import annotations

import pytest

from dcp import schema as s
from dcp.errors import RegistryError
from dcp.registry import Registry
from dcp.state import SqlStore


def _tmpl(*, version: str = "1.0.0", title: str = "Design Review") -> s.DialogueTemplate:
    return s.DialogueTemplate(
        template_id="design-review", version=version, title=title,
        termination_policy=s.TerminationPolicy(condition="done"),
        roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                      response_requirement=s.ResponseRequirement.REQUIRED)],
    )


def test_register_and_get_template() -> None:
    reg = Registry(SqlStore())
    reg.register_template(_tmpl())
    got = reg.get_template("design-review", "1.0.0")
    assert got is not None and got.title == "Design Review"


def test_reregister_same_version_different_content_fails() -> None:
    reg = Registry(SqlStore())
    reg.register_template(_tmpl(title="Design Review"))
    with pytest.raises(RegistryError):
        reg.register_template(_tmpl(title="Changed Title"))       # same (id,version), new content


def test_reregister_identical_is_idempotent() -> None:
    reg = Registry(SqlStore())
    reg.register_template(_tmpl())
    reg.register_template(_tmpl())                                # identical -> no error
    assert reg.get_template("design-review", "1.0.0") is not None


def test_new_version_succeeds() -> None:
    reg = Registry(SqlStore())
    reg.register_template(_tmpl(version="1.0.0", title="v1"))
    reg.register_template(_tmpl(version="2.0.0", title="v2"))     # new version MUST succeed
    assert reg.get_template("design-review", "2.0.0").title == "v2"  # type: ignore[union-attr]
    assert {t.version for t in reg.list_templates()} == {"1.0.0", "2.0.0"}
