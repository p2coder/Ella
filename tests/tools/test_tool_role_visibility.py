from dataclasses import FrozenInstanceError, dataclass

import pytest

from agent.context import AgentExecutionContext
from tools import (
    CapabilityUnavailableError,
    MockChecklistTool,
    MockVisionSummaryTool,
    MockWeatherTool,
    ToolManager,
    ToolResult,
)
from tools.camera_scene import CameraSceneTool


def make_context(
    *,
    agent_role: str = "main_agent",
    allowed_tools: tuple[str, ...] = ("role_limited",),
) -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role=agent_role,
        parent_agent_id=None,
        session_id="session-role",
        task_id="task-role",
        trace_id="trace-role",
        handoff_goal="Use an allowed capability.",
        memory_scope="task_local",
        allowed_tools=allowed_tools,
        permissions=(),
    )


@dataclass(frozen=True, slots=True)
class RoleLimitedTool:
    name: str = "role_limited"
    allowed_roles: tuple[str, ...] = ("specialist_agent",)

    def run(self, context: AgentExecutionContext) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            session_id=context.session_id,
            trace_id=context.trace_id,
            payload={"agent_role": context.agent_role},
        )


def test_existing_tools_default_to_main_agent_visibility():
    tools = (
        MockWeatherTool(),
        MockVisionSummaryTool(),
        MockChecklistTool(),
        CameraSceneTool(),
    )

    assert all(tool.allowed_roles == ("main_agent",) for tool in tools)


def test_tool_role_metadata_is_immutable():
    tool = RoleLimitedTool()

    with pytest.raises(FrozenInstanceError):
        tool.allowed_roles = ("main_agent",)


def test_manager_lists_and_resolves_only_tools_visible_to_role():
    manager = ToolManager()
    main_tool = MockChecklistTool()
    specialist_tool = RoleLimitedTool()
    manager.register(main_tool)
    manager.register(specialist_tool)

    assert manager.list_names_for_role("main_agent") == ("mock_checklist",)
    assert manager.list_names_for_role("specialist_agent") == ("role_limited",)
    assert manager.get_for_role("role_limited", "specialist_agent") is specialist_tool
    assert manager.get_for_role("role_limited", "main_agent") is None


def test_execute_rejects_tool_hidden_from_context_role():
    manager = ToolManager()
    manager.register(RoleLimitedTool())

    with pytest.raises(CapabilityUnavailableError, match="agent role main_agent"):
        manager.execute("role_limited", make_context())


def test_execute_allows_visible_role_and_preserves_task_context():
    manager = ToolManager()
    manager.register(RoleLimitedTool())
    context = make_context(agent_role="specialist_agent")
    before = context.to_dict()

    result = manager.execute("role_limited", context)

    assert result.payload == {"agent_role": "specialist_agent"}
    assert context.to_dict() == before


def test_role_visibility_does_not_bypass_task_allowlist():
    manager = ToolManager()
    manager.register(RoleLimitedTool())

    with pytest.raises(CapabilityUnavailableError, match="not allowed"):
        manager.execute(
            "role_limited",
            make_context(
                agent_role="specialist_agent",
                allowed_tools=(),
            ),
        )
