"""M1 — enum value spaces (SPEC §1; TBD-3/4/5/9/12/14 confirmed)."""

from __future__ import annotations

from dcp import schema as s


def test_instance_status_space() -> None:
    assert {v.value for v in s.InstanceStatus} == {
        "created", "running", "awaiting",
        "done", "provisional", "stopped", "budget", "error",
    }


def test_terminal_statuses_are_the_five() -> None:
    assert {v.value for v in s.TERMINAL_STATUSES} == {
        "done", "provisional", "stopped", "budget", "error",
    }
    assert s.InstanceStatus.RUNNING not in s.TERMINAL_STATUSES
    assert s.InstanceStatus.CREATED not in s.TERMINAL_STATUSES


def test_response_requirement_space() -> None:
    assert {v.value for v in s.ResponseRequirement} == {"required", "optional", "gate"}


def test_role_kind_space() -> None:
    assert {v.value for v in s.RoleKind} == {"agent", "human"}


def test_access_tier_and_visibility() -> None:
    assert {v.value for v in s.AccessTier} == {"own", "speak", "observe"}
    assert {v.value for v in s.Visibility} == {"public", "unlisted", "private"}


def test_orchestration_mode_and_on_timeout() -> None:
    assert {v.value for v in s.OrchestrationMode} == {"plan", "flow"}
    assert {v.value for v in s.OnTimeout} == {"continue", "finalize_provisional"}


def test_event_taxonomy_groups_present() -> None:
    vals = {v.value for v in s.EventType}
    # one representative from each SPEC §1.9 group
    for expected in (
        "template_registered",       # registry
        "instance_created",          # lifecycle
        "participant_joined",        # participation
        "human_input_addressed",     # participation
        "post_action_verified",      # oversight
    ):
        assert expected in vals


def test_str_enum_serializes_as_string() -> None:
    assert s.InstanceStatus.RUNNING == "running"
    assert s.RoleKind.AGENT.value == "agent"
