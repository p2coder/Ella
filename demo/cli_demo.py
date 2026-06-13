from pathlib import Path

from agent import MainAgent
from agent.context import AgentExecutionContext
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
from tools import MockChecklistTool, MockVisionSummaryTool, MockWeatherTool, ToolResult


DEFAULT_INPUT = "Ella，我要出门了"
DEFAULT_MEMORY_PATH = Path("/tmp/ella-runtime-mvp-memory.md")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_demo(
    input_text: str = DEFAULT_INPUT,
    memory_path: Path = DEFAULT_MEMORY_PATH,
) -> str:
    signal = CLITextSignalSource().create_signal(
        text=input_text,
        trace_id="trace-cli-demo",
    )
    event = EventTriggerPipeline(
        stages=(CliTextToStandardizedEventStage(),),
    ).run(signal)
    if not isinstance(event, StandardizedEvent):
        raise RuntimeError("trigger pipeline did not produce a standardized event")

    route = SessionAwareEventRouter().route(event)
    if route.destination != PRESENCE_QUEUE:
        raise RuntimeError(f"demo event was routed to {route.destination.name}")

    presence_queue = PresenceQueue()
    presence_queue.enqueue(event)
    allowed_events: list[StandardizedEvent] = []
    runtime_result = PresenceRuntime(
        presence_queue=presence_queue,
        next_boundary=allowed_events.append,
    ).process_available()
    if runtime_result.allowed_count != 1 or len(allowed_events) != 1:
        raise RuntimeError("presence runtime did not allow the demo event")

    handoff = MainAgent().create_handoff(
        trigger_event=allowed_events[0],
        user_preference_summary="The user prefers short, practical reminders.",
        environment_summary="Mock environment context is available.",
    )
    session_creation = TaskSessionManager(
        allowed_tools=(
            "mock_vision_summary",
            "mock_weather",
            "mock_checklist",
        ),
        session_id_factory=lambda: "session-cli-demo",
        task_id_factory=lambda: "task-cli-demo",
    ).create_session(handoff)

    skill_loader = SkillLoader(PROJECT_ROOT / "skill" / "skills")
    skill_registry = SkillRegistry()
    skill_registry.register_all(skill_loader.discover_summaries())
    strategy = SubAgent(skill_registry).select_strategy(
        handoff=handoff,
        context=session_creation.context,
        task_session=session_creation.session,
    )
    if strategy.skill_name != "going_out":
        raise RuntimeError("going_out skill was not selected for the demo task")
    skill_loader.load_full(strategy.skill_name)

    tool_registry = ToolRegistry()
    tool_registry.register(MockVisionSummaryTool())
    tool_registry.register(MockWeatherTool())
    tool_registry.register(MockChecklistTool())
    tool_results = _run_mock_tools(tool_registry, session_creation.context)

    output = UserVisibleAgentOutput(
        process={
            "understanding": "I understood that the user is preparing to go out.",
            "strategy": "I selected the going_out skill.",
            "context": (
                "I checked the mock context and prepared a short reminder."
            ),
        },
        final_response=(
            "Before you leave, remember your keys, phone, and wallet. "
            "Light rain is possible, so consider taking an umbrella."
        ),
    )
    completion = TaskCompletionPackage(
        context=session_creation.context,
        summary="Prepared going-out reminder with mock tools.",
        user_visible_output=output,
        tool_results=tool_results,
    )
    memory_result = MemoryManager(memory_path).handle(
        MemoryManagementRequest.from_completion(completion)
    )

    return _render_output(output, memory_result.memory_path)


def _run_mock_tools(
    tool_registry: ToolRegistry,
    context: AgentExecutionContext,
) -> tuple[ToolResult, ...]:
    results = []
    for tool_name in context.allowed_tools:
        tool = tool_registry.get(tool_name)
        if tool is None:
            raise RuntimeError(f"required mock tool is not registered: {tool_name}")
        results.append(tool.run(context))
    return tuple(results)


def _render_output(output: UserVisibleAgentOutput, memory_path: Path) -> str:
    process_lines = "\n".join(str(value) for value in output.process.values())
    return (
        "[Ella Process]\n"
        f"{process_lines}\n\n"
        "[Final Answer]\n"
        f"{output.final_response}\n\n"
        "[Memory]\n"
        f"Recorded task memory at {memory_path}"
    )
