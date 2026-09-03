from datetime import datetime, timezone

from agent.context import AgentExecutionContext, CapabilityScope
from events import StandardizedEvent
from tasks.graph import (
    TaskGraphDefinition,
    TaskGraphNodeDefinition,
    TaskGraphNodeType,
    TaskGraphRun,
)
from tasks.task import Task, TaskState


def make_event(trace_id: str = "trace-task") -> StandardizedEvent:
    return StandardizedEvent(
        trace_id=trace_id,
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
        trace_id="trace-task",
        handoff_goal="",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ()),
    )


def test_task_is_the_single_runtime_aggregate_with_created_invariants():
    event = make_event()
    task = Task(
        "task-1",
        trace_id=event.trace_id,
        source_event=event,
        execution_context=make_context(),
    )

    assert task.state is TaskState.CREATED
    assert task.handoff is None
    assert task.graph is None
    assert task.completion is None
    assert task.terminal_outcome is None
    assert task.execution_context.task_id == task.task_id


def test_task_mutable_state_is_isolated():
    event = make_event()
    first = Task(
        "task-1",
        trace_id=event.trace_id,
        source_event=event,
        execution_context=make_context("task-1"),
    )
    second = Task(
        "task-2",
        trace_id=event.trace_id,
        source_event=event,
        execution_context=make_context("task-2"),
    )

    first.set_task_state("value", 1)

    assert first.task_local_state == {"value": 1}
    assert second.task_local_state == {}


def test_active_step_ids_are_derived_from_graph_node_runs():
    event = make_event()
    definition = TaskGraphDefinition(
        graph_id="graph-1",
        version="1",
        nodes=(
            TaskGraphNodeDefinition("reason", TaskGraphNodeType.REASONING, {}),
            TaskGraphNodeDefinition("step-a", TaskGraphNodeType.STEP, {}),
            TaskGraphNodeDefinition("step-b", TaskGraphNodeType.STEP, {}),
        ),
        edges=(),
        entry_node_ids=("reason", "step-a", "step-b"),
        terminal_node_ids=("reason", "step-a", "step-b"),
    )
    run = TaskGraphRun(
        definition,
        {
            "reason": {"state": "running"},
            "step-a": {"state": "ready"},
            "step-b": {"state": "succeeded"},
        },
    )
    task = Task(
        "task-1",
        trace_id=event.trace_id,
        source_event=event,
        execution_context=make_context(),
        graph=run,
    )

    assert task.active_step_ids == ("step-a",)
    assert "active_step_ids" not in task.__slots__
