from datetime import datetime, timedelta, timezone

from runtime.waiting import WaitingRegistry, current_tool_availability
from sessions.execution_state import StepToolAvailability, StepToolAvailabilityState, WaitingCondition, WaitingKind


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_user_and_external_waits_require_matching_correlation():
    registry = WaitingRegistry()
    condition = WaitingCondition(WaitingKind.USER_INPUT, "reply-1", "need input", None, NOW)
    registry.register("task", condition)
    assert registry.should_wake("task", correlation_key="other") is False
    assert registry.should_wake("task", correlation_key="reply-1") is True


def test_time_wait_wakes_at_deadline():
    registry = WaitingRegistry()
    registry.register("task", WaitingCondition(WaitingKind.TIME, "timer", "wait", NOW + timedelta(seconds=5), NOW))
    assert registry.should_wake("task", now=NOW) is False
    assert registry.should_wake("task", now=NOW + timedelta(seconds=5)) is True


def test_step_block_expires_directly_to_available_and_is_step_local():
    blocked = StepToolAvailability("step-a", "camera", StepToolAvailabilityState.BLOCKED, "busy", NOW + timedelta(seconds=5), NOW)
    assert current_tool_availability(blocked, now=NOW).state is StepToolAvailabilityState.BLOCKED
    available = current_tool_availability(blocked, now=NOW + timedelta(seconds=6))
    assert available.state is StepToolAvailabilityState.AVAILABLE
    assert available.blocked_reason is None
    other = StepToolAvailability("step-b", "camera")
    assert other.state is StepToolAvailabilityState.AVAILABLE


def test_permanent_block_does_not_expire():
    blocked = StepToolAvailability("step", "tool", StepToolAvailabilityState.BLOCKED, "permission", None, NOW)
    assert current_tool_availability(blocked, now=NOW + timedelta(days=1)) is blocked
