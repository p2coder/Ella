from agent.subagent import SubAgent
from providers.base import ProviderResult
from runtime.executor import CapabilityExecutor
from runtime.task_runtime import TaskRuntime
from skill.manager import SkillManager
from tasks.factory import TaskFactory
from tasks.graph import (
    TaskGraphDefinition,
    TaskGraphNodeDefinition,
    TaskGraphNodeType,
    TaskGraphRun,
)
from tasks.task import TaskIntent, TaskState
from tools.manager import ToolManager

from tests.runtime.test_first_decision_flow import _event


class PlanSummaryProvider:
    provider_name = "plan-summary-test"
    model_name = "test-model"

    def generate(self, prompt, *, trace_id=None, metadata=None):
        assert metadata == {"boundary": "execution_decision"}
        assert "execution_complete: True" in prompt
        return ProviderResult(
            self.provider_name,
            self.model_name,
            trace_id,
            {
                "action": "SUBMIT_RESULT",
                "decision_reason": "The completed plan now has a final result.",
                "completion_summary": "The plan completed.",
                "final_response_draft": "计划已经执行完成。",
                "evidence_refs": [],
            },
        )


def _runtime(provider=None):
    tools = ToolManager()
    skills = SkillManager()
    subagent = SubAgent(
        skills,
        tool_directory=tools,
        llm_provider=provider,
    )
    runtime = TaskRuntime(
        task_factory=TaskFactory(
            task_id_factory=lambda: "task-plan-completion",
            tool_manager=tools,
        ),
        subagent=subagent,
        executor=CapabilityExecutor(subagent, skills, tools),
    )
    handle = runtime.create_task(_event())
    task = runtime.get_task(handle.task_id)
    runtime._commit_task_intent(
        task,
        TaskIntent(
            goal="Complete the plan.",
            deliverables=("A completed result.",),
            minimum_acceptance_criteria=(),
        ),
    )
    task.state = TaskState.REASONING
    definition = TaskGraphDefinition(
        graph_id="plan-task",
        version="v1",
        nodes=(
            TaskGraphNodeDefinition(
                "terminal",
                TaskGraphNodeType.STEP,
                {"goal": "Finish the plan", "completion_criteria": ()},
            ),
        ),
        edges=(),
        entry_node_ids=("terminal",),
        terminal_node_ids=("terminal",),
    )
    task.graph = TaskGraphRun(definition, {})
    return runtime, task


def test_terminal_node_submit_result_is_verified_without_extra_reasoning() -> None:
    runtime, task = _runtime()
    runs = {
        "terminal": {
            "state": "succeeded",
            "completion_summary": "The terminal node completed the plan.",
            "final_response_draft": "计划已经执行完成。",
            "evidence_refs": (),
        }
    }
    task.graph = TaskGraphRun(task.graph.definition, runs)

    runtime._complete_graph_task(runtime._tasks[task.task_id], runs)

    assert task.state is TaskState.COMPLETED
    assert task.completion.user_visible_output.final_response == "计划已经执行完成。"
    assert task.task_local_state.get("plan_execution_complete") is None


def test_completed_plan_without_submit_schedules_one_normal_reasoning() -> None:
    runtime, task = _runtime(PlanSummaryProvider())
    runs = {"terminal": {"state": "succeeded"}}
    task.graph = TaskGraphRun(task.graph.definition, runs)

    runtime._complete_graph_task(runtime._tasks[task.task_id], runs)

    assert task.state is TaskState.REASONING
    assert task.task_local_state["plan_execution_complete"] is True
    assert task.task_local_state["pending_reasoning"]["purpose"] == "execution"

    result = runtime.step(task.task_id)

    assert result.stop_reason == "completed"
    assert result.completion.user_visible_output.final_response == "计划已经执行完成。"
