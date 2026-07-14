from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from agent.final_response import FinalResponseGenerator
from config.settings import load_settings
from devices.factory import DeviceFactory
from demo.display_snapshot import (
    CAMERA_FRAME,
    CAMERA_UNAVAILABLE,
    MOCK_IMAGE,
    TEXT_ONLY,
    RunDisplaySnapshot,
)
from demo.page_viewer import LocalPageViewer
from events.microphone_source import MicrophoneSource
from events.source import CLITextSignalSource
from memory import MemoryManager
from prompts.engine import PromptEngine
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
from tools.screen_scene import ScreenSceneTool


DEFAULT_INPUT = "Ella，看看当前画面，我要出门了"
DEFAULT_MEMORY_PATH = Path("/tmp/ella-runtime-mvp-memory.md")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_DEMO_STEPS = 20


@dataclass(frozen=True, slots=True)
class DemoDisplayResult:
    output: str
    snapshot: RunDisplaySnapshot
    page_path: Path | None = None


@dataclass(frozen=True, slots=True)
class DemoRuntime:
    event_runtime: EventRuntime
    task_runtime: TaskRuntime
    page_viewer: LocalPageViewer = field(default_factory=LocalPageViewer)

    @classmethod
    def create_default(
        cls,
        memory_path: Path = DEFAULT_MEMORY_PATH,
    ) -> "DemoRuntime":
        settings = load_settings()
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
        screen_factory = getattr(device_factory, "screen", None)
        screen_provider = (
            screen_factory()
            if screen_factory is not None
            else ScreenSceneTool().screen_provider
        )
        skill_manager = SkillManager(
            loader=SkillLoader(PROJECT_ROOT / "skill" / "skills")
        )
        skill_manager.refresh()

        tool_manager = ToolManager()
        tool_manager.register(
            CameraSceneTool(
                camera_provider=camera_provider,
                multimodal_provider=multimodal_provider,
                store_raw_media=settings.debug_store_raw_media,
            )
        )
        tool_manager.register(
            ScreenSceneTool(
                screen_provider=screen_provider,
                multimodal_provider=multimodal_provider,
                store_raw_media=settings.debug_store_raw_media,
            )
        )
        tool_manager.register(MockVisionSummaryTool())
        tool_manager.register(MockWeatherTool())
        tool_manager.register(MockChecklistTool())

        subagent = SubAgent(
            skill_manager,
            tool_directory=tool_manager,
            llm_provider=llm_provider,
        )
        final_response_generator = FinalResponseGenerator(
            prompt_engine=PromptEngine(),
            llm_provider=llm_provider,
        )
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
            final_response_generator=final_response_generator,
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

    def run_with_display(
        self,
        input_text: str,
        *,
        page_path: Path | None = None,
    ) -> DemoDisplayResult:
        signal = CLITextSignalSource().create_signal(
            text=input_text,
            trace_id="trace-cli-demo",
        )
        task_result = self._run_signal_to_completion(signal)
        output = _render_output(
            task_result.completion.user_visible_output,
            task_result.memory_result.memory_path,
            task_result.completion.tool_results,
        )
        snapshot = _build_display_snapshot(
            user_input=input_text,
            transcript=None,
            task_result=task_result,
        )
        written_path = (
            self.page_viewer.write_snapshot(snapshot, page_path)
            if page_path is not None
            else None
        )
        return DemoDisplayResult(
            output=output,
            snapshot=snapshot,
            page_path=written_path,
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

    def run_input_with_display(
        self,
        *,
        mode: str,
        input_text: str = DEFAULT_INPUT,
        microphone_source: MicrophoneSource | None = None,
        status_callback: Callable[[str], None] | None = None,
        page_path: Path | None = None,
    ) -> DemoDisplayResult:
        normalized_mode = mode.strip().lower()
        if normalized_mode == "text":
            return self.run_with_display(input_text, page_path=page_path)
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
            fallback_output = "\n".join((*statuses, "Text input remains available."))
            snapshot = RunDisplaySnapshot(
                user_input="",
                transcript=None,
                captured_frame_reference=None,
                image_status=TEXT_ONLY,
                scene_summary="",
                visible_items=(),
                task_goal="",
                task_formulation_prompt_text="",
                final_response_prompt_text="",
                tool_results_summary="",
                final_response=fallback_output,
                memory_status="not recorded",
            )
            return DemoDisplayResult(output=fallback_output, snapshot=snapshot)

        report("Transcription complete.")
        transcript = str(source_result.raw_signal.payload.get("text", ""))
        task_result = self._run_signal_to_completion(source_result.raw_signal)
        rendered = _render_output(
            task_result.completion.user_visible_output,
            task_result.memory_result.memory_path,
            task_result.completion.tool_results,
        )
        output = "[Input]\n" + "\n".join(statuses) + "\n\n" + rendered
        snapshot = _build_display_snapshot(
            user_input=transcript,
            transcript=transcript,
            task_result=task_result,
        )
        written_path = (
            self.page_viewer.write_snapshot(snapshot, page_path)
            if page_path is not None
            else None
        )
        return DemoDisplayResult(
            output=output,
            snapshot=snapshot,
            page_path=written_path,
        )

    def _run_signal_to_completion(self, signal):
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
        return task_result


def run_demo(
    input_text: str = DEFAULT_INPUT,
    memory_path: Path = DEFAULT_MEMORY_PATH,
    runtime: DemoRuntime | None = None,
) -> str:
    if runtime is not None:
        return runtime.run(input_text)

    from demo.app_runtime import AppRuntime

    result = AppRuntime.create_default(memory_path).run_text_with_display(input_text)
    return result.output


def _render_output(
    output: UserVisibleAgentOutput,
    memory_path: Path,
    tool_results: tuple[ToolResult, ...] = (),
) -> str:
    process_values = [str(value) for value in output.process.values()]
    process_values.extend(
        f"Visual context: {result.payload['summary']}"
        for result in tool_results
        if result.tool_name in {"camera_scene", "screen_scene"}
        and "summary" in result.payload
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


def _build_display_snapshot(
    *,
    user_input: str,
    transcript: str | None,
    task_result,
) -> RunDisplaySnapshot:
    completion = task_result.completion
    output = completion.user_visible_output
    tool_results = completion.tool_results
    camera_result = _find_tool_result(tool_results, "camera_scene")
    screen_result = _find_tool_result(tool_results, "screen_scene")
    visual_result = camera_result or screen_result
    process = output.process
    return RunDisplaySnapshot(
        user_input=user_input,
        transcript=transcript,
        captured_frame_reference=_captured_frame_reference(visual_result),
        image_status=_image_status(tool_results, visual_result),
        scene_summary=_scene_summary(visual_result),
        visible_items=_visible_items(visual_result),
        task_goal=str(process.get("task_goal", "")),
        task_formulation_prompt_text=str(
            process.get("task_formulation_prompt_text", "")
        ),
        strategy_selection_prompt_text=str(
            process.get("strategy_selection_prompt_text", "")
        ),
        execution_decision_prompt_text=str(
            process.get("execution_decision_prompt_text", "")
        ),
        final_response_prompt_text=str(process.get("final_response_prompt_text", "")),
        tool_results_summary=_tool_results_summary(tool_results),
        final_response=output.final_response,
        memory_status=getattr(task_result.memory_result, "action", "unknown"),
    )


def _find_tool_result(
    tool_results: tuple[ToolResult, ...],
    tool_name: str,
) -> ToolResult | None:
    for result in tool_results:
        if result.tool_name == tool_name:
            return result
    return None


def _image_status(
    tool_results: tuple[ToolResult, ...],
    visual_result: ToolResult | None,
) -> str:
    if visual_result is not None:
        payload = visual_result.payload
        if payload.get("available") is False:
            return CAMERA_UNAVAILABLE
        summary = payload.get("summary") or payload.get("scene_summary")
        if isinstance(summary, str) and "unavailable" in summary.lower():
            return CAMERA_UNAVAILABLE
        return CAMERA_FRAME
    if any(result.tool_name == "mock_vision_summary" for result in tool_results):
        return MOCK_IMAGE
    return TEXT_ONLY


def _captured_frame_reference(visual_result: ToolResult | None) -> str | None:
    if visual_result is None:
        return None
    payload = visual_result.payload
    value = payload.get("captured_frame_reference") or payload.get(
        "frame_reference"
    )
    return value if isinstance(value, str) else None


def _scene_summary(visual_result: ToolResult | None) -> str:
    if visual_result is None:
        return ""
    payload = visual_result.payload
    value = payload.get("scene_summary") or payload.get("summary")
    return value if isinstance(value, str) else ""


def _visible_items(visual_result: ToolResult | None) -> tuple[str, ...]:
    if visual_result is None:
        return ()
    value = visual_result.payload.get("visible_items")
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ()


def _tool_results_summary(tool_results: tuple[ToolResult, ...]) -> str:
    summaries = []
    for result in tool_results:
        lines = [f"{result.tool_name}:"]
        for key in sorted(result.payload):
            value = result.payload[key]
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                value_text = ", ".join(str(item) for item in value)
            else:
                value_text = str(value)
            lines.append(f"- {key}: {value_text}")
        summaries.append("\n".join(lines))
    return "\n\n".join(summaries)
