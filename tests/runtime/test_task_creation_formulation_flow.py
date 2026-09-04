from pathlib import Path

from events import RawSignal
from runtime.event_runtime import EventRuntime
from runtime.task_queue import TaskQueue
from runtime.task_runtime import TaskRuntime
from runtime.task_store import TaskStore
from tasks.task import TaskState
from tasks.factory import TaskFactory


def signal() -> RawSignal:
    return RawSignal(
        trace_id="trace-create-flow",
        source="cli_input",
        payload={"text": "hello"},
        signal_type="cli_text",
        metadata={"trigger_kind": "user_initiated"},
    )


def test_task_is_created_without_intent_and_enqueued_for_first_decision(tmp_path):
    store = TaskStore(tmp_path)
    queue = TaskQueue()
    runtime = TaskRuntime(
        task_factory=TaskFactory(task_id_factory=lambda: "task-flow"),
        task_store=store,
        task_queue=queue,
    )
    event_runtime = EventRuntime(task_runtime=runtime)

    result = event_runtime.publish(signal())
    record = store.load("task-flow")

    assert result.submitted is True
    assert result.task_handle.task_id == "task-flow"
    assert record.task.state is TaskState.READY
    assert record.task.intent is None
    assert record.task.execution_context.task_id == "task-flow"
    assert queue.snapshot() == ()
