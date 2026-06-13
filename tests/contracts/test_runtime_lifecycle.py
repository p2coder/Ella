from datetime import datetime, timezone
from pathlib import Path

from agent import MainAgent
from events import StandardizedEvent
from events.source import CLITextSignalSource
from events.trigger_pipeline import (
    CliTextToStandardizedEventStage,
    EventTriggerPipeline,
)
from memory import MemoryManagementRequest, MemoryManager
from registries.tool_registry import ToolRegistry
from runtime.event_queue import PresenceQueue
from runtime.event_router import PRESENCE_QUEUE, SessionAwareEventRouter
from runtime.presence_runtime import PresenceRuntime
from sessions import SubAgent, TaskSessionManager
from sessions.completion import TaskCompletionPackage
from sessions.output import UserVisibleAgentOutput
from skill import SkillLoader, SkillRegistry
from tools import MockChecklistTool, MockWeatherTool


FIXED_TIME = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def test_going_out_event_reaches_memory_through_runtime_boundaries(tmp_path: Path):
    signal = CLITextSignalSource().create_signal(
        text="Ella，我要出门了",
        trace_id="trace-contract",
        timestamp=FIXED_TIME,
    )
    event = EventTriggerPipeline(
        stages=(CliTextToStandardizedEventStage(),),
    ).run(signal)

    assert isinstance(event, StandardizedEvent)
    route = SessionAwareEventRouter().route(event)
    assert route.destination == PRESENCE_QUEUE

    queue = PresenceQueue()
    queue.enqueue(route.event)
    allowed_events = []
    runtime_result = PresenceRuntime(
        presence_queue=queue,
        next_boundary=allowed_events.append,
    ).process_available()

    assert runtime_result.allowed_count == 1
    assert allowed_events == [event]

    handoff = MainAgent().create_handoff(
        trigger_event=allowed_events[0],
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Mock environment context only.",
    )
    creation = TaskSessionManager(
        allowed_tools=("mock_weather", "mock_checklist"),
        session_id_factory=lambda: "session-contract",
        task_id_factory=lambda: "task-contract",
    ).create_session(handoff)

    skill_loader = SkillLoader()
    skill_registry = SkillRegistry()
    skill_registry.register_all(skill_loader.discover_summaries())
    strategy = SubAgent(skill_registry).select_strategy(
        handoff=handoff,
        context=creation.context,
        task_session=creation.session,
    )

    assert strategy.mode == "skill"
    assert strategy.skill_name == "going_out"
    assert skill_loader.load_full("going_out").content is not None

    tool_registry = ToolRegistry()
    tool_registry.register(MockWeatherTool())
    tool_registry.register(MockChecklistTool())
    tool_results = tuple(
        tool_registry.get(name).run(creation.context)
        for name in creation.context.allowed_tools
    )
    output = UserVisibleAgentOutput(
        process={"strategy": strategy.skill_name},
        final_response="Take your keys and phone. Consider an umbrella.",
    )
    completion = TaskCompletionPackage(
        context=creation.context,
        summary="Prepared going-out reminder with mock tools.",
        user_visible_output=output,
        tool_results=tool_results,
    )
    request = MemoryManagementRequest.from_completion(completion)
    memory_path = tmp_path / "memory.md"
    write_result = MemoryManager(memory_path).handle(request)

    assert write_result.action == "appended"
    assert write_result.memory_path == memory_path
    memory_text = memory_path.read_text(encoding="utf-8")
    assert "## Task task-contract" in memory_text
    assert "- session_id: session-contract" in memory_text
    assert "- trace_id: trace-contract" in memory_text
    assert output.final_response in memory_text


def test_runtime_contract_uses_only_local_mock_tools():
    tools = (MockWeatherTool(), MockChecklistTool())

    assert tuple(tool.name for tool in tools) == (
        "mock_weather",
        "mock_checklist",
    )
    for tool in tools:
        assert not hasattr(tool, "api_key")
        assert not hasattr(tool, "http_client")
