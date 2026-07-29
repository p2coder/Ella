from pathlib import Path

from events import RawSignal
from runtime.event_runtime import EventRuntime
from runtime.task_queue import TaskQueue
from runtime.task_runtime import TaskRuntime
from runtime.task_store import TaskStore
from sessions.session import TaskState
from sessions.session_manager import TaskFactory


def signal() -> RawSignal:
    return RawSignal(
        trace_id="trace-create-flow",
        source="cli_input",
        payload={"text": "hello"},
        signal_type="cli_text",
        metadata={"trigger_kind": "user_initiated"},
    )


def test_task_is_created_and_persisted_before_formulation_then_enqueued(tmp_path):
    store = TaskStore(tmp_path)
    queue = TaskQueue()
    runtime = TaskRuntime(
        session_manager=TaskFactory(task_id_factory=lambda: "task-flow"),
        task_store=store,
        task_queue=queue,
    )
    event_runtime = EventRuntime(task_runtime=runtime)

    result = event_runtime.publish(signal())
    record = store.load("task-flow")

    assert result.submitted is True
    assert result.task_handle.task_id == "task-flow"
    assert record.task.state is TaskState.READY
    assert record.task.handoff is not None
    assert record.task.execution_context.task_id == "task-flow"
    assert queue.snapshot() == ("task-flow",)


class FailingAgent:
    llm_provider = None

    def create_handoff(self, **kwargs):
        raise RuntimeError("formulation unavailable")


def test_formulation_failure_persists_failed_and_does_not_enqueue(tmp_path):
    store = TaskStore(tmp_path)
    queue = TaskQueue()
    runtime = TaskRuntime(
        session_manager=TaskFactory(task_id_factory=lambda: "task-failed"),
        task_store=store,
        task_queue=queue,
    )
    event_runtime = EventRuntime(task_runtime=runtime, main_agent=FailingAgent())

    result = event_runtime.publish(signal())

    assert result.submitted is False
    assert store.load("task-failed").task.state is TaskState.FAILED
    assert queue.snapshot() == ()
