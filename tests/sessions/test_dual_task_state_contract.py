from datetime import datetime, timezone

import pytest

from agent.context import AgentExecutionContext, CapabilityScope
from events import StandardizedEvent
from runtime.task_store import TaskStore
from tasks.task import Task, TaskGoalState, TaskState


def _task() -> Task:
    event = StandardizedEvent(
        trace_id="trace-dual-state",
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
        task_id="task-dual-state",
        trace_id=event.trace_id,
        handoff_goal="",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ()),
    )
    return Task(
        task_id="task-dual-state",
        trace_id=event.trace_id,
        source_event=event,
        execution_context=context,
    )


def test_goal_state_has_only_three_terminal_outcomes() -> None:
    assert tuple(TaskGoalState) == (
        TaskGoalState.ACHIEVED,
        TaskGoalState.PARTIALLY_ACHIEVED,
        TaskGoalState.NOT_ACHIEVED,
    )


def test_active_task_has_no_goal_outcome() -> None:
    task = _task()
    task.transition_to(TaskState.READY)

    assert task.goal_state is None
    with pytest.raises(ValueError, match="terminal boundary"):
        task.set_goal_state(TaskGoalState.ACHIEVED)


def test_completed_task_can_commit_goal_outcome() -> None:
    task = _task()
    task.transition_to(TaskState.READY)
    task.transition_to(TaskState.REASONING)
    task.transition_to(TaskState.COMPLETED)
    task.set_goal_state(TaskGoalState.PARTIALLY_ACHIEVED)

    assert task.goal_state is TaskGoalState.PARTIALLY_ACHIEVED


def test_checkpoint_round_trips_dual_state(tmp_path) -> None:
    task = _task()
    task.transition_to(TaskState.READY)
    task.transition_to(TaskState.REASONING)
    task.transition_to(TaskState.COMPLETED)
    task.set_goal_state(TaskGoalState.ACHIEVED)
    task.terminal_execution_state = TaskState.COMPLETED
    task.transition_to(TaskState.DELIVERED)

    store = TaskStore(tmp_path)
    store.save(task)
    restored = store.load(task.task_id)

    assert restored is not None
    assert restored.task.state is TaskState.DELIVERED
    assert restored.task.goal_state is TaskGoalState.ACHIEVED
    assert restored.task.terminal_execution_state is TaskState.COMPLETED
