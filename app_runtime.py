from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum
from typing import Any, Callable, Mapping
from uuid import uuid4

from agent.verification import VerificationAgent
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
from events.microphone_source import MicrophoneSource
from events.source import CLITextSignalSource
from memory import MemoryManager
from prompts.engine import PromptEngine
from providers.factory import ProviderFactory
from runtime.event_runtime import EventRuntime
from runtime.plan_store import PlanStore
from runtime.provider_usage import aggregate_provider_usage
from runtime.task_runtime import TaskRuntime, TaskRuntimeResult
from runtime.task_queue import TaskQueue
from runtime.task_store import TaskStore
from runtime.timing import RuntimeTimingRecorder
from runtime.trace import TraceRecorder
from runtime.task_events import TERMINAL_TASK_STATES
from tasks.state import (
    TaskControlCommand,
    TaskControlType,
)
from agent.subagent import SubAgent
from runtime.executor import CapabilityExecutor
from tasks.factory import TaskFactory
from skill import SkillLoader, SkillManager
from tools import (
    BashTool,
    DocumentWriteTool,
    EditTextTool,
    ReadTextTool,
    RefreshTool,
    WriteTextTool,
    MockChecklistTool,
    MockVisionSummaryTool,
    MockWeatherTool,
    ToolManager,
    ToolResult,
    WebPageReadTool,
    WebSearchTool,
)
from tools.camera_scene import CameraSceneTool
from tools.screen_scene import ScreenSceneTool
from tools.plan import PlanWrittenTool
from tools.ask_user_question import AskUserQuestionTool
from tools.verification import (
    ArtifactExistsTool,
    DocumentReadTool,
    ToolObservationCheckTool,
    VerificationTool,
)
from runtime.interactions import InteractionBroker

