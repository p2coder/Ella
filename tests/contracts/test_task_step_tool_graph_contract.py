from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from runtime.task_queue import TaskQueue
from runtime.trace import TraceRecorder
from runtime.waiting import WaitingRegistry, current_tool_availability
from sessions.session import TaskSession
from tasks.graph import (
    DynamicGraphCapacity,
    GraphEdge,
    TaskGraphDefinition,
    TaskGraphNodeDefinition,
    TaskGraphNodeType,
    TaskGraphRun,
)
from tasks.state import (
    StepExecutionState,
    StepState,
    StepToolAvailability,
    StepToolAvailabilityState,
    ToolNodeState,
    WaitingCondition,
    WaitingKind,
    any_terminal_succeeded,
)
from tasks.task import Task, TaskState
from tools.base import ToolDefinition, ToolIdempotency, ToolUncertainPolicy
from tools.manager import ToolManager


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _task_graph(node_runs=None):
    nodes = (
        TaskGraphNodeDefinition("a", TaskGraphNodeType.STEP, {}),
        TaskGraphNodeDefinition("b", TaskGraphNodeType.STEP, {}),
        TaskGraphNodeDefinition("c", TaskGraphNodeType.STEP, {}),
    )
    definition = TaskGraphDefinition(
        "graph", "v1", nodes,
        (GraphEdge("a", "c", {"outcome": "success"}, 2), GraphEdge("b", "c", None, 1)),
        ("a", "b"), ("c",),
    )
    return TaskGraphRun(definition, node_runs or {})


def test_task_is_only_aggregate_and_queue_contains_ids_only():
    task = Task("task")
    assert TaskSession is Task
    assert not hasattr(task, "session_id")
    assert "session_id" not in {field.name for field in fields(Task)}
    queue = TaskQueue()
    queue.enqueue(task.task_id)
    assert queue.snapshot() == ("task",)


def test_graph_topology_conditions_and_priority_live_on_edges_only():
    run = _task_graph()
    assert run.definition.predecessors("c") == ("b", "a")
    assert run.definition.stable_ready_order(("a", "b")) == ("a", "b")
    assert all(edge.condition is None or "outcome" in edge.condition for edge in run.definition.edges)
    assert not hasattr(run.definition.nodes[0], "depends_on")


def test_node_runs_are_active_step_source_and_any_terminal_is_success():
    run = _task_graph({"a": {"state": "ready"}, "b": {"state": "failed"}})
    task = Task("task", graph=run)
    assert task.active_step_ids == ("a",)
    assert any_terminal_succeeded(
        {"left": ToolNodeState.FAILED, "right": ToolNodeState.SUCCEEDED},
        ("left", "right"),
    )


def test_dynamic_capacity_uses_five_slots_then_doubles_and_retry_budget_is_independent():
    capacity = DynamicGraphCapacity.initial(20)
    assert capacity.allocated_slots == 5
    for _ in range(6):
        capacity = capacity.consume()
    assert capacity.allocated_slots == 10
    state = StepExecutionState(max_argument_retries=2)
    assert state.max_argument_retries == 2
    assert capacity.max_slots == 20


def test_tool_definition_is_execution_metadata_authority():
    definition = ToolDefinition(
        "tool", "description", "1", {"type": "object"}, (), {"type": "object"},
        version="2", idempotency=ToolIdempotency.IDEMPOTENT,
        side_effecting=True, uncertain_policy=ToolUncertainPolicy.POSSIBLE_AFTER_DISPATCH,
        overridable_fields=("side_effecting",),
    )
    tool = type("Tool", (), {"name": "tool", "allowed_roles": ("main_agent",), "definition": definition})()
    manager = ToolManager()
    manager.register(tool)
    metadata = manager.resolve_execution_metadata("tool", "2", {"side_effecting": False})
    assert metadata.name == "tool"
    assert metadata.overridden_fields == ("side_effecting",)
    with pytest.raises(ValueError):
        manager.resolve_execution_metadata("tool", "2", {"idempotency": "unknown"})


def test_step_tool_block_is_isolated_and_expires_directly_to_available():
    blocked = StepToolAvailability(
        "step-a", "camera", StepToolAvailabilityState.BLOCKED,
        "busy", NOW + timedelta(seconds=5), NOW,
    )
    assert current_tool_availability(blocked, now=NOW).state is StepToolAvailabilityState.BLOCKED
    assert current_tool_availability(blocked, now=NOW + timedelta(seconds=6)).state is StepToolAvailabilityState.AVAILABLE
    assert StepToolAvailability("step-b", "camera").state is StepToolAvailabilityState.AVAILABLE


def test_waiting_requires_correlation_or_deadline():
    registry = WaitingRegistry()
    registry.register("task", WaitingCondition(WaitingKind.USER_INPUT, "reply", "need reply", None, NOW))
    assert not registry.should_wake("task", correlation_key="other")
    assert registry.should_wake("task", correlation_key="reply")
    registry.register("timer", WaitingCondition(WaitingKind.TIME, "timer", "delay", NOW, NOW))
    assert registry.should_wake("timer", now=NOW)


def test_pause_origin_and_uncertain_terminal_rules_are_explicit():
    task = Task("task", state=TaskState.RUNNING)
    task.paused_from_state = task.state
    task.transition_to(TaskState.PAUSE_REQUESTED)
    task.transition_to(TaskState.PAUSED)
    task.transition_to(task.paused_from_state)
    assert task.state is TaskState.RUNNING
    uncertain = Task("uncertain", state=TaskState.UNCERTAIN)
    with pytest.raises(ValueError):
        uncertain.transition_to(TaskState.RUNNING)
    uncertain.transition_to(TaskState.FAILED)


def test_killed_is_terminal_and_success_or_failure_can_be_delivered():
    killed = Task("killed", state=TaskState.KILLED)
    with pytest.raises(ValueError):
        killed.transition_to(TaskState.READY)
    Task("success", state=TaskState.SUCCEEDED).transition_to(TaskState.DELIVERED)
    Task("failure", state=TaskState.FAILED).transition_to(TaskState.DELIVERED)


def test_trace_is_append_only_redacted_isolated_and_not_state_source():
    recorder = TraceRecorder()
    recorder.record(task_id="a", trace_id="ta", boundary="tool_attempt.x", event_type="failed", payload={"api_key": "secret"})
    recorder.record(task_id="b", trace_id="tb", boundary="task", event_type="created", payload={})
    snapshot = recorder.snapshot("a")
    assert snapshot.events[0].payload["api_key"] == "[REDACTED]"
    assert recorder.snapshot("b").task_id == "b"
    assert not hasattr(recorder, "transition_to")


def test_final_runtime_ownership_and_facade_boundaries_are_visible_in_source():
    runtime_source = Path("runtime/task_runtime.py").read_text(encoding="utf-8")
    app_source = Path("app_runtime.py").read_text(encoding="utf-8")
    web_source = Path("demo/web_ui.py").read_text(encoding="utf-8")
    assert "_sessions" not in runtime_source
    assert "from tasks." in runtime_source
    for command in ("submit_text", "get_task", "pause", "resume", "kill", "resolve_uncertain_as_failed"):
        assert f"def {command}" in app_source
    assert "TaskStore" not in web_source
    assert "CapabilityExecutor" not in web_source
    assert 'DEFAULT_HOST = "127.0.0.1"' in web_source
