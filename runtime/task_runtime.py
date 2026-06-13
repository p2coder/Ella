from dataclasses import dataclass, field

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from sessions.decision import COMPLETE, WAIT
from sessions.executor import CapabilityExecutor
from sessions.session import TaskSession, TaskState
from sessions.session_manager import TaskSessionCreation, TaskSessionManager
from sessions.strategy import StrategyDecision
from sessions.subagent import SubAgent


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
    subagent: SubAgent | None = None
    executor: CapabilityExecutor | None = None
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

    def step(self, task_id: str) -> TaskRuntimeResult:
        creation = self._tasks[task_id]
        session = creation.session

        if session.state in {
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }:
            raise ValueError(f"cannot step terminal task: {session.state.value}")

        if session.state is TaskState.CREATED:
            session.transition_to(TaskState.PLANNING)
            return self._result(creation)

        subagent, executor = self._execution_components()

        if session.state is TaskState.PLANNING:
            session.current_strategy = subagent.select_strategy(
                session.handoff,
                creation.context,
                session,
            )
            session.transition_to(TaskState.RUNNING)
            return self._result(creation)

        if session.state is TaskState.REPLANNING:
            subagent.skill_manager.refresh()
            executor.tool_manager.list_names()
            session.current_strategy = subagent.select_strategy(
                session.handoff,
                creation.context,
                session,
            )
            session.transition_to(TaskState.RUNNING)
            return self._result(creation)

        if session.state is TaskState.WAITING:
            raise ValueError("cannot step waiting task without a resume signal")

        strategy = session.current_strategy
        if not isinstance(strategy, StrategyDecision):
            raise ValueError("running task requires a current strategy")

        decision = subagent.decide_next_action(
            session.handoff,
            creation.context,
            session,
            strategy,
        )
        execution = executor.execute(
            decision,
            strategy,
            creation.context,
            session,
        )
        if execution.tool_result is not None:
            session.tool_trace += (execution.tool_result.to_dict(),)

        if execution.replan_required:
            session.transition_to(TaskState.REPLANNING)
        elif decision.action == WAIT:
            session.transition_to(TaskState.WAITING)
        elif decision.action == COMPLETE:
            session.set_task_state("completion_ready", True)
            session.set_task_state("completion_decision", decision)

        return self._result(creation)

    def _execution_components(self) -> tuple[SubAgent, CapabilityExecutor]:
        if self.subagent is None or self.executor is None:
            raise RuntimeError(
                "TaskRuntime requires subagent and executor for state progression"
            )
        return self.subagent, self.executor

    @staticmethod
    def _result(creation: TaskSessionCreation) -> TaskRuntimeResult:
        return TaskRuntimeResult(
            handle=TaskHandle(
                task_id=creation.session.task_id,
                session_id=creation.session.session_id,
                trace_id=creation.context.trace_id,
            ),
            session=creation.session,
            context=creation.context,
        )
