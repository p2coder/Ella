from dataclasses import dataclass

from agent.main_agent import MainAgent
from events import RawSignal, StandardizedEvent
from events.trigger_pipeline import (
    CliTextToStandardizedEventStage,
    EventTriggerPipeline,
)

from .event_queue import PresenceQueue
from .event_router import (
    PRESENCE_QUEUE,
    EventRouteResult,
    SessionAwareEventRouter,
)
from .presence_runtime import PresenceRuntime
from .task_runtime import TaskHandle, TaskRuntime


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
    task_runtime: TaskRuntime
    user_preference_summary: str
    environment_summary: str

    def __init__(
        self,
        trigger_pipeline: EventTriggerPipeline | None = None,
        event_router: SessionAwareEventRouter | None = None,
        presence_queue: PresenceQueue | None = None,
        presence_runtime: PresenceRuntime | None = None,
        main_agent: MainAgent | None = None,
        task_runtime: TaskRuntime | None = None,
        user_preference_summary: str = "No user preference summary provided.",
        environment_summary: str = "No environment summary provided.",
    ) -> None:
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
        self.main_agent = main_agent or MainAgent()
        self.task_runtime = task_runtime or TaskRuntime()
        self.user_preference_summary = user_preference_summary
        self.environment_summary = environment_summary

    def publish(self, raw_signal: RawSignal) -> EventRuntimeResult:
        event = self.trigger_pipeline.run(raw_signal)
        if not isinstance(event, StandardizedEvent):
            raise TypeError(
                "EventRuntime trigger pipeline must produce a StandardizedEvent"
            )

        route = self.event_router.route(event)
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
        self.presence_queue.enqueue(event)
        try:
            self.presence_runtime.process_available()
        finally:
            self.presence_runtime.next_boundary = previous_boundary

        if event not in allowed_events:
            return EventRuntimeResult(
                event=event,
                route=route,
                submitted=False,
                task_handle=None,
                reason="presence runtime did not allow event",
            )

        handoff = self.main_agent.create_handoff(
            trigger_event=event,
            user_preference_summary=self.user_preference_summary,
            environment_summary=self.environment_summary,
        )
        task_handle = self.task_runtime.submit(handoff)
        return EventRuntimeResult(
            event=event,
            route=route,
            submitted=True,
            task_handle=task_handle,
            reason="event submitted to task runtime",
        )
