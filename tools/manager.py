from dataclasses import dataclass, field

from agent.context import AgentExecutionContext
from registries.tool_registry import ToolRegistry

from .base import Tool, ToolResult


class CapabilityUnavailableError(RuntimeError):
    def __init__(self, capability_name: str, reason: str) -> None:
        self.capability_name = capability_name
        self.reason = reason
        super().__init__(f"tool {capability_name} is {reason}")


@dataclass(slots=True)
class ToolManager:
    registry: ToolRegistry = field(default_factory=ToolRegistry)
    version: int = 0

    def register(self, tool: Tool) -> None:
        self.registry.register(tool)
        self.version += 1

    def unregister(self, tool_name: str) -> None:
        if self.registry.get(tool_name) is not None:
            self.registry.unregister(tool_name)
            self.version += 1

    def list_names(self) -> tuple[str, ...]:
        return self.registry.list_names()

    def execute(
        self,
        tool_name: str,
        context: AgentExecutionContext,
    ) -> ToolResult:
        if tool_name not in context.allowed_tools:
            raise CapabilityUnavailableError(tool_name, "not allowed")

        tool = self.registry.get(tool_name)
        if tool is None:
            raise CapabilityUnavailableError(tool_name, "not registered")
        return tool.run(context)
