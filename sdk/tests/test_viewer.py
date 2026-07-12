"""Phase 6.4 — the replay viewer (timeline of transcript + control + oversight)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dcp import render_timeline
from dcp import schema as s
from dcp.errors import RegistryError
from dcp.orchestration import Orchestrator, ScriptedOversight
from dcp.provider import MockProvider
from dcp.state import InstanceHeader, SqlStore

_TS = datetime(2026, 7, 11, tzinfo=UTC)


def _post(outcome: str, verdict: str = "pass") -> s.PostActionVerification:
    return s.PostActionVerification(
        verdict=verdict, relevance="ok", role_consistency="ok", completeness="ok",
        grounding="ok", safety="ok", human_input_addressed=True, outcome=outcome)


async def _run_revision_dialogue() -> SqlStore:
    store = SqlStore()
    store.create_instance(InstanceHeader(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@o", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0", created_at=_TS))
    tmpl = s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done", max_turns=6),
        roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                      response_requirement=s.ResponseRequirement.REQUIRED)])
    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg", cast={"a": "a"},
        participants={"a": s.Participant(participant_id="a", kind=s.RoleKind.AGENT,
                                         display_name="A")},
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"}]),
        agent_providers={"a": MockProvider(texts=["draft", "revised"])},
        oversight=ScriptedOversight(post=[_post("request_revision", "revise"), _post("continue")]))
    await orch.run()
    return store


async def test_timeline_interleaves_transcript_control_and_oversight() -> None:
    tl = render_timeline(await _run_revision_dialogue(), "dlg")

    assert "status=done" in tl and "template t@1.0.0" in tl
    # transcript, in order, with turn ids
    assert "> [t1] a: draft" in tl
    assert "> [t2] a: revised" in tl
    # control decisions
    assert "turn 1 -> a" in tl
    # oversight verdicts drove the revision
    assert "post: verdict=revise -> request_revision" in tl
    assert "revision requested: a" in tl
    assert "terminated: done" in tl
    # message and its following post appear in log order (message before the post that judged it)
    assert tl.index("> [t1] a: draft") < tl.index("post: verdict=revise")


async def test_timeline_skips_redundant_contribution_recorded() -> None:
    tl = render_timeline(await _run_revision_dialogue(), "dlg")
    assert "contribution" not in tl                     # noise suppressed; the message line stands


def test_timeline_unknown_instance_raises() -> None:
    with pytest.raises(RegistryError):
        render_timeline(SqlStore(), "nope")
