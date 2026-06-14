from agent.context import AgentExecutionContext
from tools.base import ToolDefinition
from tools.camera_scene import CameraSceneTool
from tools.mock_tools import (
    MockChecklistTool,
    MockVisionSummaryTool,
    MockWeatherTool,
)


def _make_context(*, allowed_tools: tuple[str, ...]) -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        session_id="session-tools",
        task_id="task-tools",
        trace_id="trace-tools",
        handoff_goal="Give the user a short, necessary reminder before leaving.",
        memory_scope="task_local",
        allowed_tools=allowed_tools,
        permissions=("read_context",),
    )


def test_existing_tools_expose_tool_definitions() -> None:
    tools = (
        MockVisionSummaryTool(),
        MockWeatherTool(),
        MockChecklistTool(),
        CameraSceneTool(),
    )

    for tool in tools:
        assert isinstance(tool.definition, ToolDefinition)


def test_tool_definition_names_match_stable_tool_names() -> None:
    tools = (
        MockVisionSummaryTool(),
        MockWeatherTool(),
        MockChecklistTool(),
        CameraSceneTool(),
    )

    for tool in tools:
        assert tool.definition.name == tool.name


def test_tool_definitions_have_required_metadata() -> None:
    definitions = (
        MockVisionSummaryTool().definition,
        MockWeatherTool().definition,
        MockChecklistTool().definition,
        CameraSceneTool().definition,
    )

    for definition in definitions:
        assert definition.description.strip()
        assert definition.schema_version == "1.0"
        assert definition.input_schema["type"] == "object"
        assert definition.output_schema["type"] == "object"
        assert isinstance(definition.input_examples, tuple)


def test_tool_definition_descriptions_explain_use_and_limits() -> None:
    definitions = (
        MockVisionSummaryTool().definition,
        MockWeatherTool().definition,
        MockChecklistTool().definition,
        CameraSceneTool().definition,
    )

    for definition in definitions:
        description = definition.description.lower()
        assert "use" in description
        assert "do not use" in description


def test_tool_definition_input_examples_are_deterministic() -> None:
    assert MockWeatherTool().definition.input_examples == (
        {"location": "local", "unit": "celsius"},
    )
    assert MockVisionSummaryTool().definition.input_examples == ({},)
    assert MockChecklistTool().definition.input_examples == ({},)
    assert CameraSceneTool().definition.input_examples == (
        {"max_frames": 3, "max_duration_seconds": 3},
    )


def test_tool_definitions_exclude_runtime_and_secret_fields() -> None:
    definitions = (
        MockVisionSummaryTool().definition,
        MockWeatherTool().definition,
        MockChecklistTool().definition,
        CameraSceneTool().definition,
    )
    forbidden_fragments = (
        "api_key",
        "credential",
        "authorization",
        "local_path",
        "class_name",
        "raw_media",
        "permission",
        "camera_provider",
        "multimodal_provider",
    )

    for definition in definitions:
        serialized = str(definition.to_dict()).lower()
        for fragment in forbidden_fragments:
            assert fragment not in serialized


def test_existing_tool_run_behavior_remains_compatible() -> None:
    mock_context = _make_context(
        allowed_tools=("mock_weather", "mock_vision_summary", "mock_checklist")
    )
    camera_context = _make_context(allowed_tools=("camera_scene",))

    assert MockWeatherTool().run(mock_context).tool_name == "mock_weather"
    assert (
        MockVisionSummaryTool().run(mock_context).tool_name
        == "mock_vision_summary"
    )
    assert MockChecklistTool().run(mock_context).tool_name == "mock_checklist"
    assert CameraSceneTool().run(camera_context).tool_name == "camera_scene"
