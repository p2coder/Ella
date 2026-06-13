from datetime import datetime, timezone

from events import StandardizedEvent
from runtime.event_queue import PresenceQueue
from runtime.presence_runtime import PresenceRuntime, PresenceRuntimeResult


FIXED_TIME = datetime(2026, 6, 13, 11, 30, tzinfo=timezone.utc)


def make_event(event_type: str, metadata: dict | None = None) -> StandardizedEvent:
    return StandardizedEvent(
        trace_id=f"trace-{event_type.lower()}",
        source="test",
        timestamp=FIXED_TIME,
        payload={"text": "Ella，我要出门了"},
        event_type=event_type,
        confidence=1.0,
        metadata=metadata or {},
    )


def test_presence_runtime_consumes_presence_queue_events():
    queue = PresenceQueue()
    allowed_event = make_event(
        "USER_UTTERANCE",
        {"trigger_kind": "user_initiated"},
    )
    suppressed_event = make_event("BACKGROUND_NOISE")
    queue.enqueue(allowed_event)
    queue.enqueue(suppressed_event)
    forwarded_events = []
    runtime = PresenceRuntime(
        presence_queue=queue,
        next_boundary=forwarded_events.append,
    )

    result = runtime.process_available()

    assert result == PresenceRuntimeResult(
        consumed_count=2,
        allowed_count=1,
        suppressed_count=1,
    )
    assert len(queue) == 0
    assert forwarded_events == [allowed_event]


def test_presence_runtime_passes_allowed_events_to_next_boundary_only():
    queue = PresenceQueue()
    allowed_event = make_event("USER_UTTERANCE")
    suppressed_event = make_event("USER_UTTERANCE", {"suppress": True})
    queue.enqueue(allowed_event)
    queue.enqueue(suppressed_event)
    forwarded_events = []
    runtime = PresenceRuntime(queue, next_boundary=forwarded_events.append)

    result = runtime.process_available()

    assert result.allowed_count == 1
    assert result.suppressed_count == 1
    assert forwarded_events == [allowed_event]


def test_presence_runtime_does_not_poll_world_or_external_inputs():
    queue = PresenceQueue()
    runtime = PresenceRuntime(queue)

    result = runtime.process_available()

    assert result == PresenceRuntimeResult(
        consumed_count=0,
        allowed_count=0,
        suppressed_count=0,
    )
    assert len(queue) == 0


def test_suppressed_events_do_not_trigger_next_boundary():
    queue = PresenceQueue()
    queue.enqueue(make_event("BACKGROUND_NOISE"))

    def fail_if_called(event):
        raise AssertionError(f"unexpected task boundary call: {event}")

    runtime = PresenceRuntime(queue, next_boundary=fail_if_called)

    result = runtime.process_available()

    assert result.suppressed_count == 1
