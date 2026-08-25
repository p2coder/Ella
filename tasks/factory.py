from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from agent.context import AgentExecutionContext, CapabilityScope
from agent.handoff import HandoffRequest
from skill.manager import SkillManager
from tools.manager import ToolManager

from .task import Task, TaskIntent


@dataclass(frozen=True, slots=True, init=False)
class TaskCreationResult:
    task: Task

    def __init__(
        self,
        task: Task | None = None,
        *,
        context: AgentExecutionContext | None = None,
    ) -> None:
        if task is None:
            raise TypeError("TaskCreationResult requires task")
        if context is not None:
            task.execution_context = context
        if task.execution_context is None:
            raise ValueError("Task must own an execution context")
        object.__setattr__(self, "task", task)

    @property
    def context(self) -> AgentExecutionContext:
        return self.task.execution_context


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

    def create_task(self, handoff: HandoffRequest) -> TaskCreationResult:
        task_id = self._new_task_id()
        context = AgentExecutionContext(
            agent_id=self.agent_id,
            agent_role=self.agent_role,
            parent_agent_id=self.parent_agent_id,
            task_id=task_id,
            trace_id=handoff.trigger_event.trace_id,
            handoff_goal=handoff.task_goal,
            memory_scope=self.memory_scope,
            permissions=self.permissions,
            capability_scope=self._resolve_capability_scope(),
        )
        task = Task(
            task_id=task_id,
            handoff=handoff,
            trace_id=handoff.trigger_event.trace_id,
            source_event=handoff.trigger_event,
            execution_context=context,
            intent=TaskIntent(
                goal=handoff.task_goal,
                constraints=handoff.constraints,
                deliverables=(handoff.context_summary,)
                if handoff.context_summary
                else (),
                minimum_acceptance_criteria=handoff.completion_criteria,
            ),
        )
        return TaskCreationResult(task=task)

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
