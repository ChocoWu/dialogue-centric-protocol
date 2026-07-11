"""Phase 6.1c — RubricOversight: compose per-dimension checks into post verification (SPEC §1.7)."""

from __future__ import annotations

from datetime import UTC, datetime

from dcp import schema as s
from dcp.orchestration import (
    Check,
    CheckOutcome,
    Orchestrator,
    RubricOversight,
)
from dcp.provider import MockProvider
from dcp.state import InstanceHeader, SqlStore

_TS = datetime(2026, 7, 11, tzinfo=UTC)
_A = s.Assessment
_ROLE = s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
               response_requirement=s.ResponseRequirement.REQUIRED)


def _msg(content: str) -> s.Message:
    return s.Message(message_id="m", instance_id="dlg", turn_id=1, role_id="a", participant_id="a",
                     speaker_kind=s.RoleKind.AGENT, content=content, created_at=_TS)


async def _post(rubric: RubricOversight, content: str = "x") -> s.PostActionVerification:
    return await rubric.post(role=_ROLE, message=_msg(content), transcript=content)


# --- unit: assessment → verdict/outcome mapping ------------------------------------------

async def test_all_ok_defaults_to_pass_continue() -> None:
    post = await _post(RubricOversight())              # no checks -> every dimension ok
    assert post.verdict is s.Verdict.PASS
    assert post.outcome is s.PostOutcome.CONTINUE
    assert post.grounding is _A.OK


async def test_weak_dimension_requests_revision_and_records_issue() -> None:
    async def grounding(*, role: s.Role, message: s.Message, transcript: str) -> CheckOutcome:
        return CheckOutcome(_A.WEAK, "no citation")
    post = await _post(RubricOversight(grounding=grounding))
    assert post.verdict is s.Verdict.REVISE
    assert post.outcome is s.PostOutcome.REQUEST_REVISION
    assert post.grounding is _A.WEAK
    assert any(i.type == "grounding" and i.description == "no citation" for i in post.issues)


async def test_safety_failure_escalates_to_a_gate() -> None:
    async def safety(*, role: s.Role, message: s.Message, transcript: str) -> s.Assessment:
        return _A.FAIL
    post = await _post(RubricOversight(safety=safety))
    assert post.verdict is s.Verdict.ESCALATE
    assert post.outcome is s.PostOutcome.ESCALATE_GATE
    assert post.escalated is True


async def test_bare_assessment_return_is_accepted() -> None:
    async def relevance(*, role: s.Role, message: s.Message, transcript: str) -> s.Assessment:
        return _A.OK
    check: Check = relevance
    post = await _post(RubricOversight(relevance=check))
    assert post.outcome is s.PostOutcome.CONTINUE


async def test_custom_verdict_fn_overrides_mapping() -> None:
    async def completeness(*, role: s.Role, message: s.Message, transcript: str) -> s.Assessment:
        return _A.WEAK
    # a stricter rubric: any non-ok -> stop
    def strict(assessments: dict[str, s.Assessment]) -> tuple[s.Verdict, s.PostOutcome]:
        if any(a is not _A.OK for a in assessments.values()):
            return s.Verdict.REJECT, s.PostOutcome.STOP
        return s.Verdict.PASS, s.PostOutcome.CONTINUE
    post = await _post(RubricOversight(completeness=completeness, verdict_fn=strict))
    assert post.verdict is s.Verdict.REJECT and post.outcome is s.PostOutcome.STOP


# --- end-to-end: a weak grounding check drives a revision through the real loop -----------

async def test_rubric_drives_revision_in_the_loop() -> None:
    store = SqlStore()
    store.create_instance(InstanceHeader(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@o", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0", created_at=_TS))
    tmpl = s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done", max_turns=6), roles=[_ROLE])

    async def grounding(*, role: s.Role, message: s.Message, transcript: str) -> CheckOutcome:
        # first draft is ungrounded; the revision is fine
        if message.content == "revised":
            return CheckOutcome(_A.OK)
        return CheckOutcome(_A.WEAK, "cite")

    orch = Orchestrator(
        store=store, template=tmpl, instance_id="dlg", cast={"a": "a"},
        participants={"a": s.Participant(participant_id="a", kind=s.RoleKind.AGENT,
                                         display_name="A")},
        provider=MockProvider(structured_queue=[
            {"action": "select_speaker", "target_role_id": "a"},
            {"action": "stop", "status": "done"}]),
        agent_providers={"a": MockProvider(texts=["draft", "revised"])},
        oversight=RubricOversight(grounding=grounding),
    )
    inst = await orch.run()
    assert inst.status is s.InstanceStatus.DONE
    assert [m.content for m in inst.messages] == ["draft", "revised"]     # rubric forced a revision
    assert s.EventType.REVISION_REQUESTED in {e.type for e in inst.events}
