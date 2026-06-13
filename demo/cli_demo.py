from dataclasses import dataclass
from pathlib import Path

from events.source import CLITextSignalSource
from memory import MemoryManager
from runtime.event_runtime import EventRuntime
from runtime.task_runtime import TaskRuntime
from sessions import CapabilityExecutor, SubAgent, TaskSessionManager
from sessions.output import UserVisibleAgentOutput
from skill import SkillLoader, SkillManager
from tools import MockChecklistTool, MockVisionSummaryTool, MockWeatherTool, ToolManager


DEFAULT_INPUT = "Ella，我要出门了"
DEFAULT_MEMORY_PATH = Path("/tmp/ella-runtime-mvp-memory.md")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_DEMO_STEPS = 20


@dataclass(frozen=True, slots=True)
class DemoRuntime:
    event_runtime: EventRuntime
    task_runtime: TaskRuntime

    @classmethod
    def create_default(
        cls,
        memory_path: Path = DEFAULT_MEMORY_PATH,
    ) -> "DemoRuntime":
        skill_manager = SkillManager(
            loader=SkillLoader(PROJECT_ROOT / "skill" / "skills")
        )
        skill_manager.refresh()

        tool_manager = ToolManager()
        tool_manager.register(MockVisionSummaryTool())
        tool_manager.register(MockWeatherTool())
        tool_manager.register(MockChecklistTool())

        subagent = SubAgent(skill_manager)
        task_runtime = TaskRuntime(
            session_manager=TaskSessionManager(
                allowed_tools=(
                    "mock_vision_summary",
                    "mock_weather",
                    "mock_checklist",
                ),
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
            user_preference_summary=(
                "The user prefers short, practical reminders."
            ),
            environment_summary="Mock environment context is available.",
        )
        return cls(
            event_runtime=event_runtime,
            task_runtime=task_runtime,
        )

    def run(self, input_text: str) -> str:
        signal = CLITextSignalSource().create_signal(
            text=input_text,
            trace_id="trace-cli-demo",
        )
        event_result = self.event_runtime.publish(signal)
        if not event_result.submitted or event_result.task_handle is None:
            raise RuntimeError(event_result.reason)

        task_result = self.task_runtime.run_until_complete(
            event_result.task_handle.task_id,
            max_steps=MAX_DEMO_STEPS,
        )
        if task_result.failure_reason is not None:
            raise RuntimeError(task_result.failure_reason)
        if task_result.completion is None:
            raise RuntimeError(
                f"demo task did not complete: {task_result.stop_reason}"
            )
        if task_result.memory_result is None:
            raise RuntimeError("demo task completed without a memory result")

        return _render_output(
            task_result.completion.user_visible_output,
            task_result.memory_result.memory_path,
        )


def run_demo(
    input_text: str = DEFAULT_INPUT,
    memory_path: Path = DEFAULT_MEMORY_PATH,
    runtime: DemoRuntime | None = None,
) -> str:
    active_runtime = runtime or DemoRuntime.create_default(memory_path)
    return active_runtime.run(input_text)


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
