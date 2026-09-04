from datetime import datetime, timezone

from agent.context import AgentExecutionContext, CapabilityScope
from events import StandardizedEvent
from tasks.task import Task, TaskState


def make_event(task_id: str = "task-task") -> StandardizedEvent:
    return StandardizedEvent(
        task_id=task_id,
        source="test",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        payload={"text": "hello"},
        event_type="USER_UTTERANCE",
        metadata={},
    )


def make_context(task_id: str = "task-1") -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id=task_id,
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ()),
    )


def test_task_is_the_single_runtime_aggregate_with_created_invariants():
    event = make_event()
    task = Task(
        "task-1",
        source_event=event,
        execution_context=make_context(),
    )

    assert task.state is TaskState.CREATED
    assert task.completion is None
    assert task.terminal_outcome is None
    assert task.execution_context.task_id == task.task_id


def test_task_mutable_state_is_isolated():
    event = make_event()
    first = Task(
        "task-1",
        source_event=event,
        execution_context=make_context("task-1"),
    )
    second = Task(
        "task-2",
        source_event=event,
        execution_context=make_context("task-2"),
    )

    first.set_task_state("value", 1)

    assert first.task_local_state == {"value": 1}
    assert second.task_local_state == {}
