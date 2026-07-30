from dataclasses import dataclass

from agent.context import AgentExecutionContext

from .base import ToolDefinition, ToolResult


TASK_CONTEXT_INPUT_PROPERTIES = {
    "task_goal": {
        "type": "string",
        "description": "Current task goal supplied by the execution boundary.",
    },
}


@dataclass(frozen=True, slots=True)
class MockWeatherTool:
    name: str = "mock_weather"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Use to provide deterministic mock weather context for local "
                "tests and demos. Do not use for real weather, live forecasts, "
                "or external API-backed weather decisions."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {
                    **TASK_CONTEXT_INPUT_PROPERTIES,
                    "location": {
                        "type": "string",
                        "description": "Optional local area to describe.",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                    },
                },
                "additionalProperties": False,
            },
            input_examples=({"location": "local", "unit": "celsius"},),
            output_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "rain_probability": {"type": "number"},
                },
                "required": ["summary", "rain_probability"],
            },
        )

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict[str, object] | None = None,
    ) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            trace_id=context.trace_id,
            payload={
                "summary": "Light rain is possible later today.",
                "rain_probability": 0.7,
            },
        )


@dataclass(frozen=True, slots=True)
class MockVisionSummaryTool:
    name: str = "mock_vision_summary"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Use to provide a deterministic mock scene summary for local "
                "tests and demos. Do not use when a task requires real camera "
                "capture or real visual understanding."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": dict(TASK_CONTEXT_INPUT_PROPERTIES),
                "additionalProperties": False,
            },
            input_examples=({},),
            output_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "visible_items": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["summary", "visible_items"],
            },
        )

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict[str, object] | None = None,
    ) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            trace_id=context.trace_id,
            payload={
                "summary": "Desk contains a laptop, headphones, and a water bottle.",
                "visible_items": ("laptop", "headphones", "water_bottle"),
            },
        )


@dataclass(frozen=True, slots=True)
class MockChecklistTool:
    name: str = "mock_checklist"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Use to provide a deterministic mock checklist for local tests "
                "and demos. Do not use as a personalized, exhaustive, or "
                "externally verified packing list."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": dict(TASK_CONTEXT_INPUT_PROPERTIES),
                "additionalProperties": False,
            },
            input_examples=({},),
            output_schema={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["items"],
            },
        )

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict[str, object] | None = None,
    ) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            trace_id=context.trace_id,
            payload={
                "items": ("phone", "keys", "wallet", "umbrella"),
            },
        )
