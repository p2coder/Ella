from dataclasses import dataclass, field

from agent.context import AgentExecutionContext
from registries.tool_registry import ToolRegistry

from .base import Tool, ToolDefinition, ToolResult


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

    def get_tool(self, tool_name: str) -> Tool | None:
        return self.registry.get(tool_name)

    def list_definitions(
        self, context: AgentExecutionContext
    ) -> tuple[ToolDefinition, ...]:
        return tuple(
            tool.definition
            for tool_name in self.registry.list_names()
            if tool_name in context.allowed_tools
            for tool in (self.get_for_role(tool_name, context.agent_role),)
            if tool is not None
        )

    def list_names_for_role(self, agent_role: str) -> tuple[str, ...]:
        return tuple(
            tool_name
            for tool_name in self.registry.list_names()
            if self.get_for_role(tool_name, agent_role) is not None
        )

    def get_for_role(self, tool_name: str, agent_role: str) -> Tool | None:
        tool = self.registry.get(tool_name)
        if tool is None or agent_role not in self._allowed_roles(tool):
            return None
        return tool

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
        if context.agent_role not in self._allowed_roles(tool):
            raise CapabilityUnavailableError(
                tool_name,
                f"not visible to agent role {context.agent_role}",
            )
        return tool.run(context)

    @staticmethod
    def _allowed_roles(tool: Tool) -> tuple[str, ...]:
        return getattr(tool, "allowed_roles", ("main_agent",))
