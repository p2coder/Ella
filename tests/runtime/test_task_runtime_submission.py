from datetime import datetime, timezone

import pytest

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from runtime.task_runtime import TaskHandle, TaskRuntime, TaskRuntimeResult
from sessions.session import TaskState
from sessions.session_manager import TaskSessionManager


def make_handoff(trace_id: str = "trace-task-runtime") -> HandoffRequest:
    return HandoffRequest(
        task_goal="Give the user a short reminder before leaving.",
        trigger_event=StandardizedEvent(
            trace_id=trace_id,
            source="cli_input",
            timestamp=datetime(2026, 6, 13, 14, 0, tzinfo=timezone.utc),
            payload={"text": "Ella，我要出门了"},
            event_type="USER_UTTERANCE",
            metadata={"trigger_kind": "user_initiated"},
        ),
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Mock environment only.",
        context_summary="User is preparing to leave.",
        constraints=("Keep the reminder short.",),
        completion_criteria=("A reminder is ready.",),
    )


def make_runtime(
    task_id_factory=lambda: "task-runtime",
    session_id_factory=lambda: "session-runtime",
) -> TaskRuntime:
    return TaskRuntime(
        session_manager=TaskSessionManager(
            allowed_tools=("mock_checklist",),
            task_id_factory=task_id_factory,
            session_id_factory=session_id_factory,
        )
    )


def test_submit_creates_session_and_context_and_returns_handle():
    runtime = make_runtime()

    handle = runtime.submit(make_handoff())

    assert handle == TaskHandle(
        task_id="task-runtime",
        session_id="session-runtime",
        trace_id="trace-task-runtime",
    )
    assert runtime.get_session(handle.task_id).session_id == handle.session_id
    assert runtime.get_context(handle.task_id).trace_id == handle.trace_id
    assert runtime.get_context(handle.task_id).allowed_tools == ("mock_checklist",)


def test_runtime_result_can_represent_submitted_task_without_execution():
    runtime = make_runtime()
    handle = runtime.submit(make_handoff())

    result = TaskRuntimeResult(
        handle=handle,
        session=runtime.get_session(handle.task_id),
        context=runtime.get_context(handle.task_id),
    )

    assert result.handle == handle
    assert result.session.state is TaskState.CREATED
    assert result.context.task_id == handle.task_id


def test_get_session_and_context_return_objects_from_same_creation():
    runtime = make_runtime()
    handle = runtime.submit(make_handoff())

    session = runtime.get_session(handle.task_id)
    context = runtime.get_context(handle.task_id)

    assert session.task_id == context.task_id == handle.task_id
    assert session.session_id == context.session_id == handle.session_id
    assert session.handoff.trigger_event.trace_id == context.trace_id


def test_duplicate_task_id_is_rejected_without_replacing_original():
    session_ids = iter(("session-first", "session-second"))
    runtime = make_runtime(
        task_id_factory=lambda: "duplicate-task",
        session_id_factory=lambda: next(session_ids),
    )
    first = runtime.submit(make_handoff("trace-first"))

    with pytest.raises(ValueError, match="duplicate task_id: duplicate-task"):
        runtime.submit(make_handoff("trace-second"))

    assert runtime.get_session(first.task_id).session_id == "session-first"
    assert runtime.get_context(first.task_id).trace_id == "trace-first"


def test_duplicate_session_id_is_rejected_without_storing_second_task():
    task_ids = iter(("task-first", "task-second"))
    runtime = make_runtime(
        task_id_factory=lambda: next(task_ids),
        session_id_factory=lambda: "duplicate-session",
    )
    runtime.submit(make_handoff("trace-first"))

    with pytest.raises(ValueError, match="duplicate session_id: duplicate-session"):
        runtime.submit(make_handoff("trace-second"))

    with pytest.raises(KeyError, match="task-second"):
        runtime.get_session("task-second")


def test_submit_leaves_task_unexecuted_in_created_state():
    runtime = make_runtime()
    handle = runtime.submit(make_handoff())
    session = runtime.get_session(handle.task_id)

    assert session.state is TaskState.CREATED
    assert session.current_strategy is None
    assert session.tool_trace == ()
    assert session.completion is None
    assert session.failure_reason is None
