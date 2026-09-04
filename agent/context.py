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


@dataclass(frozen=True, slots=True)
class AgentExecutionContext:
    agent_id: str
    agent_role: str
    parent_agent_id: str | None
    task_id: str
    trace_id: str
    handoff_goal: str
    memory_scope: str
    capability_scope: CapabilityScope
    permissions: tuple[str, ...] = ()
    agent_depth: int = 0

    def __post_init__(self) -> None:
        if self.capability_scope.agent_role != self.agent_role:
            raise ValueError("capability scope agent role must match context agent role")
        if self.agent_depth < 0:
            raise ValueError("agent_depth must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "parent_agent_id": self.parent_agent_id,
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "handoff_goal": self.handoff_goal,
            "memory_scope": self.memory_scope,
            "permissions": self.permissions,
            "capability_scope": self.capability_scope.to_dict(),
            "agent_depth": self.agent_depth,
        }
