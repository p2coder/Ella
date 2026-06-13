from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentExecutionContext:
    agent_id: str
    agent_role: str
    parent_agent_id: str | None
    session_id: str
    task_id: str
    trace_id: str
    handoff_goal: str
    memory_scope: str
    allowed_tools: tuple[str, ...]
    permissions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "parent_agent_id": self.parent_agent_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "handoff_goal": self.handoff_goal,
            "memory_scope": self.memory_scope,
            "allowed_tools": self.allowed_tools,
            "permissions": self.permissions,
        }
