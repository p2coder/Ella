from datetime import datetime, timezone

from app_runtime import AppRuntime
from events import StandardizedEvent
from runtime.task_events import TaskEventPublisher
from runtime.task_runtime import TaskRuntime
from tasks.factory import TaskFactory
from tasks.task import TaskState


class _EventRuntime:
    pass


def _app():
    runtime = TaskRuntime(
        task_factory=TaskFactory(),
        event_publisher=TaskEventPublisher(),
    )
    event = StandardizedEvent(
        task_id="task-projection",
        source="test",
        timestamp=datetime.now(timezone.utc),
        payload={"text": "hello"},
        event_type="USER_UTTERANCE",
        metadata={},
    )
    runtime.create_task(event)
    return AppRuntime(_EventRuntime(), runtime), runtime


def test_app_runtime_lists_active_and_terminal_tasks_by_task_id():
    app, runtime = _app()
    assert [item["task_id"] for item in app.list_active_tasks()] == [
        "task-projection"
    ]

    task = runtime.get_task("task-projection")
    task.transition_to(TaskState.KILL_REQUESTED)
    task.transition_to(TaskState.KILLED)
    runtime._persist(task)

    assert app.list_active_tasks() == ()
    assert [item["task_id"] for item in app.list_terminal_tasks()] == [
        "task-projection"
    ]


def test_subscription_starts_with_full_snapshot():
    app, _ = _app()
    event = next(app.subscribe_task_events())

    assert event["event_type"] == "task_snapshot"
    assert event["payload"]["active_tasks"][0]["task_id"] == (
        "task-projection"
    )
    assert event["payload"]["recovery_errors"] == ()


def test_task_projection_exposes_timing_for_sse_and_web_ui():
    app, _ = _app()

    projection = app.get_task("task-projection")

    assert "timing" in projection
    assert "timing_summary" in projection
    assert projection["tool_observations"] == ()
