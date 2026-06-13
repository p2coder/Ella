import inspect
from datetime import datetime, timezone
from pathlib import Path

from demo.cli_demo import DemoRuntime
from events.source import CLITextSignalSource
from memory import MemoryManager
from runtime.event_runtime import EventRuntime
from runtime.task_runtime import TaskRuntime
from sessions import CapabilityExecutor, SubAgent, TaskSessionManager, TaskState
from sessions.completion import TaskCompletionPackage
from skill import SkillLoader, SkillManager
from tools import (
    MockChecklistTool,
    MockVisionSummaryTool,
    MockWeatherTool,
    ToolManager,
)


FIXED_TIME = datetime(2026, 6, 13, 14, 0, tzinfo=timezone.utc)


def make_application_runtime(
    memory_path: Path,
    *,
    session_ids: tuple[str, ...] = ("session-contract",),
    task_ids: tuple[str, ...] = ("task-contract",),
):
    skill_manager = SkillManager(loader=SkillLoader())
    skill_manager.refresh()

    tool_manager = ToolManager()
    tool_manager.register(MockVisionSummaryTool())
    tool_manager.register(MockWeatherTool())
    tool_manager.register(MockChecklistTool())

    session_id_values = iter(session_ids)
    task_id_values = iter(task_ids)
    subagent = SubAgent(skill_manager)
    task_runtime = TaskRuntime(
        session_manager=TaskSessionManager(
            allowed_tools=(
                "mock_vision_summary",
                "mock_weather",
                "mock_checklist",
            ),
            session_id_factory=lambda: next(session_id_values),
            task_id_factory=lambda: next(task_id_values),
        ),
        subagent=subagent,
        executor=CapabilityExecutor(
            subagent=subagent,
            skill_manager=skill_manager,
            tool_manager=tool_manager,
        ),
        memory_manager=MemoryManager(memory_path),
    )
    event_runtime = EventRuntime(
        task_runtime=task_runtime,
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Mock environment only.",
    )
    return event_runtime, task_runtime, skill_manager, tool_manager


def make_signal(trace_id: str):
    return CLITextSignalSource().create_signal(
        text="Ella，我要出门了",
        trace_id=trace_id,
        timestamp=FIXED_TIME,
    )


def test_event_runtime_is_raw_signal_entrypoint_and_task_runtime_orchestrates(
    tmp_path: Path,
):
    event_runtime, task_runtime, _, _ = make_application_runtime(
        tmp_path / "memory.md"
    )

    publication = event_runtime.publish(make_signal("trace-contract"))

    assert publication.submitted is True
    assert publication.task_handle is not None
    assert publication.task_handle.task_id == "task-contract"
    session = task_runtime.get_session(publication.task_handle.task_id)
    context = task_runtime.get_context(publication.task_handle.task_id)
    assert session.state is TaskState.CREATED
    assert session.handoff.trigger_event is publication.event
    assert context.trace_id == "trace-contract"

    task_runtime.step(publication.task_handle.task_id)
    assert session.state is TaskState.PLANNING
    task_runtime.step(publication.task_handle.task_id)
    assert session.state is TaskState.RUNNING
    assert session.current_strategy.skill_name == "going_out"


def test_task_runtime_generates_completion_and_is_memory_path(tmp_path: Path):
    memory_path = tmp_path / "memory.md"
    event_runtime, task_runtime, _, _ = make_application_runtime(memory_path)
    publication = event_runtime.publish(make_signal("trace-completion-contract"))
    assert publication.task_handle is not None

    result = task_runtime.run_until_complete(
        publication.task_handle.task_id,
        max_steps=20,
    )

    assert result.session.state is TaskState.COMPLETED
    assert isinstance(result.completion, TaskCompletionPackage)
    assert result.completion.context is result.context
    assert tuple(item.tool_name for item in result.completion.tool_results) == (
        "mock_vision_summary",
        "mock_weather",
        "mock_checklist",
    )
    assert result.memory_result is not None
    assert result.memory_result.memory_path == memory_path
    memory_text = memory_path.read_text(encoding="utf-8")
    assert publication.task_handle.task_id in memory_text
    assert "trace-completion-contract" in memory_text


def test_task_runtime_observes_skill_and_tool_hot_plug_during_current_session(
    tmp_path: Path,
):
    event_runtime, task_runtime, skill_manager, tool_manager = (
        make_application_runtime(tmp_path / "memory.md")
    )
    publication = event_runtime.publish(make_signal("trace-hot-plug-contract"))
    assert publication.task_handle is not None
    task_id = publication.task_handle.task_id

    task_runtime.step(task_id)
    task_runtime.step(task_id)
    session = task_runtime.get_session(task_id)
    assert session.current_strategy.skill_name == "going_out"

    tool_manager.unregister("mock_vision_summary")
    task_runtime.step(task_id)
    assert session.state is TaskState.REPLANNING

    tool_manager.register(MockVisionSummaryTool())
    skill_manager.unregister("going_out")
    task_runtime.step(task_id)
    assert session.state is TaskState.RUNNING
    assert session.current_strategy.skill_name == "going_out"

    task_runtime.step(task_id)
    assert session.tool_trace[0]["tool_name"] == "mock_vision_summary"


def test_each_submitted_task_has_isolated_session_context_and_local_data(
    tmp_path: Path,
):
    event_runtime, task_runtime, _, _ = make_application_runtime(
        tmp_path / "memory.md",
        session_ids=("session-a", "session-b"),
        task_ids=("task-a", "task-b"),
    )
    first = event_runtime.publish(make_signal("trace-a"))
    second = event_runtime.publish(make_signal("trace-b"))
    assert first.task_handle is not None
    assert second.task_handle is not None

    first_session = task_runtime.get_session(first.task_handle.task_id)
    second_session = task_runtime.get_session(second.task_handle.task_id)
    first_context = task_runtime.get_context(first.task_handle.task_id)
    second_context = task_runtime.get_context(second.task_handle.task_id)

    first_session.set_task_state("owner", "first")
    first_session.message_history = ({"role": "user", "content": "first"},)
    first_session.tool_trace = ({"tool_name": "first_tool"},)

    assert first_session is not second_session
    assert first_context is not second_context
    assert first_context.task_id == "task-a"
    assert second_context.task_id == "task-b"
    assert second_session.task_local_state == {}
    assert second_session.message_history == ()
    assert second_session.tool_trace == ()


def test_demo_uses_runtime_entrypoints_without_internal_orchestration():
    run_source = inspect.getsource(DemoRuntime.run)

    assert ".publish(" in run_source
    assert ".run_until_complete(" in run_source
    for forbidden in (
        "TaskSessionManager",
        "create_session",
        "select_strategy",
        "CapabilityExecutor",
        ".execute(",
        "ToolManager",
        "MemoryManager",
        ".handle(",
    ):
        assert forbidden not in run_source
