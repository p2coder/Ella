from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from agent.final_response import FinalResponseGenerator
from config.config import PROJECT_ROOT
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
from runtime.plan_store import PlanStore
from runtime.task_runtime import TaskRuntime, TaskRuntimeResult
from runtime.timing import RuntimeTimingRecorder
from runtime.trace import TraceRecorder
from tasks.state import (
    TaskControlCommand,
    TaskControlType,
)
from agent.subagent import SubAgent
from runtime.executor import CapabilityExecutor
from tasks.factory import TaskFactory
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
from tools.plan import PlanWrittenTool

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
    microphone_source: MicrophoneSource | None = None

    @classmethod
    def create_default(
        cls,
        memory_path: Path | None = None,
    ) -> "AppRuntime":
        settings = load_settings()
        provider_factory = ProviderFactory()
        device_factory = DeviceFactory()
        llm_provider = provider_factory.llm()
        multimodal_provider = provider_factory.multimodal()
        camera_provider = device_factory.camera()
        timing_recorder = RuntimeTimingRecorder()
        trace_recorder = TraceRecorder.for_directory(settings.trace_directory)

        skill_manager = SkillManager(
            loader=SkillLoader(PROJECT_ROOT / "skill" / "skills")
        )
        skill_manager.refresh()

        tool_manager = ToolManager()
        screen_factory = getattr(device_factory, "screen", None)
        screen_provider = (
            screen_factory()
            if screen_factory is not None
            else ScreenSceneTool().screen_provider
        )

        # tool改成热插拔
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
        plan_store = PlanStore(settings.plan_directory)
        tool_manager.register(PlanWrittenTool(plan_store))


        subagent = SubAgent(
            skill_manager,
            tool_directory=tool_manager,
            llm_provider=llm_provider,
            timing_recorder=timing_recorder,
            trace_recorder=trace_recorder,
        )
        task_runtime = TaskRuntime(
            task_factory=TaskFactory(
                skill_manager=skill_manager,
                tool_manager=tool_manager,
            ),
            subagent=subagent,
            executor=CapabilityExecutor(
                subagent=subagent,
                skill_manager=skill_manager,
                tool_manager=tool_manager,
                timing_recorder=timing_recorder,
            ),
            memory_manager=MemoryManager(memory_path or settings.memory_path),
            final_response_generator=FinalResponseGenerator(
                prompt_engine=PromptEngine(),
                llm_provider=llm_provider,
                timing_recorder=timing_recorder,
            ),
            timing_recorder=timing_recorder,
            trace_recorder=trace_recorder,
        )
        event_runtime = EventRuntime(
            task_runtime=task_runtime,
            llm_provider=llm_provider,
            timing_recorder=timing_recorder,
        )
        microphone_source = MicrophoneSource.from_factories(
            device_factory=device_factory,
            provider_factory=provider_factory,
        )
        return cls(
            event_runtime,
            task_runtime,
            microphone_source=microphone_source,
        )

    def run_text_with_display(self, input_text: str) -> AppDisplayResult:
        signal = CLITextSignalSource().create_signal(
            text=input_text,
            trace_id=f"trace-web-{uuid4().hex}",
        )
        return self._run_signal_with_display(
            signal,
            user_input=input_text,
        )

    def run_submitted_task_with_display(
        self,
        task_id: str,
        *,
        user_input: str,
        transcript: str | None = None,
    ) -> AppDisplayResult:
        task_result = self._task_runtime.run_until_complete(
            task_id,
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
        return self._display_result(
            task_result,
            user_input=user_input,
            transcript=transcript,
        )

    def submit_text(self, input_text: str):
        signal = CLITextSignalSource().create_signal(
            text=input_text,
            trace_id=f"trace-app-{uuid4().hex}",
        )
        result = self._event_runtime.publish(signal)
        if not result.submitted or result.task_handle is None:
            raise RuntimeError(result.reason)
        return result.task_handle

    def get_task(self, task_id: str) -> dict[str, object]:
        creation = self._task_runtime._tasks.get(task_id)
        if creation is None:
            raise KeyError(task_id)
        task = creation.task
        trace = self._task_runtime.trace_recorder.snapshot(task_id)
        return {
            "task_id": task.task_id,
            "state": task.state.value,
            "active_step_ids": task.active_step_ids,
            "waiting_condition": task.waiting_condition,
            "paused_from_state": (
                None if task.paused_from_state is None else task.paused_from_state.value
            ),
            "terminal_outcome": task.terminal_outcome,
            "failure": task.failure,
            "uncertain_resolution": task.uncertain_resolution,
            "delivery": task.delivery,
            "graph": task.graph,
            "trace": None if trace is None else trace.to_dict(),
        }

    def pause(self, task_id: str, reason: str = ""):
        return self._control(task_id, TaskControlType.PAUSE, reason)

    def resume(self, task_id: str, reason: str = ""):
        return self._control(task_id, TaskControlType.RESUME, reason)

    def kill(self, task_id: str, reason: str = ""):
        return self._control(task_id, TaskControlType.KILL, reason)

    def resolve_uncertain_as_failed(self, task_id: str, reason: str):
        self._task_runtime.resolve_uncertain_as_failed(task_id, reason)
        return self.get_task(task_id)

    def _control(self, task_id: str, command_type: TaskControlType, reason: str):
        return self._task_runtime.apply_control(
            TaskControlCommand(
                command_id=f"control-{uuid4().hex}",
                task_id=task_id,
                command_type=command_type,
                requested_at=datetime.now(timezone.utc),
                actor="app_runtime",
                reason=reason or None,
            )
        )

    def run_microphone_with_display(
        self,
        *,
        status_callback: Callable[[str], None] | None = None,
    ) -> AppDisplayResult:
        report_status = status_callback or (lambda _status: None)
        report_status("Listening...")
        source = self.microphone_source or MicrophoneSource.from_factories()
        try:
            source_result = source.capture_transcript(
                trace_id=f"trace-web-microphone-{uuid4().hex}",
            )
        except Exception:
            return _microphone_failure_result(
                "Microphone input failed. Text input remains available."
            )
        signal = source_result.raw_signal
        if signal is None:
            return _microphone_failure_result(
                "Microphone input failed. Text input remains available."
            )
        print("[appruntime.py]line156:before asr")
        transcript = signal.payload.get("text")
        if not isinstance(transcript, str) or not transcript.strip():
            return _microphone_failure_result(
                "No speech was detected. Text input remains available."
            )

        normalized_transcript = transcript.strip()
        report_status("Transcription complete.")
        text_signal = CLITextSignalSource().create_signal(
            text=normalized_transcript,
            trace_id=f"trace-web-microphone-text-{uuid4().hex}",
        )
        return self._run_signal_with_display(
            text_signal,
            user_input=normalized_transcript,
            transcript=normalized_transcript,
        )

    def _run_signal_with_display(
        self,
        signal,
        *,
        user_input: str,
        transcript: str | None = None,
    ) -> AppDisplayResult:
        task_result = self._run_signal_to_completion(signal)
        return self._display_result(
            task_result,
            user_input=user_input,
            transcript=transcript,
        )

    def _display_result(
        self,
        task_result: TaskRuntimeResult,
        *,
        user_input: str,
        transcript: str | None = None,
    ) -> AppDisplayResult:
        completion = task_result.completion
        memory_result = task_result.memory_result
        output = _render_output(
            completion.user_visible_output,
            memory_result.memory_path,
            completion.tool_results,
        )
        return AppDisplayResult(
            output=output,
            snapshot=_build_display_snapshot(
                user_input,
                task_result,
                transcript=transcript,
            ),
        )

    def _run_signal_to_completion(self, signal) -> TaskRuntimeResult:
        event_result = self._event_runtime.publish(signal)
        if not event_result.submitted or event_result.task_handle is None:
            raise RuntimeError(event_result.reason)
        print("[app_runtime]:_run_signal_to_completion")
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
    *,
    transcript: str | None = None,
) -> RunDisplaySnapshot:
    completion = task_result.completion
    output = completion.user_visible_output
    tool_results = completion.tool_results
    camera_result = _find_tool_result(tool_results, "camera_scene")
    process = output.process
    return RunDisplaySnapshot(
        user_input=user_input,
        transcript=transcript,
        captured_frame_reference=_captured_frame_reference(camera_result),
        image_status=_image_status(tool_results, camera_result),
        scene_summary=_scene_summary(camera_result),
        visible_items=_visible_items(camera_result),
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
        final_response_prompt_text=str(
            process.get("final_response_prompt_text", "")
        ),
        tool_results_summary=_tool_results_summary(tool_results),
        final_response=output.final_response,
        memory_status=getattr(task_result.memory_result, "action", "unknown"),
        timing_summary=_timing_summary(task_result),
        task_id=task_result.handle.task_id,
        task_state=task_result.task.state.value,
        active_step_ids=task_result.task.active_step_ids,
        waiting_condition=_display_value(task_result.task.waiting_condition),
        paused_from_state=(
            ""
            if task_result.task.paused_from_state is None
            else task_result.task.paused_from_state.value
        ),
        terminal_outcome=_display_value(task_result.task.terminal_outcome),
        delivery_status=_display_value(task_result.task.delivery),
    )