@dataclass(frozen=True, slots=True)
class AppRuntime:
    _event_runtime: EventRuntime
    _task_runtime: TaskRuntime
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
        screen_provider = device_factory.screen()

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
        tool_manager.register(WebSearchTool())
        tool_manager.register(WebPageReadTool())
        tool_manager.register(DocumentWriteTool(settings.document_directory))
        tool_manager.register(ReadTextTool(PROJECT_ROOT))
        tool_manager.register(WriteTextTool(PROJECT_ROOT))
        tool_manager.register(EditTextTool(PROJECT_ROOT))
        tool_manager.register(BashTool(PROJECT_ROOT))
        tool_manager.register(RefreshTool())
        tool_manager.register(ArtifactExistsTool(settings.document_directory))
        tool_manager.register(DocumentReadTool(settings.document_directory))
        plan_store = PlanStore(settings.plan_directory)
        tool_manager.register(PlanWrittenTool(plan_store))
        interaction_broker = InteractionBroker()
        tool_manager.register(AskUserQuestionTool(interaction_broker))


        subagent = SubAgent(
            skill_manager,
            tool_directory=tool_manager,
            llm_provider=llm_provider,
            timing_recorder=timing_recorder,
            trace_recorder=trace_recorder,
            context_window_tokens=settings.context_window_tokens,
            context_compression_threshold=settings.context_compression_threshold,
        )
        verification_agent = VerificationAgent(
            prompt_engine=PromptEngine(),
            llm_provider=llm_provider,
            timing_recorder=timing_recorder,
            context_window_tokens=settings.context_window_tokens,
            context_compression_threshold=settings.context_compression_threshold,
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
            timing_recorder=timing_recorder,
            trace_recorder=trace_recorder,
            task_store=TaskStore(settings.task_checkpoint_directory),
            task_queue=TaskQueue(),
        )
        tool_manager.register(
            ToolObservationCheckTool(
                lambda task_id: tuple(task_runtime.get_task(task_id).tool_trace)
            )
        )
        tool_manager.register(
            VerificationTool(task_runtime.get_task, verification_agent)
        )
        interaction_broker.set_question_handler(
            lambda question: task_runtime.event_publisher.publish(
                "task_interaction_required",
                question.task_id,
                {"question": question.to_dict()},
            )
        )
        event_runtime = EventRuntime(
            task_runtime=task_runtime,
            timing_recorder=timing_recorder,
        )
        microphone_source = MicrophoneSource.from_factories(
            device_factory=device_factory,
            provider_factory=provider_factory,
        )
        runtime = cls(
            event_runtime,
            task_runtime,
            microphone_source=microphone_source,
        )
        task_runtime.start()
        return runtime

    def close(self, timeout: float | None = 5.0) -> bool:
        self._task_runtime.stop()
        return self._task_runtime.join(timeout)

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
        task = self._task_runtime.get_task(task_id)
        return self._task_projection(task)

    def list_active_tasks(self) -> tuple[dict[str, object], ...]:
        return tuple(
            self._task_projection(task, include_trace=False)
            for task in self._task_runtime.list_tasks()
            if task.state not in TERMINAL_TASK_STATES
        )

    def list_terminal_tasks(self) -> tuple[dict[str, object], ...]:
        return tuple(
            self._task_projection(task, include_trace=False)
            for task in self._task_runtime.list_tasks()
            if task.state in TERMINAL_TASK_STATES
        )

    def task_snapshot(self) -> dict[str, object]:
        return {
            "active_tasks": self.list_active_tasks(),
            "terminal_tasks": self.list_terminal_tasks(),
        }

    def subscribe_task_events(self, last_event_id: int | None = None):
        publisher = self._task_runtime.event_publisher
        cursor = publisher.latest_event_id
        yield {
            "event_id": cursor,
            "event_type": "task_snapshot",
            "task_id": "",
            "payload": self.task_snapshot(),
        }
        if last_event_id is not None and last_event_id > cursor:
            cursor = last_event_id
        while self._task_runtime.is_running:
            events = publisher.wait_after(cursor, timeout=15.0)
            if not events:
                yield {
                    "event_id": cursor,
                    "event_type": "heartbeat",
                    "task_id": "",
                    "payload": {},
                }
                continue
            for event in events:
                cursor = event.event_id
                document = event.to_dict()
                try:
                    document["payload"] = {
                        **dict(event.payload),
                        "task": self._task_projection(
                            self._task_runtime.get_task(event.task_id),
                            include_trace=False,
                        ),
                    }
                except KeyError:
                    pass
                yield document

    def provide_input(
        self,
        task_id: str,
        correlation_key: str,
        value: str,
    ) -> bool:
        return self._task_runtime.provide_input(
            task_id,
            correlation_key=correlation_key,
            value=value,
        )

    def _task_projection(
        self,
        task,
        *,
        include_trace: bool = True,
    ) -> dict[str, object]:
        trace = (
            self._task_runtime.trace_recorder.snapshot(task.task_id)
            if include_trace
            else None
        )
        projection = {
            "task_id": task.task_id,
            "trace_id": task.trace_id,
            "user_input_summary": _task_user_input(task),
            "state": task.state.value,
            "goal_state": None if task.goal_state is None else task.goal_state.value,
            "terminal_execution_state": (
                None
                if task.terminal_execution_state is None
                else task.terminal_execution_state.value
            ),
            "execution_stage": _execution_stage(task),
            "active_step_ids": task.active_step_ids,
            "pending_questions": tuple(
                item.to_dict()
                for item in self._task_runtime.pending_questions(task.task_id)
            ),
            "paused_from_state": (
                None if task.paused_from_state is None else task.paused_from_state.value
            ),
            "terminal_outcome": _public_value(task.terminal_outcome),
            "failure": _public_value(task.failure),
            "uncertain_resolution": _public_value(task.uncertain_resolution),
            "delivery": _public_value(task.delivery),
            "trace": None if trace is None else trace.to_dict(),
            "trace_url": f"/task?task_id={task.task_id}",
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
            "finished_at": (
                task.updated_at.isoformat()
                if task.state in TERMINAL_TASK_STATES
                else None
            ),
            "final_response": None,
            "model_output": _current_model_output(task),
        }
        result = self._task_runtime.result_for(task.task_id)
        projection["timing"] = (
            None if result.timing is None else result.timing.to_dict()
        )
        projection["timing_summary"] = _timing_summary(result)
        projection.update(_usage_projection(task))
        if result.completion is not None:
            user_input = ""
            source_event = task.source_event
            if source_event is not None:
                user_input = str(source_event.payload.get("text", ""))
            projection["display_snapshot"] = _build_display_snapshot(
                user_input,
                result,
            ).to_dict()
            projection["final_response"] = (
                result.completion.user_visible_output.final_response
            )
        return projection

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

    def submit_microphone(
        self,
        *,
        status_callback: Callable[[str], None] | None = None,
    ):
        report_status = status_callback or (lambda _status: None)
        report_status("Listening...")
        source = self.microphone_source or MicrophoneSource.from_factories()
        source_result = source.capture_transcript(
            trace_id=f"trace-web-microphone-{uuid4().hex}",
        )
        signal = source_result.raw_signal
        if signal is None:
            raise RuntimeError("Microphone input failed.")
        transcript = signal.payload.get("text")
        if not isinstance(transcript, str) or not transcript.strip():
            raise RuntimeError("No speech was detected.")
        normalized = transcript.strip()
        report_status("Transcription complete.")
        text_signal = CLITextSignalSource().create_signal(
            text=normalized,
            trace_id=f"trace-web-microphone-text-{uuid4().hex}",
        )
        result = self._event_runtime.publish(text_signal)
        if not result.submitted or result.task_handle is None:
            raise RuntimeError(result.reason)
        return result.task_handle, normalized

