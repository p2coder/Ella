from datetime import datetime, timezone
from pathlib import Path

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from sessions.decision import CALL_TOOL, ExecutionDecision
from sessions.session_manager import TaskSessionManager
from sessions.subagent import SubAgent
from skill import SkillDefinition, SkillManager


FIXED_TIME = datetime(2026, 6, 13, 17, 0, tzinfo=timezone.utc)


def make_handoff(*, visual: bool) -> HandoffRequest:
    text = "Ella，看看当前画面里我有没有带伞，我要出门了" if visual else "Ella，我要出门了"
    return HandoffRequest(
        task_goal=(
            "Use the current camera view to give a short reminder before leaving."
            if visual
            else "Give the user a short, necessary reminder before leaving."
        ),
        trigger_event=StandardizedEvent(
            trace_id="trace-visual-decision",
            source="cli_input",
            timestamp=FIXED_TIME,
            payload={"text": text},
            event_type="USER_UTTERANCE",
            metadata={"trigger_kind": "user_initiated"},
        ),
        user_preference_summary="Prefers concise reminders.",
        environment_summary=(
            "The user explicitly requested current visual context."
            if visual
            else "No interpreted visual summary yet."
        ),
        context_summary=(
            "The user asked Ella to look at the current scene before leaving."
            if visual
            else "User said they are about to leave."
        ),
        constraints=("Keep the reminder short and necessary.",),
        completion_criteria=("A concise reminder is ready.",),
    )


def make_subagent() -> SubAgent:
    manager = SkillManager()
    manager.register(
        SkillDefinition(
            name="going_out",
            description="Prepare a reminder when the user is leaving.",
            when_to_use=(
                "Use when the user is heading out; request camera_scene only "
                "when current visual context is explicitly needed."
            ),
            path=Path("skill/skills/going_out/SKILL.md"),
        )
    )
    return SubAgent(manager)


def make_creation(*, visual: bool):
    return TaskSessionManager(
        allowed_tools=(
            "camera_scene",
            "mock_vision_summary",
            "mock_weather",
            "mock_checklist",
        ),
        session_id_factory=lambda: "session-visual-decision",
        task_id_factory=lambda: "task-visual-decision",
    ).create_session(make_handoff(visual=visual))


def decide(*, visual: bool) -> ExecutionDecision:
    creation = make_creation(visual=visual)
    subagent = make_subagent()
    strategy = subagent.select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )
    return subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        strategy,
    )


def test_visual_going_out_request_produces_camera_scene_call():
    decision = decide(visual=True)

    assert isinstance(decision, ExecutionDecision)
    assert decision.action == CALL_TOOL
    assert decision.tool_name == "camera_scene"
    assert decision.tool_input["task_goal"].startswith("Use the current camera")
    assert decision.is_complete is False


def test_non_visual_going_out_request_does_not_call_camera_scene():
    decision = decide(visual=False)

    assert decision.action == CALL_TOOL
    assert decision.tool_name == "mock_vision_summary"


def test_visual_decision_is_single_and_does_not_execute_tool():
    creation = make_creation(visual=True)
    subagent = make_subagent()
    strategy = subagent.select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )
    before_trace = creation.session.tool_trace

    decision = subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        strategy,
    )

    assert isinstance(decision, ExecutionDecision)
    assert creation.session.tool_trace == before_trace
    assert not hasattr(subagent, "tool_manager")
    assert not hasattr(subagent, "executor")


def test_camera_scene_completion_advances_to_existing_sequence():
    creation = make_creation(visual=True)
    creation.session.tool_trace = (
        {"tool_name": "camera_scene", "payload": {"status": "available"}},
    )
    subagent = make_subagent()
    strategy = subagent.select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )

    decision = subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        strategy,
    )

    assert decision.tool_name == "mock_weather"


def test_no_global_tool_registration_is_required():
    source = Path("sessions/subagent.py").read_text(encoding="utf-8")

    assert "ToolManager" not in source
    assert ".register(" not in source
