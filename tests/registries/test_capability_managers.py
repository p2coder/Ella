from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from events import StandardizedEvent
from sessions import CapabilityExecutor, SubAgent, TaskSessionManager
from skill import SkillDefinition, SkillLoader, SkillManager
from tools import (
    CapabilityUnavailableError,
    MockChecklistTool,
    ToolManager,
)


def make_handoff() -> HandoffRequest:
    event = StandardizedEvent(
        trace_id="trace-hot-plug",
        source="cli_input",
        timestamp=datetime(2026, 6, 13, 16, 0, tzinfo=timezone.utc),
        payload={"text": "Ella，我要出门了"},
        event_type="USER_UTTERANCE",
        metadata={"trigger_kind": "user_initiated"},
    )
    return HandoffRequest(
        task_goal="Give the user a short, necessary reminder before leaving.",
        trigger_event=event,
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Mock environment context only.",
        context_summary="User is preparing to leave.",
        constraints=("Keep the reminder concise.",),
        completion_criteria=("A reminder is ready.",),
    )


def make_creation():
    return TaskSessionManager(
        allowed_tools=("mock_checklist",),
        session_id_factory=lambda: "session-hot-plug",
        task_id_factory=lambda: "task-hot-plug",
    ).create_session(make_handoff())


def going_out_skill() -> SkillDefinition:
    return SkillDefinition(
        name="going_out",
        description="Prepare a reminder when the user is leaving.",
        when_to_use="Use when the user is heading out.",
        path=Path("skill/skills/going_out/SKILL.md"),
    )


def test_current_session_discovers_skill_registered_after_session_creation():
    creation = make_creation()
    manager = SkillManager()
    subagent = SubAgent(manager)

    before = subagent.select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )
    manager.register(going_out_skill())
    after = subagent.select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )

    assert before.mode == "plan_to_execute"
    assert after.mode == "skill"
    assert after.skill_name == "going_out"


def test_skill_manager_refresh_adds_and_removes_skill_files(tmp_path: Path):
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "temporary"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\n"
        "name: temporary\n"
        "description: Temporary runtime skill.\n"
        "when_to_use: Use for a temporary capability.\n"
        "---\n"
        "\n"
        "# temporary\n",
        encoding="utf-8",
    )
    manager = SkillManager(loader=SkillLoader(skills_root))

    manager.refresh()
    added_version = manager.version
    assert manager.get_summary("temporary") is not None

    skill_file.unlink()
    manager.refresh()

    assert manager.get_summary("temporary") is None
    assert manager.version == added_version + 1


def test_removed_skill_causes_current_session_to_replan():
    creation = make_creation()
    manager = SkillManager()
    manager.register(going_out_skill())
    subagent = SubAgent(manager)
    selected = subagent.select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )

    manager.unregister("going_out")
    replanned = subagent.replan_if_unavailable(
        selected,
        creation.session.handoff,
        creation.context,
        creation.session,
    )

    assert selected.skill_name == "going_out"
    assert replanned.mode == "plan_to_execute"
    assert replanned.skill_name is None


def test_current_session_can_use_tool_registered_after_session_creation():
    creation = make_creation()
    manager = ToolManager()

    manager.register(MockChecklistTool())
    result = manager.execute("mock_checklist", creation.context)

    assert result.session_id == creation.context.session_id
    assert result.payload["items"] == ("phone", "keys", "wallet", "umbrella")


def test_removed_tool_is_rejected_before_next_execution():
    creation = make_creation()
    manager = ToolManager()
    manager.register(MockChecklistTool())
    manager.unregister("mock_checklist")

    with pytest.raises(CapabilityUnavailableError, match="not registered"):
        manager.execute("mock_checklist", creation.context)


def test_tool_outside_context_allowlist_is_rejected():
    context = AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        session_id="session-denied",
        task_id="task-denied",
        trace_id="trace-denied",
        handoff_goal="Prepare a reminder.",
        memory_scope="task_local",
        allowed_tools=(),
        permissions=(),
    )
    manager = ToolManager()
    manager.register(MockChecklistTool())

    with pytest.raises(CapabilityUnavailableError, match="not allowed"):
        manager.execute("mock_checklist", context)


def test_executor_replans_when_selected_skill_was_removed():
    creation = make_creation()
    skill_manager = SkillManager()
    skill_manager.register(going_out_skill())
    subagent = SubAgent(skill_manager)
    selected = subagent.select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )
    skill_manager.unregister("going_out")

    result = CapabilityExecutor(
        subagent=subagent,
        skill_manager=skill_manager,
        tool_manager=ToolManager(),
    ).execute(
        selected,
        creation.session.handoff,
        creation.context,
        creation.session,
    )

    assert result.replanned is True
    assert result.strategy.mode == "plan_to_execute"
    assert result.strategy.skill_name is None


def test_executor_replans_when_allowed_tool_was_removed():
    creation = make_creation()
    skill_manager = SkillManager()
    skill_manager.register(going_out_skill())
    tool_manager = ToolManager()
    tool_manager.register(MockChecklistTool())
    subagent = SubAgent(skill_manager)
    selected = subagent.select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )
    tool_manager.unregister("mock_checklist")

    result = CapabilityExecutor(
        subagent=subagent,
        skill_manager=skill_manager,
        tool_manager=tool_manager,
    ).execute(
        selected,
        creation.session.handoff,
        creation.context,
        creation.session,
    )

    assert result.replanned is True
    assert result.unavailable_tools == ("mock_checklist",)
    assert result.tool_results == ()
