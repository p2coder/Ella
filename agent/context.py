from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CapabilityScope:
    agent_role: str
    allowed_skills: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    skill_registry_version: int | None = None
    tool_registry_version: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_role": self.agent_role,
            "allowed_skills": self.allowed_skills,
            "allowed_tools": self.allowed_tools,
            "skill_registry_version": self.skill_registry_version,
            "tool_registry_version": self.tool_registry_version,
        }


@dataclass(frozen=True, slots=True, init=False)
class AgentExecutionContext:
    agent_id: str
    agent_role: str
    parent_agent_id: str | None
    task_id: str
    trace_id: str
    handoff_goal: str
    memory_scope: str
    permissions: tuple[str, ...]
    capability_scope: CapabilityScope

    def __init__(
        self,
        agent_id: str,
        agent_role: str,
        parent_agent_id: str | None,
        task_id: str,
        trace_id: str,
        handoff_goal: str,
        memory_scope: str,
        allowed_tools: tuple[str, ...] = (),
        permissions: tuple[str, ...] = (),
        capability_scope: CapabilityScope | None = None,
    ) -> None:
        if capability_scope is None:
            capability_scope = CapabilityScope(
                agent_role=agent_role,
                allowed_skills=(),
                allowed_tools=allowed_tools,
            )
        elif capability_scope.agent_role != agent_role:
            raise ValueError("capability scope agent role must match context agent role")
        elif allowed_tools and allowed_tools != capability_scope.allowed_tools:
            raise ValueError(
                "allowed_tools must match capability scope when both are provided"
            )

        object.__setattr__(self, "agent_id", agent_id)
        object.__setattr__(self, "agent_role", agent_role)
        object.__setattr__(self, "parent_agent_id", parent_agent_id)
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "trace_id", trace_id)
        object.__setattr__(self, "handoff_goal", handoff_goal)
        object.__setattr__(self, "memory_scope", memory_scope)
        object.__setattr__(self, "permissions", permissions)
        object.__setattr__(self, "capability_scope", capability_scope)

    @property
    def allowed_tools(self) -> tuple[str, ...]:
        return self.capability_scope.allowed_tools

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "parent_agent_id": self.parent_agent_id,
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "handoff_goal": self.handoff_goal,
            "memory_scope": self.memory_scope,
            "allowed_tools": self.allowed_tools,
            "permissions": self.permissions,
            "capability_scope": self.capability_scope.to_dict(),
        }
