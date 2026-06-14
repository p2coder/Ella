from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from devices.factory import DeviceFactory
from events.microphone_source import MicrophoneSource
from events.source import CLITextSignalSource
from memory import MemoryManager
from providers.factory import ProviderFactory
from runtime.event_runtime import EventRuntime
from runtime.task_runtime import TaskRuntime
from sessions import CapabilityExecutor, SubAgent, TaskSessionManager
from sessions.output import UserVisibleAgentOutput
from skill import SkillLoader, SkillManager
from tools import (
    MockChecklistTool,
    MockVisionSummaryTool,
    MockWeatherTool,
    ToolManager,
    ToolResult,
)
from tools.camera_scene import CameraSceneTool


DEFAULT_INPUT = "Ella，看看当前画面，我要出门了"
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
        provider_factory = ProviderFactory()
        device_factory = DeviceFactory()
        llm_provider = provider_factory.llm()
        multimodal_factory = getattr(provider_factory, "multimodal", None)
        multimodal_provider = (
            multimodal_factory()
            if multimodal_factory is not None
            else CameraSceneTool().multimodal_provider
        )
        camera_provider = device_factory.camera()
        skill_manager = SkillManager(
            loader=SkillLoader(PROJECT_ROOT / "skill" / "skills")
        )
        skill_manager.refresh()

        tool_manager = ToolManager()
        tool_manager.register(
            CameraSceneTool(
                camera_provider=camera_provider,
                multimodal_provider=multimodal_provider,
            )
        )
        tool_manager.register(MockVisionSummaryTool())
        tool_manager.register(MockWeatherTool())
        tool_manager.register(MockChecklistTool())

        subagent = SubAgent(skill_manager)
        task_runtime = TaskRuntime(
            session_manager=TaskSessionManager(
                allowed_tools=tool_manager.list_names_for_role("main_agent"),
                skill_manager=skill_manager,
                tool_manager=tool_manager,
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
            llm_provider=llm_provider,
            user_preference_summary=(
                "The user prefers short, practical reminders."
            ),
            environment_summary=(
                "Mock environment context is available. "
                "Give the user a short, necessary reminder before leaving."
            ),
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
            task_result.completion.tool_results,
        )

    def run_input(
        self,
        *,
        mode: str,
        input_text: str = DEFAULT_INPUT,
        microphone_source: MicrophoneSource | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> str:
        normalized_mode = mode.strip().lower()
        if normalized_mode == "text":
            return self.run(input_text)
        if normalized_mode != "microphone":
            raise ValueError("mode must be 'text' or 'microphone'")

        statuses: list[str] = []

        def report(message: str) -> None:
            statuses.append(message)
            if status_callback is not None:
                status_callback(message)

        report("Listening...")
        active_source = microphone_source or MicrophoneSource.from_factories()
        source_result = active_source.capture_transcript(
            trace_id="trace-cli-microphone"
        )
        if source_result.error is not None or source_result.raw_signal is None:
            reason = source_result.error or "microphone input was unavailable"
            message = f"Microphone input failed: {reason}"
            report(message)
            return "\n".join((*statuses, "Text input remains available."))

        report("Transcription complete.")
        event_result = self.event_runtime.publish(source_result.raw_signal)
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

        rendered = _render_output(
            task_result.completion.user_visible_output,
            task_result.memory_result.memory_path,
            task_result.completion.tool_results,
        )
        return "[Input]\n" + "\n".join(statuses) + "\n\n" + rendered


def run_demo(
    input_text: str = DEFAULT_INPUT,
    memory_path: Path = DEFAULT_MEMORY_PATH,
    runtime: DemoRuntime | None = None,
) -> str:
    active_runtime = runtime or DemoRuntime.create_default(memory_path)
    return active_runtime.run(input_text)


def _render_output(
    output: UserVisibleAgentOutput,
    memory_path: Path,
    tool_results: tuple[ToolResult, ...] = (),
) -> str:
    process_values = [str(value) for value in output.process.values()]
    process_values.extend(
        f"Visual context: {result.payload['summary']}"
        for result in tool_results
        if result.tool_name == "camera_scene" and "summary" in result.payload
    )
    process_lines = "\n".join(process_values)
    return (
        "[Ella Process]\n"
        f"{process_lines}\n\n"
        "[Final Answer]\n"
        f"{output.final_response}\n\n"
        "[Memory]\n"
        f"Recorded task memory at {memory_path}"
    )
