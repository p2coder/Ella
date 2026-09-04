import pytest

from tools.base import ToolDefinition, ToolResult


def _object_schema() -> dict[str, object]:
    return {"type": "object", "properties": {"summary": {"type": "string"}}}


def test_tool_definition_construction_and_serialization() -> None:
    definition = ToolDefinition(
        name="mock_weather",
        description="Get deterministic weather context for local tests.",
        schema_version="1.0",
        input_schema={
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
        input_examples=({"location": "San Francisco, CA"},),
        output_schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    )

    assert definition.name == "mock_weather"
    assert definition.input_examples == ({"location": "San Francisco, CA"},)
    assert definition.to_dict() == {
        "name": "mock_weather",
        "description": "Get deterministic weather context for local tests.",
        "schema_version": "1.0",
        "input_schema": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
        "input_examples": ({"location": "San Francisco, CA"},),
        "output_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
        "result_ttl_seconds": None,
        "capability_kind": "external",
    }


@pytest.mark.parametrize("value", (-1, float("nan"), float("inf"), True))
def test_tool_definition_rejects_invalid_result_ttl(value) -> None:
    with pytest.raises(ValueError, match="result_ttl_seconds"):
        ToolDefinition(
            name="mock_weather",
            description="Get deterministic weather context.",
            schema_version="1.0",
            input_schema=_object_schema(),
            input_examples=(),
            output_schema=_object_schema(),
            result_ttl_seconds=value,
        )


@pytest.mark.parametrize("value", (None, 0, 60, 0.5))
def test_tool_definition_accepts_valid_result_ttl(value) -> None:
    definition = ToolDefinition(
        name="mock_weather",
        description="Get deterministic weather context.",
        schema_version="1.0",
        input_schema=_object_schema(),
        input_examples=(),
        output_schema=_object_schema(),
        result_ttl_seconds=value,
    )

    assert definition.result_ttl_seconds == value


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("name", ""),
        ("description", ""),
        ("schema_version", ""),
    ),
)
def test_tool_definition_rejects_empty_text_fields(
    field_name: str, value: str
) -> None:
    kwargs = {
        "name": "mock_weather",
        "description": "Get deterministic weather context.",
        "schema_version": "1.0",
        "input_schema": _object_schema(),
        "input_examples": (),
        "output_schema": _object_schema(),
    }
    kwargs[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        ToolDefinition(**kwargs)


@pytest.mark.parametrize(
    "input_schema",
    (
        {},
        {"type": "string"},
        {"type": "array"},
    ),
)
def test_tool_definition_requires_object_input_schema(
    input_schema: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match="input_schema"):
        ToolDefinition(
            name="mock_weather",
            description="Get deterministic weather context.",
            schema_version="1.0",
            input_schema=input_schema,
            input_examples=(),
            output_schema=_object_schema(),
        )


@pytest.mark.parametrize(
    "output_schema",
    (
        {},
        {"type": "string"},
        {"type": "array"},
    ),
)
def test_tool_definition_requires_object_output_schema(
    output_schema: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match="output_schema"):
        ToolDefinition(
            name="mock_weather",
            description="Get deterministic weather context.",
            schema_version="1.0",
            input_schema=_object_schema(),
            input_examples=(),
            output_schema=output_schema,
        )


def test_tool_definition_preserves_input_examples_as_tuple() -> None:
    definition = ToolDefinition(
        name="mock_weather",
        description="Get deterministic weather context.",
        schema_version="1.0",
        input_schema=_object_schema(),
        input_examples=[{"location": "Tokyo"}, {"location": "New York"}],
        output_schema=_object_schema(),
    )

    assert definition.input_examples == (
        {"location": "Tokyo"},
        {"location": "New York"},
    )


def test_tool_definition_does_not_expose_runtime_resource_fields() -> None:
    definition = ToolDefinition(
        name="mock_weather",
        description="Get deterministic weather context.",
        schema_version="1.0",
        input_schema=_object_schema(),
        input_examples=(),
        output_schema=_object_schema(),
    )

    serialized = definition.to_dict()

    assert "tool" not in serialized
    assert "provider_credentials" not in serialized
    assert "local_path" not in serialized
    assert "class_name" not in serialized
    assert "raw_media" not in serialized


def test_existing_tool_result_construction_still_works() -> None:
    result = ToolResult(
        tool_name="mock_weather",
        task_id="task-1",
        trace_id="trace-1",
        payload={"summary": "Light rain is possible later today."},
    )

    assert result.to_dict() == {
        "tool_name": "mock_weather",
        "task_id": "task-1",
        "trace_id": "trace-1",
        "payload": {"summary": "Light rain is possible later today."},
        "tool_use_id": None,
        "agent_id": None,
        "parent_agent_id": None,
        "arguments": {},
        "called_at": None,
        "completed_at": None,
        "result_ttl_seconds": None,
        "refresh_of_tool_use_id": None,
    }
