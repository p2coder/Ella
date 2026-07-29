from datetime import datetime, timezone

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from sessions import TaskSessionManager, TaskState
from sessions.session import Task
from sessions.session_manager import TaskCreationResult, TaskFactory


FIXED_TIME = datetime(2026, 6, 13, 13, 0, tzinfo=timezone.utc)


def make_handoff(trace_id: str = "trace-session") -> HandoffRequest:
    event = StandardizedEvent(
        trace_id=trace_id,
        source="cli_input",
        timestamp=FIXED_TIME,
        payload={"text": "Ella，我要出门了"},
        event_type="USER_UTTERANCE",
        metadata={"trigger_kind": "user_initiated"},
    )
    return HandoffRequest(
        task_goal="Give the user a short, necessary reminder before leaving.",
        trigger_event=event,
        user_preference_summary="Prefers concise reminders.",
        environment_summary="No interpreted visual summary yet.",
        context_summary="User said they are about to leave.",
        constraints=("Keep the reminder short and necessary.",),
        completion_criteria=("A reminder goal is ready for handoff.",),
    )


def test_session_manager_creates_task_session_from_handoff():
    manager = TaskSessionManager(
        session_id_factory=lambda: "session-001",
        task_id_factory=lambda: "task-001",
    )

    result = manager.create_session(make_handoff())

    assert result.session.session_id == "session-001"
    assert result.session.task_id == "task-001"
    assert result.session.handoff.task_goal == (
        "Give the user a short, necessary reminder before leaving."
    )
    assert result.session.state == TaskState.CREATED
    assert result.session.task_local_state == {}
    assert result.session.message_history == ()
    assert result.session.tool_trace == ()


def test_session_manager_creates_context_after_session_boundary():
    manager = TaskSessionManager(
        session_id_factory=lambda: "session-002",
        task_id_factory=lambda: "task-002",
    )

    result = manager.create_session(make_handoff("trace-context"))

    assert result.context.session_id == result.session.session_id
    assert result.context.task_id == result.session.task_id
    assert result.context.trace_id == "trace-context"
    assert result.context.agent_id == "ella-main"
    assert result.context.agent_role == "main_agent"
    assert result.context.parent_agent_id is None


def test_task_sessions_keep_task_specific_state_isolated():
    manager = TaskSessionManager(
        session_id_factory=iter(["session-a", "session-b"]).__next__,
        task_id_factory=iter(["task-a", "task-b"]).__next__,
    )

    first = manager.create_session(make_handoff("trace-a")).session
    second = manager.create_session(make_handoff("trace-b")).session
    first.set_task_state("reminder_style", "short")

    assert first.task_local_state == {"reminder_style": "short"}
    assert second.task_local_state == {}
    assert first.session_id != second.session_id
    assert first.task_id != second.task_id


def test_task_session_does_not_select_or_execute_skill():
    session = TaskSessionManager(
        session_id_factory=lambda: "session-003",
        task_id_factory=lambda: "task-003",
    ).create_session(make_handoff()).session

    assert not hasattr(session, "skill_name")
    assert not hasattr(session, "execution_strategy")
    assert not hasattr(session, "run")


def test_task_factory_returns_the_task_aggregate_and_context_projection():
    result = TaskFactory(
        task_id_factory=lambda: "task-factory",
        session_id_factory=lambda: "legacy-session",
    ).create_task(make_handoff("trace-factory"))

    assert isinstance(result, TaskCreationResult)
    assert isinstance(result.task, Task)
    assert result.session is result.task
    assert result.context is result.task.execution_context
    assert result.task.trace_id == "trace-factory"
    assert result.task.source_event is result.task.handoff.trigger_event
