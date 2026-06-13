from datetime import datetime, timezone

from agent import MainAgent
from events import StandardizedEvent


def make_event() -> StandardizedEvent:
    return StandardizedEvent(
        trace_id="trace-handoff-contract",
        source="cli_input",
        timestamp=datetime(2026, 6, 13, 12, 15, tzinfo=timezone.utc),
        payload={"text": "Ella，我要出门了"},
        event_type="USER_UTTERANCE",
        metadata={"trigger_kind": "user_initiated"},
    )


def test_main_agent_handoff_contains_goal_context_and_constraints_only():
    handoff = MainAgent().create_handoff(
        trigger_event=make_event(),
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Mock environment context only.",
    )
    serialized = handoff.to_dict()

    assert "before leaving" in handoff.task_goal
    assert handoff.trigger_event.trace_id == "trace-handoff-contract"
    assert handoff.user_preference_summary == "Prefers concise reminders."
    assert handoff.environment_summary == "Mock environment context only."
    assert handoff.constraints
    assert handoff.completion_criteria
    assert "skill_name" not in serialized
    assert "strategy" not in serialized
    assert "session_id" not in serialized
    assert "task_id" not in serialized
    assert "tool_results" not in serialized


def test_handoff_creation_does_not_execute_or_mutate_the_trigger_event():
    event = make_event()
    before = event.to_dict()

    handoff = MainAgent().create_handoff(
        trigger_event=event,
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Mock environment context only.",
    )

    assert handoff.trigger_event is event
    assert event.to_dict() == before
    assert not hasattr(handoff, "run")
    assert not hasattr(handoff, "execute")
    assert not hasattr(handoff, "tool_registry")
