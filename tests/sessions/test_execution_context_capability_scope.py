from dataclasses import FrozenInstanceError

import pytest

from agent.context import AgentExecutionContext, CapabilityScope


def make_context(
    *,
    capability_scope: CapabilityScope | None = None,
    allowed_tools: tuple[str, ...] = (),
) -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        session_id="session-scope",
        task_id="task-scope",
        trace_id="trace-scope",
        handoff_goal="Complete one scoped task.",
        memory_scope="task_local",
        allowed_tools=allowed_tools,
        permissions=("read_context",),
        capability_scope=capability_scope,
    )


def test_capability_scope_is_an_immutable_task_local_snapshot():
    scope = CapabilityScope(
        agent_role="main_agent",
        allowed_skills=("going_out",),
        allowed_tools=("camera_scene",),
        skill_registry_version=3,
        tool_registry_version=5,
    )

    with pytest.raises(FrozenInstanceError):
        scope.allowed_tools = ("mock_weather",)


def test_context_carries_effective_capability_scope():
    scope = CapabilityScope(
        agent_role="main_agent",
        allowed_skills=("going_out",),
        allowed_tools=("camera_scene", "mock_weather"),
        skill_registry_version=3,
        tool_registry_version=5,
    )

    context = make_context(capability_scope=scope)

    assert context.capability_scope is scope
    assert context.allowed_tools == ("camera_scene", "mock_weather")
    assert context.capability_scope.allowed_skills == ("going_out",)


def test_legacy_allowed_tools_constructor_creates_compatible_scope():
    context = make_context(allowed_tools=("mock_checklist",))

    assert context.allowed_tools == ("mock_checklist",)
    assert context.capability_scope == CapabilityScope(
        agent_role="main_agent",
        allowed_skills=(),
        allowed_tools=("mock_checklist",),
    )


def test_scope_role_must_match_context_role():
    scope = CapabilityScope(
        agent_role="specialist_agent",
        allowed_skills=(),
        allowed_tools=(),
    )

    with pytest.raises(ValueError, match="agent role"):
        make_context(capability_scope=scope)


def test_conflicting_legacy_tools_and_scope_are_rejected():
    scope = CapabilityScope(
        agent_role="main_agent",
        allowed_skills=(),
        allowed_tools=("camera_scene",),
    )

    with pytest.raises(ValueError, match="allowed_tools"):
        make_context(
            capability_scope=scope,
            allowed_tools=("mock_weather",),
        )


def test_context_serialization_includes_capability_scope_and_legacy_tools():
    context = make_context(
        capability_scope=CapabilityScope(
            agent_role="main_agent",
            allowed_skills=("going_out",),
            allowed_tools=("camera_scene",),
            skill_registry_version=7,
            tool_registry_version=11,
        )
    )

    serialized = context.to_dict()

    assert serialized["allowed_tools"] == ("camera_scene",)
    assert serialized["capability_scope"] == {
        "agent_role": "main_agent",
        "allowed_skills": ("going_out",),
        "allowed_tools": ("camera_scene",),
        "skill_registry_version": 7,
        "tool_registry_version": 11,
    }


def test_scope_contains_no_process_managers_or_registries():
    scope = CapabilityScope(
        agent_role="main_agent",
        allowed_skills=(),
        allowed_tools=(),
    )

    assert not hasattr(scope, "skill_manager")
    assert not hasattr(scope, "tool_manager")
    assert not hasattr(scope, "skill_registry")
    assert not hasattr(scope, "tool_registry")
