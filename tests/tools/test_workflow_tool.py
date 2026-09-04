from dataclasses import dataclass
from threading import Barrier, Lock
from time import monotonic, sleep

import pytest

from agent.child_runner import ChildAgentRun
from agent.context import AgentExecutionContext, CapabilityScope
from runtime.workflow_runtime import WorkflowRuntime
from tasks.task import Task, TaskState


@dataclass
class FakeChildRunner:
    barrier: Barrier | None = None

    def __post_init__(self):
        self.calls = []
        self.lock = Lock()

    def run(self, context, *, prompt, timeout_seconds, fork=False):
        started = monotonic()
        with self.lock:
            self.calls.append(("start", prompt, started, fork))
        if self.barrier is not None:
            self.barrier.wait(timeout=2)
        sleep(0.02)
        completed = monotonic()
        with self.lock:
            self.calls.append(("end", prompt, completed, fork))
        return ChildAgentRun(
            child_agent_id=f"child-{prompt}",
            status="completed",
            final_response=f"answer-{prompt}",
            observations=(),
            error=None,
            provider_usage=None,
            completed_at="2026-09-04T00:00:01Z",
            mode="fork" if fork else "clean",
            depth=1,
            parent_agent_id=context.agent_id,
            capability_scope=context.capability_scope.to_dict(),
            started_at="2026-09-04T00:00:00Z",
            provider_usage_calls=(),
        )


def _context():
    return AgentExecutionContext(
        agent_id="parent",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-workflow",
        trace_id="trace-workflow",
        handoff_goal="Run workflow",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ("workflow",)),
    )


def _runtime(runner):
    task = Task("task-workflow", state=TaskState.TOOL_EXECUTION)
    return WorkflowRuntime(runner, lambda _: task, max_wall_seconds=3)


def test_workflow_await_runs_children_in_sequence() -> None:
    runner = FakeChildRunner()
    result = _runtime(runner).execute(
        _context(),
        "const a = await tools.subagent({prompt: 'a'});\n"
        "const b = await tools.subagent_fork({prompt: 'b'});\n"
        "return [a.final_response, b.final_response];",
    )

    assert result["script_return_value"] == ["answer-a", "answer-b"]
    assert [item["tool_name"] for item in result["child_results"]] == [
        "subagent",
        "subagent_fork",
    ]
    events = {(kind, prompt): timestamp for kind, prompt, timestamp, _ in runner.calls}
    assert events[("end", "a")] <= events[("start", "b")]


def test_workflow_promise_all_dispatches_children_in_parallel() -> None:
    runner = FakeChildRunner(Barrier(2))
    result = _runtime(runner).execute(
        _context(),
        "const values = await Promise.all(["
        "tools.subagent({prompt: 'a'}),"
        "tools.subagent_fork({prompt: 'b'})"
        "]); return values.map(value => value.final_response);",
    )

    assert result["script_return_value"] == ["answer-a", "answer-b"]
    assert len(result["child_results"]) == 2


@pytest.mark.parametrize(
    "script",
    (
        "return await tools.read({path: 'secret'});",
        "return eval('1 + 1');",
        "return process.cwd();",
        "return require('fs');",
    ),
)
def test_workflow_rejects_unexposed_host_capabilities(script) -> None:
    runner = FakeChildRunner()
    with pytest.raises(RuntimeError, match="workflow script failed"):
        _runtime(runner).execute(_context(), script)
    assert runner.calls == []


def test_workflow_rejects_invalid_script_before_child_dispatch() -> None:
    runner = FakeChildRunner()
    with pytest.raises(RuntimeError, match="workflow script failed"):
        _runtime(runner).execute(_context(), "return (")
    assert runner.calls == []
