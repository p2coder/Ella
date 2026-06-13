from datetime import datetime, timezone

from agent import MainAgent
from events import StandardizedEvent
from sessions import SubAgent, TaskSessionManager
from skill import SkillLoader, SkillManager


FIXED_TIME = datetime(2026, 6, 13, 15, 0, tzinfo=timezone.utc)


def make_handoff():
    event = StandardizedEvent(
        trace_id="trace-controlled-autonomy",
        source="cli_input",
        timestamp=FIXED_TIME,
        payload={"text": "Ella，我要出门了"},
        event_type="USER_UTTERANCE",
        metadata={"trigger_kind": "user_initiated"},
    )
    return MainAgent().create_handoff(
        trigger_event=event,
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Mock environment context only.",
    )


def make_creation():
    return TaskSessionManager(
        allowed_tools=("mock_weather", "mock_checklist"),
        permissions=("read_mock_context",),
        session_id_factory=lambda: "session-controlled-autonomy",
        task_id_factory=lambda: "task-controlled-autonomy",
    ).create_session(make_handoff())


def test_main_agent_forms_a_goal_without_preselecting_a_workflow():
    handoff = make_handoff()
    serialized = handoff.to_dict()

    assert handoff.task_goal == (
        "Give the user a short, necessary reminder before leaving."
    )
    assert "skill_name" not in serialized
    assert "strategy" not in serialized
    assert "workflow" not in serialized
    assert "tool_names" not in serialized


def test_same_goal_selects_strategy_from_available_capabilities():
    creation = make_creation()
    available_skills = SkillManager(loader=SkillLoader())
    available_skills.refresh()

    skill_decision = SubAgent(available_skills).select_strategy(
        handoff=creation.session.handoff,
        context=creation.context,
        task_session=creation.session,
    )
    fallback_decision = SubAgent(SkillManager()).select_strategy(
        handoff=creation.session.handoff,
        context=creation.context,
        task_session=creation.session,
    )

    assert skill_decision.mode == "skill"
    assert skill_decision.skill_name == "going_out"
    assert fallback_decision.mode == "plan_to_execute"
    assert fallback_decision.skill_name is None


def test_strategy_decision_stays_inside_execution_context_boundaries():
    creation = make_creation()
    registry = SkillManager(loader=SkillLoader())
    registry.refresh()

    decision = SubAgent(registry).select_strategy(
        handoff=creation.session.handoff,
        context=creation.context,
        task_session=creation.session,
    )

    assert decision.session_id == creation.context.session_id
    assert decision.task_id == creation.context.task_id
    assert decision.trace_id == creation.context.trace_id
    assert creation.context.allowed_tools == ("mock_weather", "mock_checklist")
    assert creation.context.permissions == ("read_mock_context",)


def test_strategy_selection_does_not_execute_tools_or_create_output():
    creation = make_creation()
    registry = SkillManager(loader=SkillLoader())
    registry.refresh()
    subagent = SubAgent(registry)

    decision = subagent.select_strategy(
        handoff=creation.session.handoff,
        context=creation.context,
        task_session=creation.session,
    )

    assert not hasattr(subagent, "tool_registry")
    assert not hasattr(subagent, "run_tools")
    assert not hasattr(decision, "tool_results")
    assert not hasattr(decision, "user_visible_output")
