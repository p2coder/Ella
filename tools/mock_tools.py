from dataclasses import dataclass

from agent.context import AgentExecutionContext

from .base import ToolResult


@dataclass(frozen=True, slots=True)
class MockWeatherTool:
    name: str = "mock_weather"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    def run(self, context: AgentExecutionContext) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            session_id=context.session_id,
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

    def run(self, context: AgentExecutionContext) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            session_id=context.session_id,
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

    def run(self, context: AgentExecutionContext) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            session_id=context.session_id,
            trace_id=context.trace_id,
            payload={
                "items": ("phone", "keys", "wallet", "umbrella"),
            },
        )
