from dataclasses import dataclass
from time import perf_counter

from agent.main_agent import MainAgent
from agent.handoff import HandoffRequest
from events import RawSignal, StandardizedEvent
from events.trigger_pipeline import (
    CliTextToStandardizedEventStage,
    EventTriggerPipeline,
)
from providers.llm import LLMProvider

from .event_queue import PresenceQueue
from .event_router import (
    PRESENCE_QUEUE,
    EventRouteResult,
    SessionAwareEventRouter,
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
    event_router: SessionAwareEventRouter
    presence_queue: PresenceQueue
    presence_runtime: PresenceRuntime
    main_agent: MainAgent
    llm_provider: LLMProvider | None
    task_runtime: TaskRuntime
    timing_recorder: RuntimeTimingRecorder | NoOpRuntimeTimingRecorder
    user_preference_summary: str
    environment_summary: str

    def __init__(
        self,
        trigger_pipeline: EventTriggerPipeline | None = None,
        event_router: SessionAwareEventRouter | None = None,
        presence_queue: PresenceQueue | None = None,
        presence_runtime: PresenceRuntime | None = None,
        main_agent: MainAgent | None = None,
        llm_provider: LLMProvider | None = None,
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
        self.event_router = event_router or SessionAwareEventRouter()
        self.presence_queue = queue
        self.presence_runtime = runtime
        if main_agent is None:
            active_agent = MainAgent(
                llm_provider=llm_provider,
                timing_recorder=recorder,
            )
        else:
            active_agent = main_agent
            if (
                llm_provider is not None
                and active_agent.llm_provider is not llm_provider
            ):
                raise ValueError(
                    "llm_provider must match the explicitly supplied main_agent"
                )
        self.main_agent = active_agent
        self.llm_provider = active_agent.llm_provider
        self.task_runtime = task_runtime or TaskRuntime()
        configure_formulation = getattr(
            self.task_runtime,
            "configure_formulation",
            None,
        )
        if callable(configure_formulation):
            configure_formulation(self._formulate_task)
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

        create_task = getattr(self.task_runtime, "create_task", None)
        if not callable(create_task):
            stage_started = perf_counter()
            handoff = self.main_agent.create_handoff(
                trigger_event=event,
                user_preference_summary=self.user_preference_summary,
                environment_summary=self.environment_summary,
            )
            self.timing_recorder.record_stage_duration(
                event.trace_id,
                "task_formulation_duration_ms",
                stage_started,
            )
            task_handle = self.task_runtime.submit(handoff)
            self.timing_recorder.record_input_to_task_submitted(event.trace_id)
            return EventRuntimeResult(
                event=event,
                route=route,
                submitted=True,
                task_handle=task_handle,
                reason="event submitted to task runtime",
            )

        task_handle = create_task(event)
        if bool(getattr(self.task_runtime, "is_running", False)):
            self.timing_recorder.record_input_to_task_submitted(event.trace_id)
            return EventRuntimeResult(
                event=event,
                route=route,
                submitted=True,
                task_handle=task_handle,
                reason="event accepted for asynchronous task formulation",
            )
        self.task_runtime.begin_formulation(task_handle.task_id)
        stage_started = perf_counter()
        try:
            handoff = self.main_agent.create_handoff(
                trigger_event=event,
                user_preference_summary=self.user_preference_summary,
                environment_summary=self.environment_summary,
                task_id=task_handle.task_id,
            )
        except Exception as exc:
            self.task_runtime.fail_formulation(task_handle.task_id, str(exc))
            return EventRuntimeResult(
                event=event,
                route=route,
                submitted=False,
                task_handle=task_handle,
                reason="task formulation failed",
            )
        self.timing_recorder.record_stage_duration(
            event.trace_id,
            "task_formulation_duration_ms",
            stage_started,
        )
        task_handle = self.task_runtime.submit_formulated(
            task_handle.task_id, handoff
        )
        self.timing_recorder.record_input_to_task_submitted(event.trace_id)
        return EventRuntimeResult(
            event=event,
            route=route,
            submitted=True,
            task_handle=task_handle,
            reason="event submitted to task runtime",
        )

    def _formulate_task(self, task) -> HandoffRequest:
        event = task.source_event
        if event is None:
            raise ValueError("Task formulation requires a source event")
        stage_started = perf_counter()
        try:
            return self.main_agent.create_handoff(
                trigger_event=event,
                user_preference_summary=self.user_preference_summary,
                environment_summary=self.environment_summary,
                task_id=task.task_id,
            )
        finally:
            self.timing_recorder.record_stage_duration(
                event.trace_id,
                "task_formulation_duration_ms",
                stage_started,
            )
