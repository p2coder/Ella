from datetime import datetime, timezone

from events import StandardizedEvent
from runtime.ambient_state import AmbientState
from runtime.event_queue import PresenceQueue
from runtime.event_router import (
    AMBIENT_STATE,
    PRESENCE_QUEUE,
    SESSION_INBOX,
    SUPPRESSED,
    RouteDestination,
    RouteDestinationRegistry,
    SessionAwareEventRouter,
)


FIXED_TIME = datetime(2026, 6, 13, 10, 0, tzinfo=timezone.utc)


def make_event(
    event_type: str,
    *,
    metadata: dict | None = None,
    target_session_id: str | None = None,
    caused_by_task_id: str | None = None,
    confidence: float | None = 1.0,
) -> StandardizedEvent:
    return StandardizedEvent(
        trace_id=f"trace-{event_type.lower()}",
        source="test",
        timestamp=FIXED_TIME,
        payload={"value": event_type},
        event_type=event_type,
        confidence=confidence,
        target_session_id=target_session_id,
        caused_by_task_id=caused_by_task_id,
        metadata=metadata or {},
    )


def test_route_destination_registry_supports_defaults_and_extensions():
    registry = RouteDestinationRegistry()

    assert registry.get("SESSION_INBOX") == SESSION_INBOX
    assert registry.get("AMBIENT_STATE") == AMBIENT_STATE
    assert registry.get("SUPPRESSED") == SUPPRESSED
    assert registry.get("PRESENCE_QUEUE") == PRESENCE_QUEUE

    custom = RouteDestination("MONITOR_QUEUE", "External monitor queue")
    registry.register(custom)
    assert registry.get("MONITOR_QUEUE") == custom

    registry.unregister("MONITOR_QUEUE")
    assert registry.get("MONITOR_QUEUE") is None


def test_active_task_session_event_routes_to_session_inbox():
    router = SessionAwareEventRouter(active_session_ids={"task-123"})
    event = make_event(
        "TOOL_CALLBACK",
        target_session_id="task-123",
        caused_by_task_id="task-123",
    )

    result = router.route(event)

    assert result.destination == SESSION_INBOX
    assert result.event == event
    assert result.target_session_id == "task-123"


def test_ambient_environment_event_routes_to_ambient_state():
    router = SessionAwareEventRouter()
    event = make_event(
        "ENVIRONMENT_UPDATE",
        metadata={"ambient": True},
    )

    result = router.route(event)

    assert result.destination == AMBIENT_STATE


def test_user_initiated_event_routes_to_presence_queue():
    router = SessionAwareEventRouter()
    event = make_event(
        "USER_UTTERANCE",
        metadata={"trigger_kind": "user_initiated"},
    )

    result = router.route(event)

    assert result.destination == PRESENCE_QUEUE


def test_noise_event_routes_to_suppressed():
    router = SessionAwareEventRouter()
    event = make_event("BACKGROUND_NOISE", metadata={"suppress": True})

    result = router.route(event)

    assert result.destination == SUPPRESSED


def test_router_only_decides_route_and_does_not_enqueue_or_update_state():
    router = SessionAwareEventRouter()
    queue = PresenceQueue()
    ambient_state = AmbientState()
    event = make_event(
        "USER_UTTERANCE",
        metadata={"trigger_kind": "user_initiated"},
    )

    result = router.route(event)

    assert result.destination == PRESENCE_QUEUE
    assert len(queue) == 0
    assert ambient_state.to_dict() == {}


def test_presence_queue_is_fifo_storage_for_routed_events():
    queue = PresenceQueue()
    first = make_event("USER_UTTERANCE", metadata={"trigger_kind": "user_initiated"})
    second = make_event("USER_CONFIRMATION", metadata={"trigger_kind": "user_initiated"})

    queue.enqueue(first)
    queue.enqueue(second)

    assert len(queue) == 2
    assert queue.dequeue() == first
    assert queue.dequeue() == second
    assert queue.dequeue() is None


def test_ambient_state_can_store_latest_ambient_events():
    state = AmbientState()
    event = make_event("ENVIRONMENT_UPDATE", metadata={"ambient": True})

    state.update(event)

    assert state.latest("ENVIRONMENT_UPDATE") == event
    assert state.to_dict() == {"ENVIRONMENT_UPDATE": event.to_dict()}
