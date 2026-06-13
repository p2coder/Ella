from datetime import datetime, timezone

from agent import MainAgent, TaskFormulator
from agent.formulation import TaskFormulation
from events import StandardizedEvent


FIXED_TIME = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def make_user_event(text: str) -> StandardizedEvent:
    return StandardizedEvent(
        trace_id="trace-going-out",
        source="cli_input",
        timestamp=FIXED_TIME,
        payload={"text": text},
        event_type="USER_UTTERANCE",
        confidence=1.0,
        priority=0.9,
        metadata={"trigger_kind": "user_initiated"},
    )


def test_formulation_creates_pre_leaving_reminder_goal():
    event = make_user_event("Ella，我要出门了")
    formulator = TaskFormulator()

    formulation = formulator.formulate(
        trigger_event=event,
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Current visible scene is available as context.",
        current_agent_input="Ella，我要出门了",
    )

    assert isinstance(formulation, TaskFormulation)
    assert formulation.goal == "Give the user a short, necessary reminder before leaving."
    assert formulation.user_preference_summary == "Prefers concise reminders."
    assert formulation.environment_summary == "Current visible scene is available as context."
    assert formulation.context_summary == "User said they are about to leave."
    assert formulation.constraints == (
        "Keep the reminder short and necessary.",
        "Use only the provided input, preference summary, and environment summary.",
        "Do not choose a skill or execution strategy.",
    )
    assert formulation.completion_criteria == (
        "A concise pre-leaving reminder goal is ready for handoff.",
    )


def test_formulation_answers_what_should_be_done_only():
    formulation = TaskFormulator().formulate(
        trigger_event=make_user_event("Ella，我要出门了"),
        user_preference_summary="",
        environment_summary="",
    )

    assert not hasattr(formulation, "skill_name")
    assert not hasattr(formulation, "execution_strategy")
    assert "going_out" not in formulation.goal


def test_main_agent_receives_allowed_event_and_returns_handoff_shell():
    event = make_user_event("Ella，我要出门了")
    agent = MainAgent()

    handoff = agent.create_handoff(
        trigger_event=event,
        user_preference_summary="Prefers concise reminders.",
        environment_summary="No interpreted visual summary yet.",
    )

    assert handoff.task_goal == "Give the user a short, necessary reminder before leaving."
    assert handoff.trigger_event == event
    assert not hasattr(agent, "task_session_manager")
    assert not hasattr(handoff, "agent_execution_context")
