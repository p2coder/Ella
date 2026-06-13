import inspect
from dataclasses import dataclass
from pathlib import Path

from demo.cli_demo import DemoRuntime, run_demo
from memory import MemoryWriteResult
from runtime.event_runtime import EventRuntimeResult
from runtime.task_runtime import TaskHandle
from sessions.completion import TaskCompletionPackage
from sessions.output import UserVisibleAgentOutput


def test_cli_demo_runs_through_runtime_entrypoints_and_prints_sections(
    tmp_path: Path,
):
    memory_path = tmp_path / "memory.md"

    output = run_demo(
        input_text="Ella，我要出门了",
        memory_path=memory_path,
    )

    assert "[Ella Process]" in output
    assert "Give the user a short, necessary reminder before leaving." in output
    assert "going_out" in output
    assert "[Final Answer]" in output
    assert "Task completed:" in output
    assert "[Memory]" in output
    assert str(memory_path) in output


def test_cli_demo_writes_memory_through_task_runtime(tmp_path: Path):
    memory_path = tmp_path / "memory.md"

    run_demo(
        input_text="Ella，我要出门了",
        memory_path=memory_path,
    )

    memory_text = memory_path.read_text(encoding="utf-8")
    assert "## Task " in memory_text
    assert "- session_id: " in memory_text
    assert "- trace_id: trace-cli-demo" in memory_text
    assert "Completed task:" in memory_text


@dataclass
class RecordingEventRuntime:
    task_handle: TaskHandle
    published: list = None

    def __post_init__(self):
        self.published = []

    def publish(self, signal):
        self.published.append(signal)
        return EventRuntimeResult(
            event=None,
            route=None,
            submitted=True,
            task_handle=self.task_handle,
            reason="submitted",
        )


@dataclass
class RecordingTaskRuntime:
    completion: TaskCompletionPackage
    memory_result: MemoryWriteResult
    calls: list = None

    def __post_init__(self):
        self.calls = []

    def run_until_complete(self, task_id, max_steps):
        self.calls.append((task_id, max_steps))
        return StubTaskRuntimeResult(
            completion=self.completion,
            memory_result=self.memory_result,
        )


@dataclass(frozen=True)
class StubTaskRuntimeResult:
    completion: TaskCompletionPackage
    memory_result: MemoryWriteResult
    failure_reason: str | None = None


def test_demo_run_only_publishes_waits_and_renders(tmp_path: Path):
    handle = TaskHandle("task-demo", "session-demo", "trace-demo")
    completion = TaskCompletionPackage(
        context=None,
        summary="Completed through runtime.",
        user_visible_output=UserVisibleAgentOutput(
            process={"status": "Runtime handled the task."},
            final_response="Runtime result.",
        ),
        tool_results=(),
    )
    memory_result = MemoryWriteResult("appended", tmp_path / "memory.md")
    event_runtime = RecordingEventRuntime(handle)
    task_runtime = RecordingTaskRuntime(completion, memory_result)
    runtime = DemoRuntime(
        event_runtime=event_runtime,
        task_runtime=task_runtime,
    )

    output = runtime.run("Ella，我要出门了")

    assert len(event_runtime.published) == 1
    assert event_runtime.published[0].payload == {"text": "Ella，我要出门了"}
    assert task_runtime.calls == [("task-demo", 20)]
    assert "Runtime handled the task." in output
    assert "Runtime result." in output
    assert str(memory_result.memory_path) in output


def test_demo_does_not_orchestrate_internal_lifecycle_components():
    source = inspect.getsource(DemoRuntime.run)

    for forbidden_call in (
        "SessionAwareEventRouter",
        "PresenceQueue",
        "create_handoff",
        "TaskSessionManager",
        "select_strategy",
        "CapabilityExecutor",
        ".execute(",
        "TaskCompletionPackage(",
        "MemoryManager",
        ".handle(",
    ):
        assert forbidden_call not in source


def test_default_demo_runtime_exposes_only_application_runtime_entrypoints(
    tmp_path: Path,
):
    runtime = DemoRuntime.create_default(tmp_path / "memory.md")

    assert hasattr(runtime, "event_runtime")
    assert hasattr(runtime, "task_runtime")
    assert not hasattr(runtime, "subagent")
    assert not hasattr(runtime, "executor")
    assert not hasattr(runtime, "skill_manager")
    assert not hasattr(runtime, "tool_manager")
