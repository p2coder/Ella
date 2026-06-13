from dataclasses import dataclass, field

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from sessions.session import TaskSession
from sessions.session_manager import TaskSessionCreation, TaskSessionManager


@dataclass(frozen=True, slots=True)
class TaskHandle:
    task_id: str
    session_id: str
    trace_id: str


@dataclass(frozen=True, slots=True)
class TaskRuntimeResult:
    handle: TaskHandle
    session: TaskSession
    context: AgentExecutionContext


@dataclass(slots=True)
class TaskRuntime:
    session_manager: TaskSessionManager = field(default_factory=TaskSessionManager)
    _tasks: dict[str, TaskSessionCreation] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _sessions: dict[str, TaskSessionCreation] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def submit(self, handoff: HandoffRequest) -> TaskHandle:
        creation = self.session_manager.create_session(handoff)
        task_id = creation.session.task_id
        session_id = creation.session.session_id

        if task_id in self._tasks:
            raise ValueError(f"duplicate task_id: {task_id}")
        if session_id in self._sessions:
            raise ValueError(f"duplicate session_id: {session_id}")

        self._tasks[task_id] = creation
        self._sessions[session_id] = creation
        return TaskHandle(
            task_id=task_id,
            session_id=session_id,
            trace_id=creation.context.trace_id,
        )

    def get_session(self, task_id: str) -> TaskSession:
        return self._tasks[task_id].session

    def get_context(self, task_id: str) -> AgentExecutionContext:
        return self._tasks[task_id].context
