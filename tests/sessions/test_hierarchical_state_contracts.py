from datetime import datetime, timedelta, timezone

import pytest

from sessions.execution_state import (
    StepState,
    StepToolAvailability,
    StepToolAvailabilityState,
    TaskControlCommand,
    TaskControlType,
    ToolAttempt,
    ToolAttemptState,
    ToolNodeState,
    WaitingCondition,
    WaitingKind,
    any_terminal_succeeded,
)


NOW = datetime(2026, 7, 29, tzinfo=timezone.utc)


def test_hierarchical_states_include_explicit_skipped_and_uncertain():
    assert StepState.SKIPPED.value == "skipped"
    assert StepState.UNCERTAIN.value == "uncertain"
    assert ToolNodeState.SKIPPED.value == "skipped"
    assert ToolNodeState.UNCERTAIN.value == "uncertain"


def test_time_waiting_condition_requires_wake_time():
    with pytest.raises(ValueError, match="wake_at"):
        WaitingCondition(WaitingKind.TIME, "timer", "cooldown", None, NOW)
    value = WaitingCondition(
        WaitingKind.TIME, "timer", "cooldown", NOW + timedelta(seconds=5), NOW
    )
    assert value.wake_at > value.created_at


def test_control_command_has_task_scoped_idempotency_fields():
    command = TaskControlCommand(
        "command-1", "task-1", TaskControlType.PAUSE, NOW, "user"
    )
    assert (command.task_id, command.command_id) == ("task-1", "command-1")


def test_available_step_tool_cannot_carry_block_details():
    with pytest.raises(ValueError, match="blocked details"):
        StepToolAvailability(
            "step-1",
            "camera_scene",
            StepToolAvailabilityState.AVAILABLE,
            blocked_reason="busy",
        )


def test_tool_attempt_index_is_local_and_starts_at_one():
    with pytest.raises(ValueError, match="start at 1"):
        ToolAttempt("attempt", 0, {}, ToolAttemptState.RUNNING)
    source = {"count": 1}
    attempt = ToolAttempt("attempt", 1, source, ToolAttemptState.RUNNING)
    source["count"] = 2
    assert attempt.arguments["count"] == 1


def test_any_terminal_success_policy():
    states = {"left": StepState.FAILED, "right": StepState.SUCCEEDED}
    assert any_terminal_succeeded(states, ("left", "right")) is True
    assert any_terminal_succeeded(states, ("left",)) is False
