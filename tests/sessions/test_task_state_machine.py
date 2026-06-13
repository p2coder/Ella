from datetime import datetime, timezone

import pytest

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from sessions.session import TaskSession, TaskState


def make_session(session_id: str = "session-state") -> TaskSession:
    event = StandardizedEvent(
        trace_id=f"trace-{session_id}",
        source="cli_input",
        timestamp=datetime(2026, 6, 13, 18, 0, tzinfo=timezone.utc),
        payload={"text": "Ella，我要出门了"},
        event_type="USER_UTTERANCE",
        metadata={"trigger_kind": "user_initiated"},
    )
    handoff = HandoffRequest(
        task_goal="Give the user a short reminder before leaving.",
        trigger_event=event,
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Mock environment context only.",
        context_summary="User is preparing to leave.",
        constraints=("Keep the reminder concise.",),
        completion_criteria=("A reminder is ready.",),
    )
    return TaskSession(
        session_id=session_id,
        task_id=f"task-{session_id}",
        handoff=handoff,
    )


def transition_path(session: TaskSession, *states: TaskState) -> None:
    for state in states:
        session.transition_to(state)


def test_new_task_session_starts_created_with_empty_task_local_results():
    session = make_session()

    assert session.state == TaskState.CREATED
    assert session.current_strategy is None
    assert session.completion is None
    assert session.failure_reason is None


@pytest.mark.parametrize(
    ("path", "expected"),
    (
        ((TaskState.PLANNING,), TaskState.PLANNING),
        ((TaskState.PLANNING, TaskState.RUNNING), TaskState.RUNNING),
        ((TaskState.PLANNING, TaskState.WAITING), TaskState.WAITING),
        ((TaskState.PLANNING, TaskState.FAILED), TaskState.FAILED),
        ((TaskState.PLANNING, TaskState.CANCELLED), TaskState.CANCELLED),
        (
            (TaskState.PLANNING, TaskState.RUNNING, TaskState.REPLANNING),
            TaskState.REPLANNING,
        ),
        (
            (TaskState.PLANNING, TaskState.RUNNING, TaskState.WAITING),
            TaskState.WAITING,
        ),
        (
            (TaskState.PLANNING, TaskState.RUNNING, TaskState.COMPLETED),
            TaskState.COMPLETED,
        ),
        (
            (TaskState.PLANNING, TaskState.RUNNING, TaskState.FAILED),
            TaskState.FAILED,
        ),
        (
            (TaskState.PLANNING, TaskState.RUNNING, TaskState.CANCELLED),
            TaskState.CANCELLED,
        ),
        (
            (
                TaskState.PLANNING,
                TaskState.RUNNING,
                TaskState.REPLANNING,
                TaskState.RUNNING,
            ),
            TaskState.RUNNING,
        ),
        (
            (
                TaskState.PLANNING,
                TaskState.RUNNING,
                TaskState.REPLANNING,
                TaskState.WAITING,
            ),
            TaskState.WAITING,
        ),
        (
            (
                TaskState.PLANNING,
                TaskState.RUNNING,
                TaskState.REPLANNING,
                TaskState.FAILED,
            ),
            TaskState.FAILED,
        ),
        (
            (
                TaskState.PLANNING,
                TaskState.RUNNING,
                TaskState.REPLANNING,
                TaskState.CANCELLED,
            ),
            TaskState.CANCELLED,
        ),
        (
            (TaskState.PLANNING, TaskState.WAITING, TaskState.PLANNING),
            TaskState.PLANNING,
        ),
        (
            (TaskState.PLANNING, TaskState.WAITING, TaskState.CANCELLED),
            TaskState.CANCELLED,
        ),
    ),
)
def test_valid_state_transitions_succeed(path, expected):
    session = make_session()

    transition_path(session, *path)

    assert session.state == expected


@pytest.mark.parametrize(
    "next_state",
    (
        TaskState.RUNNING,
        TaskState.REPLANNING,
        TaskState.WAITING,
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELLED,
    ),
)
def test_invalid_transition_raises_clear_error(next_state):
    session = make_session()

    with pytest.raises(
        ValueError,
        match=f"invalid task state transition: created -> {next_state.value}",
    ):
        session.transition_to(next_state)

    assert session.state == TaskState.CREATED


@pytest.mark.parametrize(
    "terminal_state",
    (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED),
)
def test_terminal_states_cannot_transition(terminal_state):
    session = make_session()
    transition_path(session, TaskState.PLANNING, TaskState.RUNNING)
    if terminal_state == TaskState.COMPLETED:
        session.transition_to(terminal_state)
    else:
        session.transition_to(terminal_state)

    with pytest.raises(ValueError, match="invalid task state transition"):
        session.transition_to(TaskState.PLANNING)


def test_strategy_completion_and_failure_are_task_local():
    first = make_session("first")
    second = make_session("second")
    strategy = {"mode": "skill", "skill_name": "going_out"}
    completion = {"summary": "Reminder prepared."}

    first.current_strategy = strategy
    first.completion = completion
    first.failure_reason = "memory unavailable"

    assert first.current_strategy is strategy
    assert first.completion is completion
    assert first.failure_reason == "memory unavailable"
    assert second.current_strategy is None
    assert second.completion is None
    assert second.failure_reason is None


def test_existing_task_local_state_behavior_still_works():
    first = make_session("first")
    second = make_session("second")

    first.set_task_state("reminder_style", "short")

    assert first.task_local_state == {"reminder_style": "short"}
    assert second.task_local_state == {}


def test_existing_positional_constructor_prefix_still_works():
    session = make_session()
    positional = TaskSession(
        session.session_id,
        session.task_id,
        session.handoff,
        TaskState.CREATED,
        {"reminder_style": "short"},
        ({"role": "user", "content": "Ella，我要出门了"},),
        ({"tool": "mock_checklist"},),
    )

    assert positional.task_local_state == {"reminder_style": "short"}
    assert positional.message_history[0]["role"] == "user"
    assert positional.tool_trace[0]["tool"] == "mock_checklist"
    assert positional.current_strategy is None
