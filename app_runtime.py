from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

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
from events.source import CLITextSignalSource
from memory import MemoryManager
from prompts.engine import PromptEngine
from providers.factory import ProviderFactory
from runtime.event_runtime import EventRuntime
from runtime.task_runtime import TaskRuntime, TaskRuntimeResult
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


DEFAULT_MEMORY_PATH = Path("/tmp/ella-runtime-memory.md")
PROJECT_ROOT = Path(__file__).resolve().parent
MAX_APP_STEPS = 20


@dataclass(frozen=True, slots=True)
class AppDisplayResult:
    output: str
    snapshot: RunDisplaySnapshot
    page_path: Path | None = None


@dataclass(frozen=True, slots=True)
class AppRuntime:
    _event_runtime: EventRuntime
    _task_runtime: TaskRuntime
    _page_viewer: LocalPageViewer = field(default_factory=LocalPageViewer)

    @classmethod
    def create_default(
        cls,
        memory_path: Path = DEFAULT_MEMORY_PATH,
    ) -> "AppRuntime":
        settings = load_settings()
        provider_factory = ProviderFactory()
        device_factory = DeviceFactory()
        llm_provider = provider_factory.llm()
        multimodal_provider = provider_factory.multimodal()
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
        task_runtime = TaskRuntime(
            session_manager=TaskSessionManager(
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
            final_response_generator=FinalResponseGenerator(
                prompt_engine=PromptEngine(),
                llm_provider=llm_provider,
            ),
        )
        event_runtime = EventRuntime(
            task_runtime=task_runtime,
            llm_provider=llm_provider,
        )
        return cls(event_runtime, task_runtime)

    def run_text_with_display(self, input_text: str) -> AppDisplayResult:
        signal = CLITextSignalSource().create_signal(
            text=input_text,
            trace_id=f"trace-web-{uuid4().hex}",
        )
        task_result = self._run_signal_to_completion(signal)
        completion = task_result.completion
        memory_result = task_result.memory_result
        output = _render_output(
            completion.user_visible_output,
            memory_result.memory_path,
            completion.tool_results,
        )
        return AppDisplayResult(
            output=output,
            snapshot=_build_display_snapshot(input_text, task_result),
        )

    def _run_signal_to_completion(self, signal) -> TaskRuntimeResult:
        event_result = self._event_runtime.publish(signal)
        if not event_result.submitted or event_result.task_handle is None:
            raise RuntimeError(event_result.reason)

        task_result = self._task_runtime.run_until_complete(
            event_result.task_handle.task_id,
            max_steps=MAX_APP_STEPS,
        )
        if task_result.failure_reason is not None:
            raise RuntimeError(task_result.failure_reason)
        if task_result.completion is None:
            raise RuntimeError(
                f"task did not complete: {task_result.stop_reason}"
            )
        if task_result.memory_result is None:
            raise RuntimeError("task completed without a memory result")
        return task_result


def _render_output(
    output: UserVisibleAgentOutput,
    memory_path: Path,
    tool_results: tuple[ToolResult, ...],
) -> str:
    process_values = [str(value) for value in output.process.values()]
    process_values.extend(
        f"Visual context: {result.payload['summary']}"
        for result in tool_results
        if result.tool_name == "camera_scene" and "summary" in result.payload
    )
    return (
        "[Ella Process]\n"
        f"{'\n'.join(process_values)}\n\n"
        "[Final Answer]\n"
        f"{output.final_response}\n\n"
        "[Memory]\n"
        f"Recorded task memory at {memory_path}"
    )


def _build_display_snapshot(
    user_input: str,
    task_result: TaskRuntimeResult,
) -> RunDisplaySnapshot:
    completion = task_result.completion
    output = completion.user_visible_output
    tool_results = completion.tool_results
    camera_result = _find_tool_result(tool_results, "camera_scene")
    process = output.process
    return RunDisplaySnapshot(
        user_input=user_input,
        transcript=None,
        captured_frame_reference=_captured_frame_reference(camera_result),
        image_status=_image_status(tool_results, camera_result),
        scene_summary=_scene_summary(camera_result),
        visible_items=_visible_items(camera_result),
        task_goal=str(process.get("task_goal", "")),
        task_formulation_prompt_text=str(
            process.get("task_formulation_prompt_text", "")
        ),
        final_response_prompt_text=str(
            process.get("final_response_prompt_text", "")
        ),
        tool_results_summary=_tool_results_summary(tool_results),
        final_response=output.final_response,
        memory_status=getattr(task_result.memory_result, "action", "unknown"),
    )


def _find_tool_result(
    tool_results: tuple[ToolResult, ...],
    tool_name: str,
) -> ToolResult | None:
    return next(
        (result for result in tool_results if result.tool_name == tool_name),
        None,
    )


def _image_status(
    tool_results: tuple[ToolResult, ...],
    camera_result: ToolResult | None,
) -> str:
    if camera_result is not None:
        payload = camera_result.payload
        if payload.get("available") is False:
            return CAMERA_UNAVAILABLE
        summary = payload.get("summary") or payload.get("scene_summary")
        if isinstance(summary, str) and "unavailable" in summary.lower():
            return CAMERA_UNAVAILABLE
        return CAMERA_FRAME
    if any(result.tool_name == "mock_vision_summary" for result in tool_results):
        return MOCK_IMAGE
    return TEXT_ONLY


def _captured_frame_reference(camera_result: ToolResult | None) -> str | None:
    if camera_result is None:
        return None
    value = camera_result.payload.get("captured_frame_reference") or (
        camera_result.payload.get("frame_reference")
    )
    return value if isinstance(value, str) else None


def _scene_summary(camera_result: ToolResult | None) -> str:
    if camera_result is None:
        return ""
    value = camera_result.payload.get("scene_summary") or camera_result.payload.get(
        "summary"
    )
    return value if isinstance(value, str) else ""


def _visible_items(camera_result: ToolResult | None) -> tuple[str, ...]:
    if camera_result is None:
        return ()
    value = camera_result.payload.get("visible_items")
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ()


def _tool_results_summary(tool_results: tuple[ToolResult, ...]) -> str:
    summaries: list[str] = []
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
