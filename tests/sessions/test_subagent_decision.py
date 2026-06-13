from datetime import datetime, timezone
from pathlib import Path

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from sessions.decision import CALL_TOOL, COMPLETE, ExecutionDecision
from sessions.session_manager import TaskSessionManager
from sessions.strategy import StrategyDecision
from sessions.subagent import SubAgent
from skill import SkillDefinition, SkillManager


FIXED_TIME = datetime(2026, 6, 13, 14, 0, tzinfo=timezone.utc)


def make_handoff() -> HandoffRequest:
    event = StandardizedEvent(
        trace_id="trace-subagent-decision",
        source="cli_input",
        timestamp=FIXED_TIME,
        payload={"text": "Ella，我要出门了"},
        event_type="USER_UTTERANCE",
        metadata={"trigger_kind": "user_initiated"},
    )
    return HandoffRequest(
        task_goal="Give the user a short, necessary reminder before leaving.",
        trigger_event=event,
        user_preference_summary="Prefers concise reminders.",
        environment_summary="No interpreted visual summary yet.",
        context_summary="User said they are about to leave.",
        constraints=("Keep the reminder short and necessary.",),
        completion_criteria=("A concise reminder is ready.",),
    )


def make_subagent() -> SubAgent:
    manager = SkillManager()
    manager.register(
        SkillDefinition(
            name="going_out",
            description="Mock skill for preparing a short reminder when the user is leaving.",
            when_to_use="Use when the user says they are heading out.",
            path=Path("skill/skills/going_out/SKILL.md"),
        )
    )
    return SubAgent(skill_manager=manager)


def make_session_creation():
    return TaskSessionManager(
        allowed_tools=(
            "mock_vision_summary",
            "mock_weather",
            "mock_checklist",
        ),
        session_id_factory=lambda: "session-subagent-decision",
        task_id_factory=lambda: "task-subagent-decision",
    ).create_session(make_handoff())


def select_going_out_strategy(
    subagent: SubAgent,
    creation,
) -> StrategyDecision:
    return subagent.select_strategy(
        handoff=creation.session.handoff,
        context=creation.context,
        task_session=creation.session,
    )


def test_subagent_returns_execution_decision_for_going_out_task():
    creation = make_session_creation()
    subagent = make_subagent()
    strategy = select_going_out_strategy(subagent, creation)

    decision = subagent.decide_next_action(
        handoff=creation.session.handoff,
        context=creation.context,
        task_session=creation.session,
        strategy=strategy,
    )

    assert isinstance(decision, ExecutionDecision)
    assert decision.action == CALL_TOOL
    assert decision.tool_name == "mock_vision_summary"
    assert decision.is_complete is False


def test_going_out_decision_advances_deterministically_from_tool_trace():
    creation = make_session_creation()
    subagent = make_subagent()
    strategy = select_going_out_strategy(subagent, creation)
    creation.session.tool_trace = (
        {"tool_name": "mock_vision_summary", "payload": {}},
    )

    decision = subagent.decide_next_action(
        handoff=creation.session.handoff,
        context=creation.context,
        task_session=creation.session,
        strategy=strategy,
    )

    assert decision.action == CALL_TOOL
    assert decision.tool_name == "mock_weather"


def test_going_out_decision_completes_after_required_tool_trace():
    creation = make_session_creation()
    subagent = make_subagent()
    strategy = select_going_out_strategy(subagent, creation)
    creation.session.tool_trace = tuple(
        {"tool_name": tool_name, "payload": {}}
        for tool_name in (
            "mock_vision_summary",
            "mock_weather",
            "mock_checklist",
        )
    )

    decision = subagent.decide_next_action(
        handoff=creation.session.handoff,
        context=creation.context,
        task_session=creation.session,
        strategy=strategy,
    )

    assert decision.action == COMPLETE
    assert decision.tool_name is None
    assert decision.is_complete is True


def test_subagent_decision_does_not_execute_tools_or_mutate_session():
    creation = make_session_creation()
    subagent = make_subagent()
    strategy = select_going_out_strategy(subagent, creation)
    session = creation.session
    before = (
        session.state,
        dict(session.task_local_state),
        session.message_history,
        session.tool_trace,
        session.current_strategy,
        session.completion,
        session.failure_reason,
    )

    subagent.decide_next_action(
        handoff=session.handoff,
        context=creation.context,
        task_session=session,
        strategy=strategy,
    )

    after = (
        session.state,
        dict(session.task_local_state),
        session.message_history,
        session.tool_trace,
        session.current_strategy,
        session.completion,
        session.failure_reason,
    )
    assert after == before
    assert not hasattr(subagent, "tool_manager")


def test_existing_select_strategy_behavior_still_selects_going_out():
    creation = make_session_creation()
    strategy = select_going_out_strategy(make_subagent(), creation)

    assert strategy.mode == "skill"
    assert strategy.skill_name == "going_out"
