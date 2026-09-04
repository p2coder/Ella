from dataclasses import dataclass
from time import perf_counter

from events import RawSignal, StandardizedEvent
from events.trigger_pipeline import (
    CliTextToStandardizedEventStage,
    EventTriggerPipeline,
)
from .task_runtime import TaskHandle, TaskRuntime
from .timing import NoOpRuntimeTimingRecorder, RuntimeTimingRecorder


@dataclass(frozen=True, slots=True)
class EventRuntimeResult:
    event: StandardizedEvent
    submitted: bool
    task_handle: TaskHandle | None
    reason: str


@dataclass(slots=True, init=False)
class EventRuntime:
    trigger_pipeline: EventTriggerPipeline
    task_runtime: TaskRuntime
    timing_recorder: RuntimeTimingRecorder | NoOpRuntimeTimingRecorder
    user_preference_summary: str
    environment_summary: str

    def __init__(
        self,
        trigger_pipeline: EventTriggerPipeline | None = None,
        task_runtime: TaskRuntime | None = None,
        timing_recorder: RuntimeTimingRecorder | NoOpRuntimeTimingRecorder | None = None,
        user_preference_summary: str = "No user preference summary provided.",
        environment_summary: str = "No environment summary provided.",
    ) -> None:
        recorder = timing_recorder or NoOpRuntimeTimingRecorder()
        self.trigger_pipeline = trigger_pipeline or EventTriggerPipeline(
            stages=(CliTextToStandardizedEventStage(),),
        )
        self.task_runtime = task_runtime or TaskRuntime()
        self.timing_recorder = recorder
        self.user_preference_summary = user_preference_summary
        self.environment_summary = environment_summary

    def publish(self, raw_signal: RawSignal) -> EventRuntimeResult:
        self.timing_recorder.start_input(raw_signal.trace_id)
        stage_started = perf_counter()
        event = self.trigger_pipeline.run(raw_signal)
        self.timing_recorder.record_stage_duration(
            raw_signal.trace_id,
            "trigger_pipeline_duration_ms",
            stage_started,
        )
        if not isinstance(event, StandardizedEvent):
            raise TypeError(
                "EventRuntime trigger pipeline must produce a StandardizedEvent"
            )

        task_handle = self.task_runtime.create_task(
            event,
            user_preference_summary=self.user_preference_summary,
            environment_summary=self.environment_summary,
        )
        self.timing_recorder.record_input_to_task_submitted(event.trace_id)
        return EventRuntimeResult(
            event=event,
            submitted=True,
            task_handle=task_handle,
            reason="event submitted to task runtime for first decision",
        )
