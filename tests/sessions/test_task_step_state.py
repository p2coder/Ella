from dataclasses import replace
from datetime import datetime, timezone

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from sessions.execution_state import ToolFailureKind, ToolFailureObservation
from sessions.session import TaskSession, TaskState


def make_session(suffix: str) -> TaskSession:
    event = StandardizedEvent(
        trace_id=f"trace-{suffix}",
        source="test",
        timestamp=datetime(2026, 7, 2, tzinfo=timezone.utc),
        payload={"text": "test"},
        event_type="USER_UTTERANCE",
    )
    return TaskSession(
        session_id=f"session-{suffix}",
        task_id=f"task-{suffix}",
        handoff=HandoffRequest(
            task_goal="Test isolated step state.",
            trigger_event=event,
            user_preference_summary="",
            environment_summary="",
            context_summary="",
            constraints=(),
            completion_criteria=("The test task is complete.",),
        ),
    )


def test_new_session_starts_with_isolated_step1_try():
    first = make_session("first")
    second = make_session("second")

    assert first.current_step.attempt_id == "step1_try"
    assert first.step_history == ()
    assert first.current_step is not second.current_step


def test_step_state_does_not_leak_between_sessions():
    first = make_session("first")
    second = make_session("second")
    failure = ToolFailureObservation(
        attempt_id="step1_try",
        tool_name="camera_scene",
        kind=ToolFailureKind.PERMISSION_DENIED,
        code="permission_denied",
        message="camera permission denied",
        arguments={},
        retryable=False,
    )

    first.current_step = replace(
        first.current_step,
        blacklisted_tools=("camera_scene",),
        failures=(failure,),
    )

    assert second.current_step.blacklisted_tools == ()
    assert second.current_step.failures == ()


def test_archived_step_is_not_changed_when_current_step_is_replaced():
    session = make_session("archive")
    archived = replace(
        session.current_step,
        blacklisted_tools=("camera_scene",),
    )
    session.step_history += (archived,)
    session.current_step = replace(
        session.current_step,
        step_number=2,
        blacklisted_tools=(),
    )

    assert session.step_history == (archived,)
    assert session.step_history[0].blacklisted_tools == ("camera_scene",)
    assert session.current_step.attempt_id == "step2_try"


def test_existing_task_state_transitions_remain_compatible():
    session = make_session("state")

    session.transition_to(TaskState.READY)
    session.transition_to(TaskState.RUNNING)

    assert session.state is TaskState.RUNNING
