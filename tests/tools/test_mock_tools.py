from agent.context import AgentExecutionContext, CapabilityScope
from tools.manager import ToolManager
from tools import (
    MockChecklistTool,
    MockVisionSummaryTool,
    MockWeatherTool,
    ToolResult,
)


def make_context() -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-tools",
        trace_id="trace-tools",
        handoff_goal="Give the user a short, necessary reminder before leaving.",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ("mock_weather", "mock_vision_summary", "mock_checklist")),
        permissions=("read_context",),
    )


def test_tool_manager_registers_and_looks_up_tools():
    registry = ToolManager()
    weather = MockWeatherTool()

    registry.register(weather)

    assert registry.get_tool("mock_weather") == weather
    assert registry.list_names() == ("mock_weather",)


def test_mock_weather_tool_returns_deterministic_tool_result():
    result = MockWeatherTool().run(make_context())

    assert result == ToolResult(
        tool_name="mock_weather",
        task_id="task-tools",
        trace_id="trace-tools",
        payload={
            "summary": "Light rain is possible later today.",
            "rain_probability": 0.7,
        },
    )


def test_mock_vision_summary_tool_returns_deterministic_scene_summary():
    result = MockVisionSummaryTool().run(make_context())

    assert result.tool_name == "mock_vision_summary"
    assert result.payload == {
        "summary": "Desk contains a laptop, headphones, and a water bottle.",
        "visible_items": ("laptop", "headphones", "water_bottle"),
    }
    assert result.to_dict()["trace_id"] == "trace-tools"


def test_mock_checklist_tool_returns_stable_leaving_checklist():
    result = MockChecklistTool().run(make_context())

    assert result.payload == {
        "items": ("phone", "keys", "wallet", "umbrella"),
    }


def test_mock_tools_do_not_expose_external_api_clients():
    tools = (MockWeatherTool(), MockVisionSummaryTool(), MockChecklistTool())

    for tool in tools:
        assert not hasattr(tool, "http_client")
        assert not hasattr(tool, "api_key")
