from dataclasses import dataclass, field

from agent.context import AgentExecutionContext

from .base import (
    EffectiveToolExecutionMetadata,
    Tool,
    ToolDefinition,
    ToolIdempotency,
    ToolUncertainPolicy,
)


class CapabilityUnavailableError(RuntimeError):
    def __init__(self, capability_name: str, reason: str) -> None:
        self.capability_name = capability_name
        self.reason = reason
        super().__init__(f"tool {capability_name} is {reason}")


@dataclass(slots=True)
class ToolManager:
    _tools: dict[str, Tool] = field(default_factory=dict, init=False, repr=False)
    version: int = 0

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        self.version += 1

    def unregister(self, tool_name: str) -> None:
        if self._tools.get(tool_name) is not None:
            del self._tools[tool_name]
            self.version += 1

    def list_names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def get_tool(self, tool_name: str) -> Tool | None:
        return self._tools.get(tool_name)

    def resolve_execution_metadata(
        self,
        tool_name: str,
        tool_version: str,
        execution_override: dict[str, object] | None = None,
    ) -> EffectiveToolExecutionMetadata:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise CapabilityUnavailableError(tool_name, "not registered")
        definition = tool.definition
        if definition.version != tool_version:
            raise CapabilityUnavailableError(
                tool_name,
                f"version {tool_version} is not registered",
            )

        override = dict(execution_override or {})
        forbidden = set(override) - set(definition.overridable_fields)
        if forbidden:
            raise ValueError(
                "tool execution override is not allowed for: "
                + ", ".join(sorted(forbidden))
            )

        values: dict[str, object] = {
            "idempotency": definition.idempotency,
            "side_effecting": definition.side_effecting,
            "uncertain_policy": definition.uncertain_policy,
        }
        values.update(override)
        try:
            idempotency = ToolIdempotency(values["idempotency"])
            uncertain_policy = ToolUncertainPolicy(values["uncertain_policy"])
        except ValueError as exc:
            raise ValueError("invalid tool execution override value") from exc
        if not isinstance(values["side_effecting"], bool):
            raise ValueError("side_effecting override must be a boolean")

        return EffectiveToolExecutionMetadata(
            name=definition.name,
            version=definition.version,
            idempotency=idempotency,
            side_effecting=values["side_effecting"],
            uncertain_policy=uncertain_policy,
            overridden_fields=tuple(sorted(override)),
        )

    def list_definitions(
        self, context: AgentExecutionContext
    ) -> tuple[ToolDefinition, ...]:
        return tuple(
            tool.definition
            for name, tool in tuple(self._tools.items())
            if name in context.capability_scope.allowed_tools
            and context.agent_role in tool.allowed_roles
        )

    def list_names_for_role(self, agent_role: str) -> tuple[str, ...]:
        return tuple(
            name
            for name, tool in tuple(self._tools.items())
            if agent_role in tool.allowed_roles
        )

    def get_for_role(self, tool_name: str, agent_role: str) -> Tool | None:
        tool = self._tools.get(tool_name)
        if tool is None or agent_role not in tool.allowed_roles:
            return None
        return tool
