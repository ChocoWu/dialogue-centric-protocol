"""Phase 7C — owner-controlled context projection (D12)."""

from __future__ import annotations

from datetime import UTC, datetime

from dcp import schema as s
from dcp.component import ContextProjection, project_context
from dcp.orchestration import DialogueContext
from dcp.provider import MockProvider

_TS = datetime(2026, 7, 12, tzinfo=UTC)


def _ctx(*, transcript: bool = True) -> DialogueContext:
    template = s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done"),
        roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                      response_requirement=s.ResponseRequirement.REQUIRED)])
    msgs = [s.Message(message_id="m1", instance_id="dlg", turn_id=1, role_id="a",
                      participant_id="a", speaker_kind=s.RoleKind.AGENT, content="secret plan",
                      created_at=_TS)] if transcript else []
    inst = s.DialogueInstance(
        instance_id="dlg", template_ref=s.TemplateRef(template_id="t", version="1.0.0"),
        owner="@o", visibility=s.Visibility.PRIVATE, dcp_version="0.2.0",
        status=s.InstanceStatus.RUNNING, turn=len(msgs), roster=[], messages=msgs, events=[],
        open_gates=[], pending_inputs=[], budget=s.Budget(turns_used=len(msgs)))
    return DialogueContext.from_instance(inst, template, MockProvider())  # type: ignore[arg-type]


def test_default_projection_includes_full_transcript() -> None:
    payload, audit = project_context(_ctx())
    assert payload["transcript"] == [{"role_id": "a", "content": "secret plan"}]
    assert "transcript" in audit.fields
    assert audit.byte_size > 0 and len(audit.payload_digest) == 64      # recordable (D12)


def test_owner_can_omit_the_transcript() -> None:
    payload, _ = project_context(_ctx(), ContextProjection(transcript="omit"))
    assert "transcript" not in payload and "transcript_summary" not in payload


def test_summary_projection_does_not_send_full_content() -> None:
    payload, _ = project_context(_ctx(), ContextProjection(transcript="summary"))
    assert "transcript" not in payload
    assert "a:" in payload["transcript_summary"]


def test_audit_digest_changes_with_projection() -> None:
    _, full = project_context(_ctx())
    _, omitted = project_context(_ctx(), ContextProjection(transcript="omit"))
    assert full.payload_digest != omitted.payload_digest               # what was sent is pinned
