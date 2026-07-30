from datetime import datetime, timezone

from agent.context import AgentExecutionContext, CapabilityScope
from events import StandardizedEvent
from runtime.task_queue import TaskQueue
from runtime.task_scheduler import TaskScheduler
from runtime.task_store import TaskStore
from sessions.session import Task, TaskState


def task(task_id: str, state: TaskState) -> Task:
    event = StandardizedEvent(
        trace_id=f"trace-{task_id}",
        source="test",
        payload={},
        event_type="USER_UTTERANCE",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        metadata={},
    )
    context = AgentExecutionContext(
        "agent", "main_agent", None, task_id, event.trace_id, "", "task_local",
        capability_scope=CapabilityScope("main_agent", (), ()),
    )
    return Task(task_id, task_id, trace_id=event.trace_id, source_event=event, execution_context=context, state=state)


def test_queue_is_idempotent_and_deterministic():
    queue = TaskQueue()
    assert queue.enqueue("a") is True
    assert queue.enqueue("a") is False
    assert queue.enqueue("b") is True
    assert queue.snapshot() == ("a", "b")
    assert queue.dequeue() == "a"


def test_scheduler_claims_only_ready_with_atomic_transition(tmp_path):
    store = TaskStore(tmp_path)
    store.save(task("ready", TaskState.READY))
    store.save(task("paused", TaskState.PAUSED))
    scheduler = TaskScheduler(store)

    assert scheduler.enqueue_ready("paused") is False
    assert scheduler.enqueue_ready("ready") is True
    claimed = scheduler.claim_next()

    assert claimed is not None and claimed.state is TaskState.RUNNING
    assert store.load("ready").task.state is TaskState.RUNNING


def test_rebuild_separates_normal_and_recovery_work(tmp_path):
    store = TaskStore(tmp_path)
    store.save(task("b-ready", TaskState.READY))
    store.save(task("a-running", TaskState.RUNNING))
    store.save(task("c-failed", TaskState.FAILED))
    scheduler = TaskScheduler(store)

    scheduler.rebuild()

    assert scheduler.queue.snapshot() == ("b-ready",)
    assert scheduler.recovery_queue.snapshot() == ("a-running",)
    assert scheduler.next_recovery().task.task_id == "a-running"


def test_stale_or_changed_task_is_skipped_at_claim(tmp_path):
    store = TaskStore(tmp_path)
    record = task("changed", TaskState.READY)
    store.save(record)
    scheduler = TaskScheduler(store)
    scheduler.enqueue_ready("changed")
    stored = store.load("changed")
    stored.task.state = TaskState.PAUSED
    store.save(stored.task, expected_version=stored.version)

    assert scheduler.claim_next() is None
