import subprocess

import pytest

from agent.context import AgentExecutionContext, CapabilityScope
from runtime.plan_store import PlanStep, PlanStore
from runtime.task_runtime import TaskRuntime
from tasks.task import Task
from tasks.graph import TaskGraphRun
from tools.base import CapabilityKind
from tools.plan import PlanWrittenTool


def _context(task_id: str = "task-plan") -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id=task_id,
        trace_id="trace-plan",
        handoff_goal="Build a plan",
        memory_scope="task_local",
        capability_scope=CapabilityScope(
            agent_role="main_agent",
            allowed_skills=(),
            allowed_tools=("plan_written",),
        ),
    )


def test_plan_store_uses_git_commits_and_active_task_ref(tmp_path) -> None:
    store = PlanStore(tmp_path / "plans.git")
    first = store.write(
        task_id="task-plan",
        steps=(PlanStep("a", "First", ("done",)),),
    )
    second = store.write(
        task_id="task-plan",
        steps=(
            PlanStep("a", "First", ("done",)),
            PlanStep("b", "Second", ("done",), ("a",)),
        ),
    )

    assert second.parent_version_id == first.version_id
    assert store.active_version("task-plan") == second.version_id
    assert store.load("task-plan", first.version_id) == first
    parent = subprocess.run(
        [
            "git",
            "--git-dir",
            str(tmp_path / "plans.git"),
            "rev-parse",
            f"{second.version_id}^",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert parent == first.version_id


def test_plan_written_uses_runtime_identity_and_activates_graph(tmp_path) -> None:
    tool = PlanWrittenTool(PlanStore(tmp_path / "plans.git"))
    assert tool.definition.capability_kind is CapabilityKind.RUNTIME
    assert "task_id" not in tool.definition.input_schema["properties"]
    result = tool.run(
        _context(),
        {
            "steps": [
                {
                    "step_id": "inspect",
                    "goal": "Inspect inputs",
                    "completion_criteria": ["inputs understood"],
                },
                {
                    "step_id": "finish",
                    "goal": "Produce result",
                    "completion_criteria": ["result delivered"],
                    "depends_on": ["inspect"],
                },
            ]
        },
    )
    task = Task(task_id="task-plan", trace_id="trace-plan")

    TaskRuntime._activate_plan(task, result.payload)

    assert task.graph is not None
    assert task.graph.definition.version == result.payload["version_id"]
    assert task.graph.definition.entry_node_ids == ("inspect",)
    assert task.graph.definition.terminal_node_ids == ("finish",)
    assert task.graph.definition.successors("inspect") == ("finish",)


def test_plan_definition_describes_executable_outcomes_and_parallelism(tmp_path) -> None:
    definition = PlanWrittenTool(PlanStore(tmp_path / "plans.git")).definition

    assert "independently executable and observable intermediate goal" in definition.description
    assert "same wave" in definition.description
    assert "success dependency" in definition.description
    assert "Tool observations" in definition.description
    criteria_schema = definition.input_schema["properties"]["steps"]["items"][
        "properties"
    ]["completion_criteria"]
    assert criteria_schema.get("minItems", 0) == 0


def test_plan_store_accepts_step_without_mechanical_criteria(tmp_path) -> None:
    store = PlanStore(tmp_path / "plans.git")

    record = store.write(
        task_id="task-plan",
        steps=(PlanStep("draft", "Draft the response", ()),),
    )

    assert record.steps[0].completion_criteria == ()


@pytest.mark.parametrize(
    "steps",
    (
        (PlanStep("a", " ", ()),),
        (PlanStep("a", "Goal", (" ",)),),
        (
            PlanStep("a", "First", ()),
            PlanStep("b", "Second", (), ("a", "a")),
        ),
        (PlanStep("a", "Goal", (), ("missing",)),),
        (
            PlanStep("a", "First", (), ("b",)),
            PlanStep("b", "Second", (), ("a",)),
        ),
    ),
)
def test_invalid_plan_does_not_replace_active_version(tmp_path, steps) -> None:
    store = PlanStore(tmp_path / "plans.git")
    active = store.write(
        task_id="task-plan",
        steps=(PlanStep("valid", "Valid goal", ()),),
    )

    with pytest.raises(ValueError):
        store.write(task_id="task-plan", steps=steps)

    assert store.active_version("task-plan") == active.version_id


def test_plan_update_migrates_only_unchanged_successful_nodes() -> None:
    task = Task(task_id="task-plan", trace_id="trace-plan")
    TaskRuntime._activate_plan(
        task,
        {
            "task_id": task.task_id,
            "version_id": "v1",
            "steps": (
                {
                    "step_id": "source",
                    "goal": "Collect source",
                    "completion_criteria": ("source captured",),
                },
                {
                    "step_id": "compare",
                    "goal": "Compare facts",
                    "completion_criteria": ("comparison written",),
                    "depends_on": ("source",),
                },
            ),
        },
    )
    task.graph = TaskGraphRun(
        task.graph.definition,
        {
            "source": {"state": "succeeded", "result": "source-result"},
            "compare": {"state": "succeeded", "result": "comparison-result"},
        },
    )

    TaskRuntime._activate_plan(
        task,
        {
            "task_id": task.task_id,
            "version_id": "v2",
            "steps": (
                {
                    "step_id": "source",
                    "goal": "Collect a different source",
                    "completion_criteria": ("source captured",),
                },
                {
                    "step_id": "compare",
                    "goal": "Compare facts",
                    "completion_criteria": ("comparison written",),
                    "depends_on": ("source",),
                },
            ),
        },
    )

    assert dict(task.graph.node_runs) == {}