def _task_user_input(task, maximum: int = 120) -> str:
    if task.source_event is None:
        return ""
    text = str(task.source_event.payload.get("text", "")).strip()
    return text if len(text) <= maximum else f"{text[: maximum - 1]}…"


def _execution_stage(task) -> str:
    in_flight = task.task_local_state.get("in_flight_action")
    if isinstance(in_flight, Mapping):
        return "tool_execution"
    return {
        "created": "created",
        "ready": "queued",
        "reasoning": "reasoning",
        "tool_execution": "tool_execution",
        "pause_requested": "pause_requested",
        "paused": "paused",
        "kill_requested": "kill_requested",
    }.get(task.state.value, "terminal")

def _public_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _public_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_public_value(item) for item in value]
    if is_dataclass(value):
        return _public_value(asdict(value))
    return str(value)


def _current_model_output(task) -> str:
    """Expose user-facing model text without leaking prompts or hidden reasoning."""
    if task.completion is not None:
        return task.completion.user_visible_output.final_response
    draft = task.task_local_state.get("draft_final_response")
    if isinstance(draft, str) and draft.strip():
        return draft
    decision = task.task_local_state.get("current_decision")
    if isinstance(decision, Mapping):
        for key in ("final_response_draft", "completion_summary", "decision_reason"):
            value = decision.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return ""


def _usage_projection(task) -> dict[str, object]:
    """Project text usage from the task's provider call ledger."""
    calls = task.task_local_state.get("provider_usage_calls", ())
    usage = aggregate_provider_usage(calls, modality="text")
    if usage is None:
        usage = dict.fromkeys((
            "token_usage", "prompt_tokens", "completion_tokens",
            "cached_tokens", "cache_hit_rate",
        ))
    return {**usage, "provider_usage_calls": _public_value(calls)}


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
        tool_results_summary=_tool_results_summary(tool_results),
        final_response=output.final_response,
        memory_status=getattr(task_result.memory_result, "action", "unknown"),
        timing_summary=_timing_summary(task_result),
        task_id=task_result.handle.task_id,
        task_state=task_result.task.state.value,
        active_step_ids=task_result.task.active_step_ids,
        paused_from_state=(
            ""
            if task_result.task.paused_from_state is None
            else task_result.task.paused_from_state.value
        ),
        terminal_outcome=_display_value(task_result.task.terminal_outcome),
        delivery_status=_display_value(task_result.task.delivery),
        goal_state=(
            ""
            if task_result.task.goal_state is None
            else task_result.task.goal_state.value
        ),
        terminal_execution_state=(
            ""
            if task_result.task.terminal_execution_state is None
            else task_result.task.terminal_execution_state.value
        ),
    )


def _display_value(value) -> str:
    if value is None:
        return ""
    to_dict = getattr(value, "to_dict", None)
    return str(to_dict() if callable(to_dict) else value)


def _timing_summary(task_result: TaskRuntimeResult) -> str:
    snapshot = task_result.timing
    if snapshot is None:
        return ""
    lines = []
    values = (
        ("input_to_task_submitted", snapshot.input_to_task_submitted_duration_ms),
        ("queue_wait", snapshot.queue_wait_duration_ms),
        ("planning", snapshot.planning_duration_ms),
        ("runtime_execution", snapshot.total_execution_duration_ms),
        ("end_to_end", snapshot.end_to_end_duration_ms),
    )
    for label, value in values:
        if value is not None:
            lines.append(f"{label}: {value}ms")

    llm_by_boundary = _llm_timing_by_boundary(snapshot)
    for boundary in (
        "first_decision",
        "execution_decision",
        "verification_decision",
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
