from datetime import datetime, timezone

from agent.context import AgentExecutionContext, CapabilityScope
from events import StandardizedEvent
from runtime.task_runtime import TaskRuntime
from sessions.graph import TaskGraphDefinition, TaskGraphNodeDefinition, TaskGraphNodeType, TaskGraphRun
from sessions.session import TaskState
from sessions.session_manager import TaskCreationResult, TaskFactory


def runtime_with_graph(tmp_path, *, max_runtime_ticks=2):
    event = StandardizedEvent("trace-graph", "test", {}, "USER_UTTERANCE", datetime(2026, 1, 1, tzinfo=timezone.utc), metadata={})
    factory = TaskFactory(task_id_factory=lambda: "task-graph")
    task = factory.create_task.__self__ if False else None
    context = AgentExecutionContext("agent", "main_agent", None, "task-graph", "trace-graph", "goal", "task_local", capability_scope=CapabilityScope("main_agent", (), ()))
    from sessions.session import Task
    task = Task("task-graph", "task-graph", trace_id="trace-graph", source_event=event, execution_context=context, state=TaskState.RUNNING)
    definition = TaskGraphDefinition(
        "graph", "1",
        (TaskGraphNodeDefinition("step", TaskGraphNodeType.STEP, {}),),
        (), ("step",), ("step",),
    )
    task.graph = TaskGraphRun(definition, {})
    creation = TaskCreationResult(task)
    runtime = TaskRuntime(max_runtime_ticks=max_runtime_ticks, max_steps=2)
    runtime._tasks[task.task_id] = creation
    return runtime, task


def test_missing_step_graph_fails_terminally_in_one_tick(tmp_path):
    runtime, task = runtime_with_graph(tmp_path)
    runtime.step(task.task_id)
    result = runtime.step(task.task_id)
    assert result.session.state is TaskState.FAILED
    assert result.failure_reason == "no_reachable_success_terminal"


def test_runtime_tick_budget_produces_stable_failed_state(tmp_path):
    runtime, task = runtime_with_graph(tmp_path, max_runtime_ticks=0)
    result = runtime.step(task.task_id)
    assert result.session.state is TaskState.FAILED
    assert result.failure_reason == "max_runtime_ticks_exhausted"


def test_active_step_ids_remain_graph_projection(tmp_path):
    runtime, task = runtime_with_graph(tmp_path)
    task.graph = TaskGraphRun(task.graph.definition, {"step": {"state": "ready"}})
    assert task.active_step_ids == ("step",)
