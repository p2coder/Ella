from datetime import datetime, timezone

from events import StandardizedEvent
from runtime.interruption_policy import (
    InterruptionDecision,
    InterruptionPolicy,
)


FIXED_TIME = datetime(2026, 6, 13, 11, 0, tzinfo=timezone.utc)


def make_event(event_type: str, metadata: dict | None = None) -> StandardizedEvent:
    return StandardizedEvent(
        task_id=f"task-{event_type.lower()}",
        source="test",
        timestamp=FIXED_TIME,
        payload={"text": "Ella，我要出门了"},
        event_type=event_type,
        confidence=1.0,
        metadata=metadata or {},
    )


def test_policy_allows_user_initiated_utterance():
    policy = InterruptionPolicy()
    event = make_event(
        "USER_UTTERANCE",
        {"trigger_kind": "user_initiated"},
    )

    decision = policy.evaluate(event)

    assert decision == InterruptionDecision(
        allowed=True,
        reason="user initiated event",
    )


def test_policy_allows_user_utterance_even_without_trigger_metadata():
    policy = InterruptionPolicy()
    event = make_event("USER_UTTERANCE")

    decision = policy.evaluate(event)

    assert decision.allowed is True
    assert decision.reason == "user initiated event"


def test_policy_suppresses_marked_events():
    policy = InterruptionPolicy()
    event = make_event("USER_UTTERANCE", {"suppress": True})

    decision = policy.evaluate(event)

    assert decision.allowed is False
    assert decision.reason == "event marked as suppressed"


def test_policy_rejects_noise_and_ambient_events():
    policy = InterruptionPolicy()

    noise_decision = policy.evaluate(make_event("BACKGROUND_NOISE"))
    ambient_decision = policy.evaluate(
        make_event("ENVIRONMENT_UPDATE", {"ambient": True})
    )

    assert noise_decision.allowed is False
    assert noise_decision.reason == "event should not interrupt"
    assert ambient_decision.allowed is False
    assert ambient_decision.reason == "ambient event should not interrupt"
