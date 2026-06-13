from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest

from .session import TaskSession


@dataclass(frozen=True, slots=True)
class TaskSessionCreation:
    session: TaskSession
    context: AgentExecutionContext


@dataclass(frozen=True, slots=True)
class TaskSessionManager:
    agent_id: str = "ella-main"
    agent_role: str = "main_agent"
    parent_agent_id: str | None = None
    memory_scope: str = "task_local"
    allowed_tools: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    session_id_factory: Callable[[], str] | None = None
    task_id_factory: Callable[[], str] | None = None

    def create_session(self, handoff: HandoffRequest) -> TaskSessionCreation:
        session = TaskSession(
            session_id=self._new_session_id(),
            task_id=self._new_task_id(),
            handoff=handoff,
        )
        context = AgentExecutionContext(
            agent_id=self.agent_id,
            agent_role=self.agent_role,
            parent_agent_id=self.parent_agent_id,
            session_id=session.session_id,
            task_id=session.task_id,
            trace_id=handoff.trigger_event.trace_id,
            handoff_goal=handoff.task_goal,
            memory_scope=self.memory_scope,
            allowed_tools=self.allowed_tools,
            permissions=self.permissions,
        )
        return TaskSessionCreation(session=session, context=context)

    def _new_session_id(self) -> str:
        if self.session_id_factory is not None:
            return self.session_id_factory()
        return f"session-{uuid4().hex}"

    def _new_task_id(self) -> str:
        if self.task_id_factory is not None:
            return self.task_id_factory()
        return f"task-{uuid4().hex}"
