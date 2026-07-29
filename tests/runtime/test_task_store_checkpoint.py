from datetime import datetime, timezone
import json

import pytest

from agent.context import AgentExecutionContext, CapabilityScope
from events import StandardizedEvent
from runtime.task_store import (
    CorruptTaskCheckpoint,
    TaskStore,
    TaskStoreError,
    TaskVersionConflict,
)
from sessions.session import Task, TaskState


def make_task(task_id: str = "task-store") -> Task:
    event = StandardizedEvent(
        trace_id="trace-store",
        source="test",
        payload={"text": "hello"},
        event_type="USER_UTTERANCE",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        metadata={},
    )
    context = AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id=task_id,
        trace_id=event.trace_id,
        handoff_goal="",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ("tool",)),
    )
    return Task(task_id, task_id, trace_id=event.trace_id, source_event=event, execution_context=context)


def test_checkpoint_round_trip_and_deterministic_list(tmp_path):
    store = TaskStore(tmp_path)
    task = make_task()

    assert store.save(task) == 1
    loaded = store.load(task.task_id)

    assert loaded is not None
    assert loaded.version == 1
    assert loaded.task.task_id == task.task_id
    assert loaded.task.execution_context.allowed_tools == ("tool",)
    assert [record.task.task_id for record in store.list()] == [task.task_id]


def test_compare_and_set_rejects_stale_version(tmp_path):
    store = TaskStore(tmp_path)
    task = make_task()
    store.save(task)

    with pytest.raises(TaskVersionConflict):
        store.save(task, expected_version=0)

    assert store.version(task.task_id) == 1


def test_checkpoint_excludes_secrets_and_full_prompt(tmp_path):
    store = TaskStore(tmp_path)
    task = make_task()
    task.task_local_state["api_key"] = "secret"

    with pytest.raises(TaskStoreError):
        store.save(task)
    assert store.load(task.task_id) is None


def test_corrupt_checkpoint_is_structured(tmp_path):
    (tmp_path / "task-store.json").write_text("{bad", encoding="utf-8")

    with pytest.raises(CorruptTaskCheckpoint):
        TaskStore(tmp_path).load("task-store")


@pytest.mark.parametrize(
    ("state", "classification"),
    ((TaskState.READY, "restorable"), (TaskState.RUNNING, "requires_recovery"), (TaskState.UNCERTAIN, "requires_resolution"), (TaskState.FAILED, "delivery_pending"), (TaskState.KILLED, "terminal")),
)
def test_recovery_classification(state, classification):
    task = make_task()
    task.state = state
    assert TaskStore.recovery_classification(task) == classification


def test_previous_checkpoint_survives_failed_replacement(tmp_path, monkeypatch):
    store = TaskStore(tmp_path)
    task = make_task()
    store.save(task)
    original = (tmp_path / "task-store.json").read_bytes()

    monkeypatch.setattr("runtime.task_store.os.replace", lambda *_: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(TaskStoreError):
        store.save(task, expected_version=1)

    assert (tmp_path / "task-store.json").read_bytes() == original
