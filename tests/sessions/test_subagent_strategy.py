from datetime import datetime, timezone
from pathlib import Path

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from sessions import TaskSessionManager
from sessions.strategy import StrategyDecision
from sessions.subagent import SubAgent
from skill import SkillDefinition, SkillManager


FIXED_TIME = datetime(2026, 6, 13, 14, 0, tzinfo=timezone.utc)


def make_handoff(
    task_goal: str,
    trigger_text: str = "Ella，我要出门了",
) -> HandoffRequest:
    event = StandardizedEvent(
        trace_id="trace-subagent",
        source="cli_input",
        timestamp=FIXED_TIME,
        payload={"text": trigger_text},
        event_type="USER_UTTERANCE",
        metadata={"trigger_kind": "user_initiated"},
    )
    return HandoffRequest(
        task_goal=task_goal,
        trigger_event=event,
        user_preference_summary="Prefers concise reminders.",
        environment_summary="No interpreted visual summary yet.",
        context_summary="User said they are about to leave.",
        constraints=("Keep the reminder short and necessary.",),
        completion_criteria=("A reminder strategy is selected.",),
    )


def make_manager() -> SkillManager:
    manager = SkillManager()
    manager.register(
        SkillDefinition(
            name="going_out",
            description="Mock skill for preparing a short reminder when the user is leaving.",
            when_to_use="Use when the user says they are heading out.",
            path=Path("skill/skills/going_out/SKILL.md"),
        )
    )
    return manager


def make_session_creation(
    task_goal: str,
    trigger_text: str = "Ella，我要出门了",
):
    return TaskSessionManager(
        session_id_factory=lambda: "session-subagent",
        task_id_factory=lambda: "task-subagent",
    ).create_session(make_handoff(task_goal, trigger_text))


def test_subagent_selects_going_out_skill_for_leaving_goal():
    creation = make_session_creation(
        "Give the user a short, necessary reminder before leaving."
    )
    subagent = SubAgent(skill_manager=make_manager())

    decision = subagent.select_strategy(
        handoff=creation.session.handoff,
        context=creation.context,
        task_session=creation.session,
    )

    assert decision == StrategyDecision(
        mode="skill",
        skill_name="going_out",
        reason="Task goal matches the going-out reminder skill metadata.",
        initial_plan=None,
        completion_criteria=creation.session.handoff.completion_criteria,
        session_id="session-subagent",
        task_id="task-subagent",
        trace_id="trace-subagent",
    )


def test_subagent_keeps_going_out_intent_when_llm_goal_is_chinese():
    creation = make_session_creation("在用户出门前给出简短且必要的提醒。")
    subagent = SubAgent(skill_manager=make_manager())

    decision = subagent.select_strategy(
        handoff=creation.session.handoff,
        context=creation.context,
        task_session=creation.session,
    )

    assert decision.mode == "skill"
    assert decision.skill_name == "going_out"


def test_subagent_accepts_execution_context_and_task_session():
    creation = make_session_creation(
        "Give the user a short, necessary reminder before leaving."
    )

    decision = SubAgent(skill_manager=make_manager()).select_strategy(
        handoff=creation.session.handoff,
        context=creation.context,
        task_session=creation.session,
    )

    assert decision.session_id == "session-subagent"
    assert decision.task_id == "task-subagent"
    assert decision.trace_id == "trace-subagent"


def test_strategy_selection_falls_back_without_skill_execution():
    creation = make_session_creation(
        "Clarify and prepare a concise response.",
        trigger_text="Ella，帮我整理一下今天的计划。",
    )
    subagent = SubAgent(skill_manager=make_manager())

    decision = subagent.select_strategy(
        handoff=creation.session.handoff,
        context=creation.context,
        task_session=creation.session,
    )

    assert decision.mode == "plan_to_execute"
    assert decision.skill_name is None
    assert decision.initial_plan == ("Clarify the task before execution.",)


def test_subagent_does_not_call_tools_or_generate_outputs():
    creation = make_session_creation(
        "Give the user a short, necessary reminder before leaving."
    )
    subagent = SubAgent(skill_manager=make_manager())

    decision = subagent.select_strategy(
        handoff=creation.session.handoff,
        context=creation.context,
        task_session=creation.session,
    )

    assert not hasattr(subagent, "tool_registry")
    assert not hasattr(subagent, "run_tools")
    assert not hasattr(decision, "task_completion_package")
    assert not hasattr(decision, "user_visible_output")