def _display_value(value) -> str:
    if value is None:
        return ""
    to_dict = getattr(value, "to_dict", None)
    return str(to_dict() if callable(to_dict) else value)


def _microphone_failure_result(message: str) -> AppDisplayResult:
    return AppDisplayResult(
        output=message,
        snapshot=RunDisplaySnapshot(
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
            final_response=message,
            memory_status="not recorded",
            timing_summary="",
        ),
    )


def _timing_summary(task_result: TaskRuntimeResult) -> str:
    snapshot = task_result.timing
    if snapshot is None:
        return ""
    lines = []
    values = (
        ("input_to_task_submitted", snapshot.input_to_task_submitted_duration_ms),
        ("task_formulation_stage", snapshot.task_formulation_duration_ms),
        ("queue_wait", snapshot.queue_wait_duration_ms),
        ("planning", snapshot.planning_duration_ms),
        ("runtime_execution", snapshot.total_execution_duration_ms),
        ("final_response_stage", snapshot.final_response_generation_duration_ms),
        ("end_to_end", snapshot.end_to_end_duration_ms),
    )
    for label, value in values:
        if value is not None:
            lines.append(f"{label}: {value}ms")

    llm_by_boundary = _llm_timing_by_boundary(snapshot)
    for boundary in (
        "task_formulation",
        "strategy_selection",
        "execution_decision",
        "final_response",
    ):
        value = llm_by_boundary.get(boundary)
        if value is not None:
            lines.append(f"llm:{boundary}: {value}ms")

    totals = (
        ("llm_total_all_boundaries", snapshot.total_llm_duration_ms),
        ("tool_total", snapshot.total_tool_duration_ms),
    )
    for label, value in totals:
        if value is not None:
            lines.append(f"{label}: {value}ms")
    for entry in snapshot.tool_calls:
        lines.append(f"tool:{entry.tool_name}: {entry.duration_ms}ms")
    return "\n".join(lines)


def _llm_timing_by_boundary(task_timing) -> dict[str, float]:
    totals: dict[str, float] = {}
    for entry in task_timing.llm_calls:
        totals[entry.boundary] = round(
            totals.get(entry.boundary, 0.0) + entry.duration_ms,
            3,
        )
    return totals


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
