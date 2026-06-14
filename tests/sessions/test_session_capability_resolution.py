from datetime import datetime, timezone
from pathlib import Path

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from sessions.session_manager import TaskSessionManager
from skill.manager import SkillManager
from skill.registry import SkillDefinition
from tools.manager import ToolManager
from tools.mock_tools import MockChecklistTool, MockWeatherTool


FIXED_TIME = datetime(2026, 6, 14, 10, 0, tzinfo=timezone.utc)


def make_handoff(trace_id: str = "trace-capability-scope") -> HandoffRequest:
    return HandoffRequest(
        task_goal="Give the user a short reminder before leaving.",
        trigger_event=StandardizedEvent(
            trace_id=trace_id,
            source="cli_input",
            timestamp=FIXED_TIME,
            payload={"text": "Ella，我要出门了"},
            event_type="USER_UTTERANCE",
            metadata={"trigger_kind": "user_initiated"},
        ),
        user_preference_summary="Prefers concise reminders.",
        environment_summary="No interpreted visual summary yet.",
        context_summary="User is about to leave.",
        constraints=("Keep the reminder short.",),
        completion_criteria=("A concise reminder is ready.",),
    )


def make_skill(
    name: str,
    allowed_roles: tuple[str, ...] = ("main_agent",),
) -> SkillDefinition:
    return SkillDefinition(
        name=name,
        description=f"{name} description",
        when_to_use=f"Use {name} when appropriate.",
        path=Path(f"/skills/{name}/SKILL.md"),
        allowed_roles=allowed_roles,
    )


def make_manager(
    skill_manager: SkillManager,
    tool_manager: ToolManager,
    *,
    agent_role: str = "main_agent",
) -> TaskSessionManager:
    return TaskSessionManager(
        agent_role=agent_role,
        skill_manager=skill_manager,
        tool_manager=tool_manager,
        session_id_factory=iter(("session-1", "session-2")).__next__,
        task_id_factory=iter(("task-1", "task-2")).__next__,
    )


def test_create_session_resolves_role_visible_capabilities_and_versions():
    skill_manager = SkillManager()
    skill_manager.register(make_skill("going_out"))
    skill_manager.register(make_skill("specialist_only", ("specialist",)))
    tool_manager = ToolManager()
    tool_manager.register(MockChecklistTool())
    tool_manager.register(MockWeatherTool(allowed_roles=("specialist",)))

    creation = make_manager(skill_manager, tool_manager).create_session(
        make_handoff()
    )

    scope = creation.context.capability_scope
    assert scope.agent_role == "main_agent"
    assert scope.allowed_skills == ("going_out",)
    assert scope.allowed_tools == ("mock_checklist",)
    assert scope.skill_registry_version == skill_manager.version
    assert scope.tool_registry_version == tool_manager.version


def test_new_registrations_affect_new_sessions_but_not_existing_scope():
    skill_manager = SkillManager()
    tool_manager = ToolManager()
    manager = make_manager(skill_manager, tool_manager)

    first = manager.create_session(make_handoff("trace-first")).context
    skill_manager.register(make_skill("going_out"))
    tool_manager.register(MockChecklistTool())
    second = manager.create_session(make_handoff("trace-second")).context

    assert first.capability_scope.allowed_skills == ()
    assert first.capability_scope.allowed_tools == ()
    assert first.capability_scope.skill_registry_version == 0
    assert first.capability_scope.tool_registry_version == 0
    assert second.capability_scope.allowed_skills == ("going_out",)
    assert second.capability_scope.allowed_tools == ("mock_checklist",)
    assert second.capability_scope.skill_registry_version == 1
    assert second.capability_scope.tool_registry_version == 1


def test_session_capability_resolution_uses_configured_agent_role():
    skill_manager = SkillManager()
    skill_manager.register(make_skill("main_only"))
    skill_manager.register(make_skill("specialist_only", ("specialist",)))
    tool_manager = ToolManager()
    tool_manager.register(MockChecklistTool())
    tool_manager.register(MockWeatherTool(allowed_roles=("specialist",)))

    context = make_manager(
        skill_manager,
        tool_manager,
        agent_role="specialist",
    ).create_session(make_handoff()).context

    assert context.capability_scope.allowed_skills == ("specialist_only",)
    assert context.capability_scope.allowed_tools == ("mock_weather",)


def test_legacy_allowed_tools_remain_compatible_without_managers():
    context = TaskSessionManager(
        allowed_tools=("legacy_tool",),
        session_id_factory=lambda: "legacy-session",
        task_id_factory=lambda: "legacy-task",
    ).create_session(make_handoff()).context

    assert context.allowed_tools == ("legacy_tool",)
    assert context.capability_scope.allowed_skills == ()
    assert context.capability_scope.skill_registry_version is None
    assert context.capability_scope.tool_registry_version is None
