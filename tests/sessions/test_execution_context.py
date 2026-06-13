from datetime import datetime, timezone

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from events import StandardizedEvent
from sessions import TaskSessionManager


FIXED_TIME = datetime(2026, 6, 13, 13, 30, tzinfo=timezone.utc)


def make_handoff() -> HandoffRequest:
    event = StandardizedEvent(
        trace_id="trace-execution-context",
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


def test_execution_context_carries_session_task_and_trace_ids():
    result = TaskSessionManager(
        session_id_factory=lambda: "session-context",
        task_id_factory=lambda: "task-context",
    ).create_session(make_handoff())

    context = result.context

    assert isinstance(context, AgentExecutionContext)
    assert context.session_id == "session-context"
    assert context.task_id == "task-context"
    assert context.trace_id == "trace-execution-context"
    assert context.handoff_goal == "Give the user a short, necessary reminder before leaving."


def test_execution_context_has_permissions_boundary_without_tool_calls():
    context = TaskSessionManager(
        session_id_factory=lambda: "session-permissions",
        task_id_factory=lambda: "task-permissions",
        allowed_tools=("read_visible_scene",),
        permissions=("read_context",),
        memory_scope="task_local",
    ).create_session(make_handoff()).context

    assert context.allowed_tools == ("read_visible_scene",)
    assert context.permissions == ("read_context",)
    assert context.memory_scope == "task_local"
    assert not hasattr(context, "tool_registry")
    assert not hasattr(context, "skill_registry")
    assert not hasattr(context, "memory_manager")


def test_execution_context_serializes_without_execution_results():
    context = TaskSessionManager(
        session_id_factory=lambda: "session-serialize",
        task_id_factory=lambda: "task-serialize",
    ).create_session(make_handoff()).context

    serialized = context.to_dict()

    assert serialized["session_id"] == "session-serialize"
    assert serialized["task_id"] == "task-serialize"
    assert serialized["trace_id"] == "trace-execution-context"
    assert "task_completion_package" not in serialized
    assert "selected_skill" not in serialized
