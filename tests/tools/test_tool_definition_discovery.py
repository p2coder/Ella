from dataclasses import dataclass

from agent.context import AgentExecutionContext, CapabilityScope
from tools.base import ToolDefinition, ToolResult
from tools.manager import ToolManager
from tools.mock_tools import MockChecklistTool, MockVisionSummaryTool, MockWeatherTool


def _context(
    *,
    allowed_tools: tuple[str, ...],
    agent_role: str = "main_agent",
) -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role=agent_role,
        parent_agent_id=None,
        task_id="task-discovery",
        trace_id="trace-discovery",
        memory_scope="task_local",
        capability_scope=CapabilityScope(agent_role, (), allowed_tools),
        permissions=("read_context",),
    )


def test_list_definitions_returns_tool_definition_snapshots() -> None:
    manager = ToolManager()
    manager.register(MockWeatherTool())
    manager.register(MockChecklistTool())

    definitions = manager.list_definitions(
        _context(allowed_tools=("mock_weather", "mock_checklist"))
    )

    assert definitions == (
        MockWeatherTool().definition,
        MockChecklistTool().definition,
    )
    assert all(isinstance(item, ToolDefinition) for item in definitions)


def test_list_definitions_filters_by_allowed_tools() -> None:
    manager = ToolManager()
    manager.register(MockWeatherTool())
    manager.register(MockChecklistTool())
    manager.register(MockVisionSummaryTool())

    definitions = manager.list_definitions(
        _context(allowed_tools=("mock_checklist",))
    )

    assert tuple(definition.name for definition in definitions) == (
        "mock_checklist",
    )


def test_list_definitions_filters_by_allowed_roles() -> None:
    manager = ToolManager()
    manager.register(RoleLimitedTool())
    manager.register(MockWeatherTool())

    definitions = manager.list_definitions(
        _context(
            allowed_tools=("role_limited", "mock_weather"),
            agent_role="main_agent",
        )
    )

    assert tuple(definition.name for definition in definitions) == (
        "mock_weather",
    )


def test_get_tool_returns_live_registered_tool_by_name() -> None:
    manager = ToolManager()
    tool = MockChecklistTool()
    manager.register(tool)

    assert manager.get_tool("mock_checklist") is tool


def test_get_tool_returns_none_for_unknown_tool() -> None:
    manager = ToolManager()

    assert manager.get_tool("missing") is None


def test_list_definitions_does_not_execute_tools() -> None:
    manager = ToolManager()
    tool = CountingTool()
    manager.register(tool)

    definitions = manager.list_definitions(_context(allowed_tools=("counting",)))

    assert tuple(definition.name for definition in definitions) == ("counting",)
    assert tool.run_count == 0


def test_list_definitions_does_not_return_tool_instances() -> None:
    manager = ToolManager()
    tool = MockWeatherTool()
    manager.register(tool)

    definitions = manager.list_definitions(_context(allowed_tools=("mock_weather",)))

    assert definitions != (tool,)
    assert definitions == (tool.definition,)


def test_tool_managers_keep_registrations_isolated() -> None:
    first = ToolManager()
    second = ToolManager()
    first.register(MockWeatherTool())

    assert first.list_names() == ("mock_weather",)
    assert second.list_names() == ()


def test_registering_once_supports_multiple_discovery_calls() -> None:
    manager = ToolManager()
    manager.register(MockWeatherTool())
    context = _context(allowed_tools=("mock_weather",))

    first = manager.list_definitions(context)
    second = manager.list_definitions(context)

    assert first == second == (MockWeatherTool().definition,)
    assert manager.list_names() == ("mock_weather",)


@dataclass(slots=True)
class RoleLimitedTool:
    name: str = "role_limited"
    allowed_roles: tuple[str, ...] = ("special_agent",)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Use for tests that require a role-limited tool. Do not use "
                "outside role visibility checks."
            ),
            schema_version="1.0",
            input_schema={"type": "object", "properties": {}},
            input_examples=({},),
            output_schema={"type": "object", "properties": {}},
        )

    def run(self, context: AgentExecutionContext) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            trace_id=context.trace_id,
            payload={},
        )


@dataclass(slots=True)
class CountingTool:
    name: str = "counting"
    allowed_roles: tuple[str, ...] = ("main_agent",)
    run_count: int = 0

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Use for tests that verify discovery is read-only. Do not use "
                "as a real capability."
            ),
            schema_version="1.0",
            input_schema={"type": "object", "properties": {}},
            input_examples=({},),
            output_schema={"type": "object", "properties": {}},
        )

    def run(self, context: AgentExecutionContext) -> ToolResult:
        self.run_count += 1
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            trace_id=context.trace_id,
            payload={},
        )
