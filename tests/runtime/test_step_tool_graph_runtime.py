from datetime import datetime, timezone

from agent.context import AgentExecutionContext, CapabilityScope
from events import StandardizedEvent
from runtime.step_runtime import StepRuntime, ToolNodeRunState
from sessions.executor import CapabilityExecutor
from sessions.graph import GraphEdge, ToolGraphDefinition, ToolGraphRun, ToolNodeDefinition
from sessions.session import Task
from sessions.strategy import StrategyDecision
from skill.manager import SkillManager
from tools.manager import ToolManager
from tools.mock_tools import MockWeatherTool


def setup_runtime():
    manager = ToolManager()
    manager.register(MockWeatherTool())
    executor = CapabilityExecutor(SkillManager(), manager)
    event = StandardizedEvent("trace-step", "test", {}, "USER_UTTERANCE", datetime(2026, 1, 1, tzinfo=timezone.utc), metadata={})
    context = AgentExecutionContext("agent", "main_agent", None, "task-step", "trace-step", "goal", "task_local", capability_scope=CapabilityScope("main_agent", (), ("mock_weather",)))
    task = Task("task-step", "task-step", trace_id="trace-step", source_event=event, execution_context=context)
    strategy = StrategyDecision("react", None, "test", None, ("done",), task_id="task-step")
    return StepRuntime(executor), task, context, strategy


def graph():
    return ToolGraphRun(
        ToolGraphDefinition(
            "tools",
            (
                ToolNodeDefinition("first", "mock_weather", "1", {}),
                ToolNodeDefinition("second", "mock_weather", "1", {}),
            ),
            (GraphEdge("first", "second"),),
            ("first",),
            ("second",),
        ),
        {},
    )


def test_one_tick_executes_one_ready_node_and_passes_arguments():
    runtime, task, context, strategy = setup_runtime()
    result = runtime.tick(graph(), task=task, context=context, strategy=strategy)

    assert result.selected_node_id == "first"
    assert result.graph_run.node_runs["first"].state is ToolNodeRunState.SUCCEEDED
    assert result.graph_run.node_runs["second"].state is ToolNodeRunState.PENDING
    assert len(result.graph_run.node_runs["first"].attempts) == 1


def test_terminal_success_completes_step_and_skips_unused_paths():
    runtime, task, context, strategy = setup_runtime()
    first = runtime.tick(graph(), task=task, context=context, strategy=strategy)
    second = runtime.tick(first.graph_run, task=task, context=context, strategy=strategy)

    assert second.selected_node_id == "second"
    assert second.step_state == "succeeded"


def test_blocked_tool_is_not_selected():
    runtime, task, context, strategy = setup_runtime()
    result = runtime.tick(graph(), task=task, context=context, strategy=strategy, availability={"mock_weather": "blocked"})
    assert result.selected_node_id is None
