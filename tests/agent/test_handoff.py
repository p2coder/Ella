from datetime import datetime, timezone

from agent import HandoffRequest, TaskFormulation
from events import StandardizedEvent


FIXED_TIME = datetime(2026, 6, 13, 12, 30, tzinfo=timezone.utc)


def make_event() -> StandardizedEvent:
    return StandardizedEvent(
        trace_id="trace-handoff",
        source="cli_input",
        timestamp=FIXED_TIME,
        payload={"text": "Ella，我要出门了"},
        event_type="USER_UTTERANCE",
        metadata={"trigger_kind": "user_initiated"},
    )


def test_handoff_request_packages_formulation_context_and_trigger_event():
    event = make_event()
    formulation = TaskFormulation(
        goal="Give the user a short, necessary reminder before leaving.",
        constraints=("Keep the reminder short and necessary.",),
        context_summary="User said they are about to leave.",
        user_preference_summary="Prefers concise reminders.",
        environment_summary="No interpreted visual summary yet.",
        completion_criteria=("A reminder goal is ready for handoff.",),
    )

    handoff = HandoffRequest.from_formulation(
        formulation=formulation,
        trigger_event=event,
    )

    assert handoff.task_goal == formulation.goal
    assert handoff.trigger_event == event
    assert handoff.user_preference_summary == "Prefers concise reminders."
    assert handoff.environment_summary == "No interpreted visual summary yet."
    assert handoff.context_summary == "User said they are about to leave."
    assert handoff.constraints == ("Keep the reminder short and necessary.",)
    assert handoff.completion_criteria == ("A reminder goal is ready for handoff.",)


def test_handoff_request_serializes_without_execution_fields():
    event = make_event()
    handoff = HandoffRequest(
        task_goal="Give the user a short, necessary reminder before leaving.",
        trigger_event=event,
        user_preference_summary="Prefers concise reminders.",
        environment_summary="No interpreted visual summary yet.",
        context_summary="User said they are about to leave.",
        constraints=("Keep the reminder short and necessary.",),
        completion_criteria=("A reminder goal is ready for handoff.",),
    )

    serialized = handoff.to_dict()

    assert serialized["task_goal"] == "Give the user a short, necessary reminder before leaving."
    assert serialized["trigger_event"] == event.to_dict()
    assert "skill_name" not in serialized
    assert "task_session" not in serialized
    assert "agent_execution_context" not in serialized
