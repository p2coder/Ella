from threading import Barrier

from agent.decision import CALL_TOOL, COMPLETE, ExecutionDecision
from agent.handoff import HandoffRequest
from events import StandardizedEvent
from runtime.executor import CapabilityExecutionResult
from runtime.task_runtime import TaskRuntime
from tasks.factory import TaskFactory
from tasks.graph import TaskGraphDefinition, TaskGraphNodeDefinition, TaskGraphNodeType, TaskGraphRun
from tasks.state import ToolFailureKind, ToolFailureObservation
from tasks.task import TaskState


def _runtime(subagent, executor) -> tuple[TaskRuntime, str]:
    runtime = TaskRuntime(
        task_factory=TaskFactory(task_id_factory=lambda: "task-wave"),
        subagent=subagent,
        executor=executor,
        max_parallel_steps_per_task=2,
    )
    event = StandardizedEvent(
        trace_id="trace-wave",
        source="test",
        payload={"text": "run plan"},
        event_type="USER_UTTERANCE",
    )
    handle = runtime.submit(
        HandoffRequest("Run plan", event, "", "", "", (), ("done",))
    )
    task = runtime.get_task(handle.task_id)
    task.transition_to(TaskState.REASONING)
    return runtime, handle.task_id


def test_ready_nodes_execute_in_one_bounded_wave() -> None:
    barrier = Barrier(2)

    class SubAgent:
        def decide_next_action(
            self, handoff, context, task, *, current_goal=None, completion_criteria=None
        ):
            barrier.wait(timeout=1)
            return ExecutionDecision(
                COMPLETE,
                None,
                None,
                "The node goal is complete.",
                f"completed {current_goal}",
                (),
            )

    class Executor:
        def execute(self, decision, context, task):
            return CapabilityExecutionResult(decision)

    runtime, task_id = _runtime(SubAgent(), Executor())
    task = runtime.get_task(task_id)
    task.graph = TaskGraphRun(
        TaskGraphDefinition(
            graph_id="parallel",
            version="v1",
            nodes=(
                TaskGraphNodeDefinition("a", TaskGraphNodeType.STEP, {"goal": "A"}),
                TaskGraphNodeDefinition("b", TaskGraphNodeType.STEP, {"goal": "B"}),
            ),
            edges=(),
            entry_node_ids=("a", "b"),
            terminal_node_ids=("a", "b"),
        ),
        {},
    )

    result = runtime.step(task_id)

    assert result.task.state is TaskState.SUCCEEDED
    assert result.task.completion is not None
    assert result.task.task_local_state["wave_completed"] == 1
    assert {
        item["wave_id"] for item in result.task.graph.node_runs.values()
    } == {1}


def test_uncertain_node_overrides_success_in_same_wave() -> None:
    class SubAgent:
        def decide_next_action(
            self, handoff, context, task, *, current_goal=None, completion_criteria=None
        ):
            return ExecutionDecision(
                CALL_TOOL,
                "external_write",
                {},
                "The node requires an external write.",
            )

    class Executor:
        def execute(self, decision, context, task):
            failure = ToolFailureObservation(
                task.current_step.attempt_id,
                "external_write",
                ToolFailureKind.TOOL_EXECUTION_FAILED,
                "uncertain_tool_outcome",
                "The external outcome is unknown.",
                {},
                False,
            )
            return CapabilityExecutionResult(
                decision,
                failure=failure,
                uncertain=True,
            )

    runtime, task_id = _runtime(SubAgent(), Executor())
    task = runtime.get_task(task_id)
    task.graph = TaskGraphRun(
        TaskGraphDefinition(
            "uncertain",
            "v1",
            (TaskGraphNodeDefinition("a", TaskGraphNodeType.STEP, {"goal": "A"}),),
            (),
            ("a",),
            ("a",),
        ),
        {},
    )

    result = runtime.step(task_id)

    assert result.task.state is TaskState.UNCERTAIN
    assert result.stop_reason == "uncertain"


def test_successors_wait_for_next_wave_even_when_predecessor_finishes() -> None:
    seen: list[str] = []

    class SubAgent:
        def decide_next_action(
            self, handoff, context, task, *, current_goal=None, completion_criteria=None
        ):
            seen.append(current_goal)
            return ExecutionDecision(
                COMPLETE,
                None,
                None,
                "The node is complete.",
                f"completed {current_goal}",
                (),
            )

    class Executor:
        def execute(self, decision, context, task):
            return CapabilityExecutionResult(decision)

    runtime, task_id = _runtime(SubAgent(), Executor())
    task = runtime.get_task(task_id)
    from tasks.graph import GraphEdge

    task.graph = TaskGraphRun(
        TaskGraphDefinition(
            "barrier",
            "v1",
            (
                TaskGraphNodeDefinition("a", TaskGraphNodeType.STEP, {"goal": "A"}),
                TaskGraphNodeDefinition("b", TaskGraphNodeType.STEP, {"goal": "B"}),
                TaskGraphNodeDefinition("c", TaskGraphNodeType.STEP, {"goal": "C"}),
            ),
            (GraphEdge("a", "c"), GraphEdge("b", "c")),
            ("a", "b"),
            ("c",),
        ),
        {},
    )

    runtime.step(task_id)

    assert set(seen) == {"A", "B"}
    assert "c" not in task.graph.node_runs
    runtime.step(task_id)
    assert seen.count("C") == 1
