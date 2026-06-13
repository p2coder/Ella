from dataclasses import dataclass
from pathlib import Path

from agent import MainAgent
from events import StandardizedEvent
from events.source import CLITextSignalSource
from events.trigger_pipeline import (
    CliTextToStandardizedEventStage,
    EventTriggerPipeline,
)
from memory import MemoryManagementRequest, MemoryManager
from runtime.event_queue import PresenceQueue
from runtime.event_router import PRESENCE_QUEUE, SessionAwareEventRouter
from runtime.presence_runtime import PresenceRuntime
from sessions import CapabilityExecutor, SubAgent, TaskSessionManager
from sessions.completion import TaskCompletionPackage
from sessions.output import UserVisibleAgentOutput
from skill import SkillLoader, SkillManager
from tools import MockChecklistTool, MockVisionSummaryTool, MockWeatherTool, ToolManager


DEFAULT_INPUT = "Ella，我要出门了"
DEFAULT_MEMORY_PATH = Path("/tmp/ella-runtime-mvp-memory.md")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class DemoRuntime:
    skill_manager: SkillManager
    tool_manager: ToolManager
    subagent: SubAgent
    executor: CapabilityExecutor

    @classmethod
    def create_default(cls) -> "DemoRuntime":
        skill_manager = SkillManager(
            loader=SkillLoader(PROJECT_ROOT / "skill" / "skills")
        )
        skill_manager.refresh()

        tool_manager = ToolManager()
        tool_manager.register(MockVisionSummaryTool())
        tool_manager.register(MockWeatherTool())
        tool_manager.register(MockChecklistTool())

        subagent = SubAgent(skill_manager)
        return cls(
            skill_manager=skill_manager,
            tool_manager=tool_manager,
            subagent=subagent,
            executor=CapabilityExecutor(
                subagent=subagent,
                skill_manager=skill_manager,
                tool_manager=tool_manager,
            ),
        )

    def run(self, input_text: str, memory_path: Path) -> str:
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

        strategy = self.subagent.select_strategy(
            handoff=handoff,
            context=session_creation.context,
            task_session=session_creation.session,
        )
        execution = self.executor.execute(
            strategy=strategy,
            handoff=handoff,
            context=session_creation.context,
            task_session=session_creation.session,
        )
        if execution.strategy.skill_name != "going_out":
            raise RuntimeError("going_out skill was not selected for the demo task")
        if execution.unavailable_tools:
            unavailable = ", ".join(execution.unavailable_tools)
            raise RuntimeError(f"demo tools became unavailable: {unavailable}")

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
            tool_results=execution.tool_results,
        )
        memory_result = MemoryManager(memory_path).handle(
            MemoryManagementRequest.from_completion(completion)
        )

        return _render_output(output, memory_result.memory_path)


DEFAULT_DEMO_RUNTIME = DemoRuntime.create_default()


def run_demo(
    input_text: str = DEFAULT_INPUT,
    memory_path: Path = DEFAULT_MEMORY_PATH,
    runtime: DemoRuntime = DEFAULT_DEMO_RUNTIME,
) -> str:
    return runtime.run(input_text, memory_path)


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
