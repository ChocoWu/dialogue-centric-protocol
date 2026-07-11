"""Phase 6.2b — guard the Student Research Companion flagship end-to-end (key-free)."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import pytest

from dcp import schema as s

_EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples"


@pytest.fixture
def flagship(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    if not (_EXAMPLES / "research_companion_mock.py").is_file():
        pytest.skip("flagship example not found")
    monkeypatch.syspath_prepend(str(_EXAMPLES))
    import research_companion_mock  # noqa: PLC0415

    return research_companion_mock


async def test_flagship_runs_to_done_with_grounded_revision(flagship: ModuleType) -> None:
    result = await flagship.run_demo()

    assert result.status is s.InstanceStatus.DONE
    roles = [m.role_id for m in result.messages]
    # custom policy drove the workflow; the scout spoke twice (grounding forced a revision)
    assert roles == ["scout", "scout", "methodologist", "coach", "advisor"]
    assert "http" in result.messages[1].content              # the revision is grounded
    assert result.messages[-1].metadata.get("decision") == "approve"   # advisor gate


async def test_flagship_resumes_across_sessions(flagship: ModuleType) -> None:
    day1, day2 = await flagship.run_across_sessions()
    # day 1: paused before the advisor — non-terminal, suspended, resumable
    assert day1.status is s.InstanceStatus.RUNNING
    assert s.is_resumable(day1.status)
    assert s.EventType.INSTANCE_SUSPENDED in {e.type for e in day1.events}
    assert "advisor" not in {m.role_id for m in day1.messages}
    # day 2: a fresh run() resumed the SAME instance and finished (not restarted)
    assert day2.status is s.InstanceStatus.DONE
    assert [m.role_id for m in day2.messages][-1] == "advisor"
    assert len(day2.messages) == len(day1.messages) + 1


async def test_grounding_check_flags_uncited_scout(flagship: ModuleType) -> None:
    scout = s.Role(role_id="scout", name="Scout", kind=s.RoleKind.AGENT,
                   response_requirement=s.ResponseRequirement.REQUIRED)
    other = s.Role(role_id="coach", name="Coach", kind=s.RoleKind.AGENT,
                   response_requirement=s.ResponseRequirement.REQUIRED)

    def _msg(role: str, content: str) -> s.Message:
        from datetime import UTC, datetime
        return s.Message(message_id="m", instance_id="i", turn_id=1, role_id=role,
                         participant_id=role, speaker_kind=s.RoleKind.AGENT, content=content,
                         created_at=datetime(2026, 7, 11, tzinfo=UTC))

    weak = await flagship.grounding_check(
        role=scout, message=_msg("scout", "no source"), transcript="")
    ok = await flagship.grounding_check(
        role=scout, message=_msg("scout", "see http://x"), transcript="")
    other_ok = await flagship.grounding_check(
        role=other, message=_msg("coach", "no source needed"), transcript="")
    assert getattr(weak, "assessment", weak) is s.Assessment.WEAK
    assert ok is s.Assessment.OK and other_ok is s.Assessment.OK
