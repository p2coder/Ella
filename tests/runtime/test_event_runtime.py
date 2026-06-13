from dataclasses import dataclass, field
from datetime import datetime, timezone

from agent import MainAgent
from events import RawSignal, StandardizedEvent
from events.trigger_pipeline import EventTriggerPipeline, PipelineStage
from runtime.event_queue import PresenceQueue
from runtime.event_router import SessionAwareEventRouter
from runtime.event_runtime import EventRuntime
from runtime.presence_runtime import PresenceRuntime
from runtime.task_runtime import TaskHandle


FIXED_TIME = datetime(2026, 6, 13, 14, 0, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class SignalToEventStage(PipelineStage):
    def process(self, signal: RawSignal) -> StandardizedEvent:
        return StandardizedEvent(
            trace_id=signal.trace_id,
            source=signal.source,
            timestamp=signal.timestamp,
            payload=signal.payload,
            event_type=str(signal.metadata.get("event_type", "USER_UTTERANCE")),
            target_session_id=signal.metadata.get("target_session_id"),
            caused_by_task_id=signal.metadata.get("caused_by_task_id"),
            metadata={
                key: value
                for key, value in signal.metadata.items()
                if key
                not in {"event_type", "target_session_id", "caused_by_task_id"}
            },
        )


@dataclass
class RecordingTaskRuntime:
    submitted_handoffs: list = field(default_factory=list)

    def submit(self, handoff):
        self.submitted_handoffs.append(handoff)
        return TaskHandle(
            task_id="task-event-runtime",
            session_id="session-event-runtime",
            trace_id=handoff.trigger_event.trace_id,
        )


def make_signal(**metadata) -> RawSignal:
    return RawSignal(
        trace_id="trace-event-runtime",
        source="test_input",
        timestamp=FIXED_TIME,
        payload={"text": "Ella，我要出门了"},
        signal_type="test_signal",
        metadata=metadata,
    )


def make_runtime(*, active_session_ids: set[str] | None = None):
    queue = PresenceQueue()
    task_runtime = RecordingTaskRuntime()
    runtime = EventRuntime(
        trigger_pipeline=EventTriggerPipeline(stages=(SignalToEventStage(),)),
        event_router=SessionAwareEventRouter(
            active_session_ids=active_session_ids,
        ),
        presence_queue=queue,
        presence_runtime=PresenceRuntime(queue),
        main_agent=MainAgent(),
        task_runtime=task_runtime,
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Mock environment only.",
    )
    return runtime, task_runtime


def test_publish_user_initiated_signal_submits_handoff_and_returns_handle():
    runtime, task_runtime = make_runtime()

    result = runtime.publish(
        make_signal(trigger_kind="user_initiated"),
    )

    assert result.submitted is True
    assert result.task_handle == TaskHandle(
        task_id="task-event-runtime",
        session_id="session-event-runtime",
        trace_id="trace-event-runtime",
    )
    assert result.route.destination.name == "PRESENCE_QUEUE"
    assert len(task_runtime.submitted_handoffs) == 1
    handoff = task_runtime.submitted_handoffs[0]
    assert handoff.trigger_event is result.event
    assert handoff.task_goal == (
        "Give the user a short, necessary reminder before leaving."
    )


def test_presence_queue_event_rejected_by_policy_is_not_submitted():
    runtime, task_runtime = make_runtime()
    signal = make_signal(trigger_kind="user_initiated")
    object.__setattr__(
        runtime.presence_runtime,
        "interruption_policy",
        RejectingInterruptionPolicy(),
    )

    result = runtime.publish(signal)

    assert result.route.destination.name == "PRESENCE_QUEUE"
    assert result.submitted is False
    assert result.task_handle is None
    assert result.reason == "presence runtime did not allow event"
    assert task_runtime.submitted_handoffs == []


@dataclass(frozen=True, slots=True)
class Rejection:
    allowed: bool = False
    reason: str = "test rejection"


@dataclass(frozen=True, slots=True)
class RejectingInterruptionPolicy:
    def evaluate(self, event):
        return Rejection()


def test_session_inbox_route_does_not_create_new_task():
    runtime, task_runtime = make_runtime(active_session_ids={"session-active"})

    result = runtime.publish(
        make_signal(
            event_type="TOOL_CALLBACK",
            target_session_id="session-active",
        )
    )

    assert result.route.destination.name == "SESSION_INBOX"
    assert result.submitted is False
    assert result.task_handle is None
    assert task_runtime.submitted_handoffs == []


def test_ambient_state_route_does_not_create_new_task():
    runtime, task_runtime = make_runtime()

    result = runtime.publish(
        make_signal(event_type="ENVIRONMENT_UPDATE", ambient=True)
    )

    assert result.route.destination.name == "AMBIENT_STATE"
    assert result.submitted is False
    assert task_runtime.submitted_handoffs == []


def test_suppressed_route_does_not_create_new_task():
    runtime, task_runtime = make_runtime()

    result = runtime.publish(
        make_signal(event_type="BACKGROUND_NOISE", suppress=True)
    )

    assert result.route.destination.name == "SUPPRESSED"
    assert result.submitted is False
    assert task_runtime.submitted_handoffs == []


def test_event_runtime_does_not_select_skill_call_tools_or_complete_task():
    runtime, task_runtime = make_runtime()

    result = runtime.publish(make_signal(trigger_kind="user_initiated"))

    assert result.submitted is True
    assert not hasattr(runtime, "subagent")
    assert not hasattr(runtime, "executor")
    assert not hasattr(runtime, "tool_manager")
    assert not hasattr(result, "completion")
    assert len(task_runtime.submitted_handoffs) == 1
