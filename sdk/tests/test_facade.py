"""M8 — the Server facade + the canonical hello-world example (SPEC §6; PLAN M8)."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from dcp import Server
from dcp import schema as s
from dcp.errors import RegistryError
from dcp.orchestration import HumanReply, ScriptedHumanGateway
from dcp.provider import MockProvider

_EXAMPLE = Path(__file__).resolve().parents[1] / "docs" / "examples" / "hello_dialogue_mock.py"


def _template() -> s.DialogueTemplate:
    return s.DialogueTemplate(
        template_id="review", version="1.0.0", title="Review",
        termination_policy=s.TerminationPolicy(condition="done", max_turns=6),
        roles=[
            s.Role(role_id="proposer", name="Proposer", kind=s.RoleKind.AGENT,
                   response_requirement=s.ResponseRequirement.REQUIRED),
            s.Role(role_id="founder", name="Founder", kind=s.RoleKind.HUMAN,
                   response_requirement=s.ResponseRequirement.GATE),
        ],
    )


def _seed(server: Server) -> None:
    server.register_template(_template())
    server.register_participant(
        s.Participant(participant_id="proposer", kind=s.RoleKind.AGENT, display_name="P"))
    server.register_participant(
        s.Participant(participant_id="founder", kind=s.RoleKind.HUMAN, display_name="F"))
    server.instantiate(
        s.TemplateRef(template_id="review", version="1.0.0"), owner="founder", instance_id="dlg")


def test_server_info_via_facade() -> None:
    info = Server(database_url="sqlite:///:memory:").server_info()
    assert info.dcp_version == "0.2.0"
    assert {p.provider for p in info.model_providers} == {"openai", "anthropic", "mock"}


async def test_facade_runs_mock_dialogue_to_done() -> None:
    server = Server(database_url="sqlite:///:memory:")
    _seed(server)
    result = await server.run(
        "dlg",
        cast={"proposer": "proposer", "founder": "founder"},
        orchestrator_provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "proposer"},
            {"action": "select_speaker", "target_role_id": "founder"},
            {"action": "stop", "status": "done"},
        ]),
        agent_providers={"proposer": MockProvider(texts=["I propose 'Northstar'."])},
        human_gateway=ScriptedHumanGateway(
            {"founder": HumanReply(content="Approved.", decision="approve")}),
    )
    assert result.status is s.InstanceStatus.DONE
    assert [m.role_id for m in result.messages] == ["proposer", "founder"]
    assert result.messages[-1].metadata["decision"] == "approve"


async def test_run_unregistered_participant_raises() -> None:
    server = Server(database_url="sqlite:///:memory:")
    server.register_template(_template())
    server.instantiate(
        s.TemplateRef(template_id="review", version="1.0.0"), owner="founder", instance_id="dlg")
    with pytest.raises(RegistryError):
        await server.run("dlg", cast={"proposer": "ghost", "founder": "founder"},
                         orchestrator_provider=MockProvider())


def test_hello_world_example_runs_end_to_end() -> None:
    # Guards the M8 DoD: the key-free example runs to a completed transcript with no credentials.
    runpy.run_path(str(_EXAMPLE), run_name="__main__")
