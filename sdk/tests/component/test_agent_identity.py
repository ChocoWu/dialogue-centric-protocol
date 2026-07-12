"""Phase 7 — the D2 identity path: agent component → AgentDefinition → Participant → dialogue.

An ``agent`` component materializes into an ``AgentDefinition`` (D2/D10); ``to_participant`` does
the identity step; ``role_defaults`` fill an empty persona but never override one (D8). It also
acts as a ModelProvider, so a materialized agent contributes real turns.
"""

from __future__ import annotations

from importlib.metadata import EntryPoint
from typing import Any

from dcp import schema as s
from dcp.component import (
    AgentDefinition,
    ComponentManifest,
    InstalledResolver,
    materialize,
    resolve,
)
from dcp.plugins import GROUP_COMPONENTS


class _ScoutProvider:
    """An agent's ModelProvider (its 'brain') — the entrypoint of a local agent component."""

    model = "scout"

    async def text(self, *, instructions: str, content: str) -> str:
        return "found: 3 relevant papers"

    async def structured(self, *, instructions: str, content: str, schema: type) -> Any:
        raise NotImplementedError


def _agent_manifest(*, persona: str = "Search the literature.") -> ComponentManifest:
    return ComponentManifest.model_validate({
        "schema_version": "1.0",
        "component": {"namespace": "alice", "name": "scout", "version": "2.1.0", "kind": "agent"},
        "metadata": {"description": "A literature scout."},
        "interface": {"name": "dcp.agent_definition", "version": "1.0"},
        "capabilities": ["dcp.agent.search"],
        "spec": {"role_defaults": {"persona": persona}},
        "access_modes": [{
            "type": "local",
            "implementation": {"type": "python_package", "source": "pypi", "package": "alice-scout",
                               "entrypoint": f"{__name__}:_ScoutProvider"},
        }],
    })


def _plan(m: ComponentManifest) -> Any:
    class _Fixed(InstalledResolver):
        def locate(self, ref: Any) -> ComponentManifest:
            return m

    return resolve("installed://alice/scout",
                   resolvers=[_Fixed(source=[EntryPoint("alice/scout", "x", GROUP_COMPONENTS)])])


def test_agent_materializes_to_a_definition() -> None:
    defn = materialize(_plan(_agent_manifest()))
    assert isinstance(defn, AgentDefinition)
    assert defn.name == "alice/scout" and defn.version == "2.1.0"
    assert defn.capabilities == ("dcp.agent.search",)
    assert defn.profile == "A literature scout."


def test_to_participant_assigns_identity() -> None:
    defn = materialize(_plan(_agent_manifest()))
    assert isinstance(defn, AgentDefinition)
    p = defn.to_participant("@scout", discoverable=True)
    assert isinstance(p, s.Participant)
    assert p.participant_id == "@scout" and p.kind is s.RoleKind.AGENT
    assert p.display_name == "scout" and p.discoverable is True
    assert p.metadata["component"] == "alice/scout"
    assert p.metadata["capabilities"] == ["dcp.agent.search"]


def test_role_defaults_fill_empty_persona_but_never_override() -> None:
    defn = materialize(_plan(_agent_manifest(persona="Search the literature.")))
    assert isinstance(defn, AgentDefinition)

    empty = s.Role(role_id="scout", name="Scout", kind=s.RoleKind.AGENT,
                   response_requirement=s.ResponseRequirement.REQUIRED)          # persona == ""
    filled = defn.apply_role_defaults(empty)
    assert filled.persona == "Search the literature."                            # D8: filled

    owned = empty.model_copy(update={"persona": "the template's own persona"})
    assert defn.apply_role_defaults(owned).persona == "the template's own persona"  # D8: kept


async def test_materialized_agent_contributes_in_a_dialogue() -> None:
    from datetime import UTC, datetime

    from dcp.orchestration import Orchestrator
    from dcp.provider import MockProvider
    from dcp.state import InstanceHeader, SqlStore

    defn = materialize(_plan(_agent_manifest()))
    assert isinstance(defn, AgentDefinition)
    participant = defn.to_participant("@scout")                # the identity step (D2)
    pid = participant.participant_id

    role = s.Role(role_id="scout", name="Scout", kind=s.RoleKind.AGENT,
                  response_requirement=s.ResponseRequirement.REQUIRED)
    template = s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done", max_turns=2),
        roles=[defn.apply_role_defaults(role)])               # role_defaults materialized (D8)
    store = SqlStore()
    store.create_instance(InstanceHeader(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@o", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0",
        created_at=datetime(2026, 7, 12, tzinfo=UTC)))
    orch = Orchestrator(
        store=store, template=template, instance_id="dlg", cast={"scout": pid},
        participants={pid: participant},
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "scout"},
            {"action": "stop", "status": "done"}]),
        agent_providers={pid: defn})                          # the definition acts as the provider
    inst = await orch.run()
    assert [m.content for m in inst.messages] == ["found: 3 relevant papers"]
