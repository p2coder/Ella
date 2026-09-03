from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from agent.context import CapabilityScope
from skill.manager import SkillManager
from tools.manager import ToolManager

@dataclass(frozen=True, slots=True)
class TaskFactory:
    agent_id: str = "ella-main"
    agent_role: str = "main_agent"
    parent_agent_id: str | None = None
    memory_scope: str = "task_local"
    allowed_tools: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    skill_manager: SkillManager | None = None
    tool_manager: ToolManager | None = None
    task_id_factory: Callable[[], str] | None = None

    def _resolve_capability_scope(self) -> CapabilityScope:
        if self.skill_manager is None:
            allowed_skills = ()
            skill_registry_version = None
        else:
            allowed_skills = tuple(
                summary["name"]
                for summary in self.skill_manager.list_summaries_for_role(
                    self.agent_role
                )
            )
            skill_registry_version = self.skill_manager.version

        if self.tool_manager is None:
            allowed_tools = self.allowed_tools
            tool_registry_version = None
        else:
            allowed_tools = self.tool_manager.list_names_for_role(self.agent_role)
            tool_registry_version = self.tool_manager.version

        return CapabilityScope(
            agent_role=self.agent_role,
            allowed_skills=allowed_skills,
            allowed_tools=allowed_tools,
            skill_registry_version=skill_registry_version,
            tool_registry_version=tool_registry_version,
        )

    def _new_task_id(self) -> str:
        if self.task_id_factory is not None:
            return self.task_id_factory()
        return f"task-{uuid4().hex}"
