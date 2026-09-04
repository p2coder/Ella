from dataclasses import dataclass
from threading import Barrier, Lock
from time import monotonic, sleep

import pytest

from agent.child_runner import ChildAgentRun
from agent.context import AgentExecutionContext, CapabilityScope
from runtime.workflow_runtime import WorkflowRuntime
from runtime.trace import TraceRecorder
from tasks.task import Task, TaskState


@dataclass
class FakeChildRunner:
    barrier: Barrier | None = None
    response: str | None = None
    status: str = "completed"

    def __post_init__(self):
        self.calls = []
        self.timeouts = []
        self.lock = Lock()

    def run(self, context, *, prompt, timeout_seconds, fork=False):
        started = monotonic()
        with self.lock:
            self.calls.append(("start", prompt, started, fork))
            self.timeouts.append(timeout_seconds)
        if self.barrier is not None:
            self.barrier.wait(timeout=2)
        sleep(0.02)
        completed = monotonic()
        with self.lock:
            self.calls.append(("end", prompt, completed, fork))
        return ChildAgentRun(
            child_agent_id=f"child-{prompt}",
            status=self.status,
            final_response=self.response or f"answer-{prompt}",
            observations=(),
            error=None if self.status == "completed" else "child failed",
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
    assert result["status"] == "completed"
    assert result["active_tool_count"] == 0
    assert [item["tool_name"] for item in result["child_results"]] == [
        "subagent",
        "subagent_fork",
    ]
    assert all(item["status"] == "completed" for item in result["child_results"])
    assert all(item["called_at"] for item in result["child_results"])
    assert all(item["completed_at"] for item in result["child_results"])
    assert runner.timeouts == [300, 300]
    events = {(kind, prompt): timestamp for kind, prompt, timestamp, _ in runner.calls}
    assert events[("end", "a")] <= events[("start", "b")]


def test_workflow_exposes_only_a_frozen_noop_console() -> None:
    result = _runtime(FakeChildRunner()).execute(
        _context(),
        "console.log('not forwarded'); "
        "return [Object.isFrozen(console), typeof console.log];",
    )

    assert result["script_return_value"] == [True, "function"]


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


def test_workflow_child_failure_closes_dispatch_even_when_script_catches() -> None:
    runner = FakeChildRunner(status="failed")

    with pytest.raises(RuntimeError, match="workflow child failed") as raised:
        _runtime(runner).execute(
            _context(),
            "try { await tools.subagent({prompt: 'a'}); } catch (_) {}\n"
            "return await tools.subagent({prompt: 'must-not-run'});",
        )

    starts = [call for call in runner.calls if call[0] == "start"]
    assert [call[1] for call in starts] == ["a"]
    assert raised.value.tool_outcome_uncertain is False


def test_workflow_preserves_uncertain_child_outcome() -> None:
    runner = FakeChildRunner(status="uncertain")

    with pytest.raises(RuntimeError) as raised:
        _runtime(runner).execute(
            _context(),
            "return await tools.subagent({prompt: 'unknown'});",
        )

    assert raised.value.tool_outcome_uncertain is True


def test_workflow_records_script_and_child_trace_events() -> None:
    runner = FakeChildRunner()
    recorder = TraceRecorder()
    task = Task("task-workflow", state=TaskState.TOOL_EXECUTION)
    runtime = WorkflowRuntime(
        runner,
        lambda _: task,
        trace_recorder=recorder,
        max_wall_seconds=3,
    )

    runtime.execute(
        _context(),
        "return await tools.subagent({prompt: 'trace'});",
    )

    snapshot = recorder.snapshot("task-workflow")
    assert snapshot is not None
    assert [event.event_type for event in snapshot.events] == [
        "script_started",
        "tool_dispatched",
        "tool_completed",
        "promise_join",
        "script_completed",
    ]
    assert "script" not in snapshot.events[0].payload


def test_workflow_checkpoints_child_before_dispatch_and_after_completion() -> None:
    runner = FakeChildRunner()
    task = Task("task-workflow", state=TaskState.TOOL_EXECUTION)
    checkpoints = []
    runtime = WorkflowRuntime(
        runner,
        lambda _: task,
        progress_recorder=lambda _, state: checkpoints.append(state),
        max_wall_seconds=3,
    )

    runtime.execute(_context(), "return await tools.subagent({prompt: 'saved'});")

    running = [
        state
        for state in checkpoints
        if state["child_results"]
        and state["child_results"][0]["status"] == "running"
    ]
    assert running
    assert running[0]["active_tool_count"] == 1
    assert checkpoints[-1]["status"] == "completed"
    assert checkpoints[-1]["active_tool_count"] == 0
    assert checkpoints[-1]["child_results"][0]["status"] == "completed"


@pytest.mark.parametrize(
    "script",
    (
        "return await tools.read({path: 'secret'});",
        "return eval('1 + 1');",
        "return process.cwd();",
        "return require('fs');",
        "return await tools.workflow({script: 'return 1'});",
        "return __workflow_enqueue('subagent', '{}');",
        "tools = {}; return await tools.subagent({prompt: 'x'});",
    ),
)
def test_workflow_rejects_unexposed_host_capabilities(script) -> None:
    runner = FakeChildRunner()
    with pytest.raises(RuntimeError, match="workflow script failed"):
        _runtime(runner).execute(_context(), script)
    assert runner.calls == []


def test_workflow_enforces_script_child_and_return_limits() -> None:
    runner = FakeChildRunner()
    runtime = _runtime(runner)
    with pytest.raises(ValueError, match="byte limit"):
        runtime.execute(_context(), "a" * (64 * 1024 + 1))

    limited_calls = WorkflowRuntime(
        runner,
        runtime.task_reader,
        max_wall_seconds=3,
        max_parallel_children=1,
        max_total_children=1,
    )
    with pytest.raises(RuntimeError, match="child call limit exceeded"):
        limited_calls.execute(
            _context(),
            "return await Promise.all(["
            "tools.subagent({prompt:'a'}), tools.subagent({prompt:'b'})]);",
        )

    limited_return = WorkflowRuntime(
        runner,
        runtime.task_reader,
        max_wall_seconds=3,
        max_return_bytes=4,
    )
    with pytest.raises(ValueError, match="byte limit"):
        limited_return.execute(_context(), "return '12345';")

    limited_child_result = WorkflowRuntime(
        FakeChildRunner(response="x" * 1000),
        runtime.task_reader,
        max_wall_seconds=3,
        max_return_bytes=500,
    )
    with pytest.raises(ValueError, match="byte limit"):
        limited_child_result.execute(
            _context(),
            "await tools.subagent({prompt:'large'}); return null;",
        )


def test_workflow_terminates_infinite_script_at_wall_timeout() -> None:
    runner = FakeChildRunner()
    task = Task("task-workflow", state=TaskState.TOOL_EXECUTION)
    runtime = WorkflowRuntime(
        runner,
        lambda _: task,
        max_wall_seconds=0.1,
    )

    started = monotonic()
    with pytest.raises(TimeoutError, match="timed out"):
        runtime.execute(_context(), "while (true) {}")
    assert monotonic() - started < 2


def test_workflow_accepts_bounded_per_call_timeout() -> None:
    runner = FakeChildRunner()
    runtime = _runtime(runner)

    with pytest.raises(TimeoutError, match="timed out"):
        runtime.execute(_context(), "while (true) {}", timeout_seconds=0.05)
    with pytest.raises(ValueError, match="timeout_seconds"):
        runtime.execute(
            _context(),
            "return null;",
            timeout_seconds=runtime.max_wall_seconds + 1,
        )


def test_workflow_rejects_invalid_script_before_child_dispatch() -> None:
    runner = FakeChildRunner()
    with pytest.raises(RuntimeError, match="workflow script failed"):
        _runtime(runner).execute(_context(), "return (")
    assert runner.calls == []
