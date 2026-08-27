from prompts.engine import PromptEngine, PromptType
from providers.llm import (
    serialize_tool_definition,
    serialize_tool_definitions,
)
from tools.base import ToolDefinition


def make_definition() -> ToolDefinition:
    return ToolDefinition(
        name="get_weather",
        description=(
            "Use to get current weather for a location. Do not use for "
            "historical climate analysis."
        ),
        schema_version="1.0",
        input_schema={
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
            },
            "required": ["location"],
            "additionalProperties": False,
        },
        input_examples=(
            {"location": "San Francisco, CA", "unit": "fahrenheit"},
            {"location": "Tokyo", "unit": "celsius"},
        ),
        output_schema={
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "provider_credentials": {"type": "string"},
                "raw_media": {"type": "string"},
                "debug_class_name": {"type": "string"},
            },
            "required": ["summary"],
        },
    )


def test_tool_definition_serializes_to_provider_neutral_shape() -> None:
    serialized = serialize_tool_definition(make_definition())

    assert serialized == {
        "name": "get_weather",
        "description": (
            "Use to get current weather for a location. Do not use for "
            "historical climate analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
            },
            "required": ["location"],
            "additionalProperties": False,
        },
        "input_examples": (
            {"location": "San Francisco, CA", "unit": "fahrenheit"},
            {"location": "Tokyo", "unit": "celsius"},
        ),
        "output_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    }


def test_tool_definition_serialization_is_deterministic() -> None:
    definition = make_definition()

    assert serialize_tool_definition(definition) == serialize_tool_definition(
        definition
    )
    assert serialize_tool_definitions((definition,)) == (
        serialize_tool_definition(definition),
    )


def test_serialization_excludes_secret_and_runtime_metadata() -> None:
    serialized_text = str(serialize_tool_definition(make_definition())).lower()

    forbidden = (
        "credential",
        "api_key",
        "authorization",
        "local_path",
        "class_name",
        "debug",
        "raw_media",
        "permission",
        "tool instance",
    )
    for fragment in forbidden:
        assert fragment not in serialized_text


def test_prompt_engine_accepts_serialized_tools_as_structured_context() -> None:
    serialized_tools = serialize_tool_definitions((make_definition(),))

    result = PromptEngine().build(
        PromptType.EXECUTION_DECISION,
        {
            "task_goal": "Help the user decide whether to bring an umbrella.",
            "visible_tools": serialized_tools,
        },
    )

    assert result.prompt_type == PromptType.EXECUTION_DECISION
    assert "get_weather" in result.prompt
    assert "provider_credentials" not in result.prompt
    assert "raw_media" not in result.prompt
