"""M6+ — discovery surface: server_info, list_instances filter, generate (SPEC §1.11/§2.2)."""

from __future__ import annotations

import pytest

from dcp import schema as s
from dcp.authoring import TemplateGenerator
from dcp.errors import RegistryError
from dcp.provider import MockProvider
from dcp.registry import Registry
from dcp.state import SqlStore


def _tmpl(vis: s.Visibility | None) -> s.DialogueTemplate:
    return s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done"), default_visibility=vis,
        roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                      response_requirement=s.ResponseRequirement.REQUIRED)],
    )


def _ref() -> s.TemplateRef:
    return s.TemplateRef(template_id="t", version="1.0.0")


def test_server_info_without_generator_disables_auto_generate() -> None:
    info = Registry(SqlStore()).server_info(env={})
    assert info.capabilities.auto_generate is False
    assert {p.provider for p in info.model_providers} == {"openai", "anthropic", "mock"}


def test_server_info_with_generator_advertises_auto_generate() -> None:
    reg = Registry(SqlStore(), generator=TemplateGenerator(MockProvider()))
    assert reg.server_info(env={}).capabilities.auto_generate is True


async def test_generate_template_capability_error_when_disabled() -> None:
    with pytest.raises(RegistryError):
        await Registry(SqlStore()).generate_template("anything")   # no generator wired (SPEC §2.2)


async def test_generate_template_returns_draft_when_enabled() -> None:
    draft = {
        "template_id": "g", "version": "1.0.0", "title": "G",
        "termination_policy": {"condition": "done"},
        "roles": [{"role_id": "a", "name": "A", "kind": "agent",
                   "response_requirement": "required"}],
    }
    reg = Registry(SqlStore(), generator=TemplateGenerator(MockProvider(structured_queue=[draft])))
    got = await reg.generate_template("make me a template")
    assert got.template_id == "g"


def test_list_instances_hides_private_from_non_owner() -> None:
    reg = Registry(SqlStore())
    reg.register_template(_tmpl(s.Visibility.PRIVATE))
    reg.register_template(s.DialogueTemplate(
        template_id="pub", version="1.0.0", title="Pub",
        termination_policy=s.TerminationPolicy(condition="done"),
        default_visibility=s.Visibility.PUBLIC,
        roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                      response_requirement=s.ResponseRequirement.REQUIRED)]))
    reg.instantiate(_ref(), owner="@owner", instance_id="priv")
    reg.instantiate(s.TemplateRef(template_id="pub", version="1.0.0"),
                    owner="@owner", instance_id="pub1")

    anon_ids = {i.instance_id for i in reg.list_instances()}
    assert anon_ids == {"pub1"}                              # private hidden
    owner_ids = {i.instance_id for i in reg.list_instances(caller="@owner")}
    assert owner_ids == {"pub1", "priv"}                     # owner sees its private one


def test_list_instances_shows_private_to_grantee() -> None:
    reg = Registry(SqlStore())
    reg.register_template(_tmpl(s.Visibility.PRIVATE))
    reg.instantiate(_ref(), owner="@owner", instance_id="priv")
    reg.grant_access("priv", grantor="@owner", participant_id="@guest", tier=s.AccessTier.OBSERVE)
    ids = {i.instance_id for i in reg.list_instances(caller="@guest")}
    assert ids == {"priv"}
