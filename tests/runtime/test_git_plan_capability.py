import subprocess

from agent.context import AgentExecutionContext, CapabilityScope
from runtime.plan_store import PlanStep, PlanStore
from runtime.task_runtime import TaskRuntime
from tasks.task import Task
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
