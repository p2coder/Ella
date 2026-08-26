from dataclasses import dataclass
from time import perf_counter

from events import RawSignal, StandardizedEvent
from events.trigger_pipeline import (
    CliTextToStandardizedEventStage,
    EventTriggerPipeline,
)
from .event_queue import PresenceQueue
from .event_router import (
    PRESENCE_QUEUE,
    EventRouteResult,
    TaskAwareEventRouter,
)
from .presence_runtime import PresenceRuntime
from .task_runtime import TaskHandle, TaskRuntime
from .timing import NoOpRuntimeTimingRecorder, RuntimeTimingRecorder


@dataclass(frozen=True, slots=True)
class EventRuntimeResult:
    event: StandardizedEvent
    route: EventRouteResult
    submitted: bool
    task_handle: TaskHandle | None
    reason: str


@dataclass(slots=True, init=False)
class EventRuntime:
    trigger_pipeline: EventTriggerPipeline
    event_router: TaskAwareEventRouter
    presence_queue: PresenceQueue
    presence_runtime: PresenceRuntime
    task_runtime: TaskRuntime
    timing_recorder: RuntimeTimingRecorder | NoOpRuntimeTimingRecorder
    user_preference_summary: str
    environment_summary: str

    def __init__(
        self,
        trigger_pipeline: EventTriggerPipeline | None = None,
        event_router: TaskAwareEventRouter | None = None,
        presence_queue: PresenceQueue | None = None,
        presence_runtime: PresenceRuntime | None = None,
        task_runtime: TaskRuntime | None = None,
        timing_recorder: RuntimeTimingRecorder | NoOpRuntimeTimingRecorder | None = None,
        user_preference_summary: str = "No user preference summary provided.",
        environment_summary: str = "No environment summary provided.",
    ) -> None:
        recorder = timing_recorder or NoOpRuntimeTimingRecorder()
        queue = presence_queue if presence_queue is not None else PresenceQueue()
        runtime = (
            presence_runtime
            if presence_runtime is not None
            else PresenceRuntime(queue)
        )
        if runtime.presence_queue is not queue:
            raise ValueError(
                "presence_runtime must consume the EventRuntime presence_queue"
            )

        self.trigger_pipeline = trigger_pipeline or EventTriggerPipeline(
            stages=(CliTextToStandardizedEventStage(),),
        )
        self.event_router = event_router or TaskAwareEventRouter()
        self.presence_queue = queue
        self.presence_runtime = runtime
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

        stage_started = perf_counter()
        route = self.event_router.route(event)
        self.timing_recorder.record_stage_duration(
            event.trace_id,
            "routing_duration_ms",
            stage_started,
        )
        if route.destination != PRESENCE_QUEUE:
            return EventRuntimeResult(
                event=event,
                route=route,
                submitted=False,
                task_handle=None,
                reason=f"event routed to {route.destination.name}",
            )

        allowed_events: list[StandardizedEvent] = []
        previous_boundary = self.presence_runtime.next_boundary

        def forward_allowed(allowed_event: StandardizedEvent) -> None:
            allowed_events.append(allowed_event)
            if previous_boundary is not None:
                previous_boundary(allowed_event)

        self.presence_runtime.next_boundary = forward_allowed
        stage_started = perf_counter()
        self.presence_queue.enqueue(event)
        try:
            self.presence_runtime.process_available()
        finally:
            self.presence_runtime.next_boundary = previous_boundary
        self.timing_recorder.record_stage_duration(
            event.trace_id,
            "presence_queue_duration_ms",
            stage_started,
        )

        if event not in allowed_events:
            return EventRuntimeResult(
                event=event,
                route=route,
                submitted=False,
                task_handle=None,
                reason="presence runtime did not allow event",
            )

        task_handle = self.task_runtime.create_task(
            event,
            user_preference_summary=self.user_preference_summary,
            environment_summary=self.environment_summary,
        )
        self.timing_recorder.record_input_to_task_submitted(event.trace_id)
        return EventRuntimeResult(
            event=event,
            route=route,
            submitted=True,
            task_handle=task_handle,
            reason="event submitted to task runtime for first decision",
        )
