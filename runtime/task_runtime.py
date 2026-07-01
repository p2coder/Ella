from dataclasses import dataclass, field, replace

from agent.context import AgentExecutionContext
from agent.final_response import FinalResponseGenerator
from agent.handoff import HandoffRequest
from memory import MemoryManagementRequest, MemoryManager, MemoryWriteResult
from sessions.completion import TaskCompletionPackage
from sessions.decision import CALL_TOOL, COMPLETE, WAIT
from sessions.execution_state import (
    StepExecutionState,
    ToolFailureKind,
    ToolFailureObservation,
)
from sessions.executor import CapabilityExecutor
from sessions.output import UserVisibleAgentOutput
from sessions.session import TaskSession, TaskState
from sessions.session_manager import TaskSessionCreation, TaskSessionManager
from sessions.strategy import StrategyDecision
from sessions.subagent import SubAgent
from tools import ToolResult


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
    completion: TaskCompletionPackage | None = None
    steps: int = 0
    stop_reason: str | None = None
    blocked: bool = False
    memory_result: MemoryWriteResult | None = None
    failure_reason: str | None = None
    logical_steps: int = 0


@dataclass(slots=True, init=False)
class TaskRuntime:
    session_manager: TaskSessionManager = field(default_factory=TaskSessionManager)
    subagent: SubAgent | None = None
    executor: CapabilityExecutor | None = None
    final_response_generator: FinalResponseGenerator | None = None
    max_argument_retries: int = 2
    _memory_manager: MemoryManager = field(init=False, repr=False)
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
    _memory_results: dict[str, MemoryWriteResult] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __init__(
        self,
        session_manager: TaskSessionManager | None = None,
        subagent: SubAgent | None = None,
        executor: CapabilityExecutor | None = None,
        memory_manager: MemoryManager | None = None,
        final_response_generator: FinalResponseGenerator | None = None,
        max_argument_retries: int = 2,
    ) -> None:
        if max_argument_retries < 0:
            raise ValueError("max_argument_retries must be non-negative")
        self.session_manager = session_manager or TaskSessionManager()
        self.subagent = subagent
        self.executor = executor
        self.final_response_generator = final_response_generator
        self.max_argument_retries = max_argument_retries
        self._memory_manager = memory_manager or MemoryManager()
        self._tasks = {}
        self._sessions = {}
        self._memory_results = {}

    def submit(self, handoff: HandoffRequest) -> TaskHandle:
        
        creation = self.session_manager.create_session(handoff)
        creation.session.current_step = replace(
            creation.session.current_step,
            max_argument_retries=self.max_argument_retries,
        )
        task_id = creation.session.task_id
        session_id = creation.session.session_id
        print("[task_runtime.py]submit:submit event ",task_id)
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

        repair_violation = self._repair_violation(session, decision)
        if repair_violation is not None:
            self._handle_failure(session, repair_violation)
            return self._result(creation)

        execution = executor.execute(
            decision,
            strategy,
            creation.context,
            session,
        )
        print("[task_runtime]desicion action: ",decision.action)
        if execution.failure is not None:
            self._handle_failure(session, execution.failure)
            return self._result(creation)

        if execution.tool_result is not None:
            session.tool_trace += (execution.tool_result.to_dict(),)
            self._archive_and_advance(session)

        if execution.replan_required:
            session.transition_to(TaskState.REPLANNING)
        elif decision.action == WAIT:
            self._archive_and_advance(session)
            session.transition_to(TaskState.WAITING)
        elif decision.action == COMPLETE:
            self._archive_and_advance(session)
            session.completion = self._build_completion(creation)
            session.transition_to(TaskState.COMPLETED)
            return self._result(
                creation,
                stop_reason="completed",
            )

        return self._result(creation)

    def _repair_violation(
        self,
        session: TaskSession,
        decision,
    ) -> ToolFailureObservation | None:
        active_tool = session.current_step.active_tool_name
        if active_tool is None:
            return None
        if (
            decision.action == CALL_TOOL
            and decision.tool_name == active_tool
            and isinstance(decision.tool_input, dict)
        ):
            return None

        requested_tool = decision.tool_name or active_tool
        return ToolFailureObservation(
            attempt_id=session.current_step.attempt_id,
            tool_name=active_tool,
            kind=ToolFailureKind.INVALID_ARGUMENTS_REPAIR_VIOLATION,
            code="invalid_arguments_repair_violation",
            message=(
                "Argument repair must call the locked Tool "
                f"{active_tool}; received {decision.action} for {requested_tool}."
            ),
            arguments=decision.tool_input or {},
            retryable=True,
        )

    def _handle_failure(
        self,
        session: TaskSession,
        failure: ToolFailureObservation,
    ) -> None:
        step = session.current_step
        failures = (*step.failures, failure)
        if failure.kind in {
            ToolFailureKind.INVALID_ARGUMENTS,
            ToolFailureKind.INVALID_ARGUMENTS_REPAIR_VIOLATION,
        }:
            active_tool = step.active_tool_name or failure.tool_name
            if step.retry_index < step.max_argument_retries:
                session.current_step = replace(
                    step,
                    retry_index=step.retry_index + 1,
                    active_tool_name=active_tool,
                    failures=failures,
                )
                return

            exhausted = ToolFailureObservation(
                attempt_id=step.attempt_id,
                tool_name=active_tool,
                kind=ToolFailureKind.INVALID_ARGUMENTS,
                code="parameter_generation_failed",
                message=(
                    "Tool arguments could not be repaired within the configured "
                    "retry budget."
                ),
                arguments=failure.arguments,
                retryable=False,
            )
            session.current_step = replace(
                step,
                active_tool_name=active_tool,
                blacklisted_tools=(
                    *step.blacklisted_tools,
                    *(
                        ()
                        if active_tool in step.blacklisted_tools
                        else (active_tool,)
                    ),
                ),
                failures=(*failures, exhausted),
            )
            self._archive_and_advance(session)
            return

        blacklisted = (
            step.blacklisted_tools
            if failure.tool_name in step.blacklisted_tools
            else (*step.blacklisted_tools, failure.tool_name)
        )
        session.current_step = replace(
            step,
            blacklisted_tools=blacklisted,
            failures=failures,
        )
        self._archive_and_advance(session)

    @staticmethod
    def _archive_and_advance(session: TaskSession) -> None:
        archived = session.current_step
        session.step_history += (archived,)
        session.current_step = StepExecutionState(
            step_number=archived.step_number + 1,
            max_argument_retries=archived.max_argument_retries,
        )

    def run_until_blocked(
        self,
        task_id: str,
        max_steps: int,
    ) -> TaskRuntimeResult:
        if max_steps < 0:
            raise ValueError("max_steps must be non-negative")

        creation = self._tasks[task_id]
        stop_reason = self._stop_reason(creation.session)
        print("[task_runtime]stop reason: ",stop_reason)
        if stop_reason is not None:
            return self._result(
                creation,
                stop_reason=stop_reason,
                blocked=self._is_blocked_reason(stop_reason),
            )

        for steps in range(1, max_steps + 1):
            self.step(task_id)
            stop_reason = self._stop_reason(creation.session)
            print("[task_runtime] stop_reason: ",stop_reason)
            if stop_reason is not None:
                return self._result(
                    creation,
                    steps=steps,
                    stop_reason=stop_reason,
                    blocked=self._is_blocked_reason(stop_reason),
                )

        return self._result(
            creation,
            steps=max_steps,
            stop_reason="max_steps",
            blocked=True,
        )

    def run_until_complete(
        self,
        task_id: str,
        max_steps: int,
    ) -> TaskRuntimeResult:
        runtime_result = self.run_until_blocked(task_id, max_steps)
        completion = runtime_result.completion
        if (
            runtime_result.session.state is not TaskState.COMPLETED
            or completion is None
        ):
            return runtime_result

        memory_result = self._memory_results.get(task_id)
        if memory_result is None:
            request = MemoryManagementRequest.from_completion(completion)
            try:
                memory_result = self._memory_manager.handle(request)
            except Exception as error:
                return self._result(
                    self._tasks[task_id],
                    steps=runtime_result.steps,
                    stop_reason="memory_failed",
                    blocked=True,
                    failure_reason=f"memory write failed: {error}",
                )
            self._memory_results[task_id] = memory_result

        return self._result(
            self._tasks[task_id],
            steps=runtime_result.steps,
            stop_reason="completed",
            memory_result=memory_result,
        )

    def _execution_components(self) -> tuple[SubAgent, CapabilityExecutor]:
        if self.subagent is None or self.executor is None:
            raise RuntimeError(
                "TaskRuntime requires subagent and executor for state progression"
            )
        return self.subagent, self.executor

    @staticmethod
    def _stop_reason(session: TaskSession) -> str | None:
        if session.state is TaskState.WAITING:
            return "waiting"
        if session.state is TaskState.COMPLETED:
            return "completed"
        if session.state is TaskState.FAILED:
            return "failed"
        if session.state is TaskState.CANCELLED:
            return "cancelled"
        return None

    @staticmethod
    def _is_blocked_reason(stop_reason: str) -> bool:
        return stop_reason in {"waiting", "max_steps"}

    def _build_completion(
        self,
        creation: TaskSessionCreation,
    ) -> TaskCompletionPackage:
        session = creation.session
        tool_results = tuple(
            ToolResult(
                tool_name=entry["tool_name"],
                task_id=entry["task_id"],
                session_id=entry["session_id"],
                trace_id=entry["trace_id"],
                payload=entry["payload"],
            )
            for entry in session.tool_trace
        )
        final_response = self._generate_final_response(creation, tool_results)
        output = UserVisibleAgentOutput(
            process={
                "task_goal": session.handoff.task_goal,
                "strategy": getattr(
                    session.current_strategy,
                    "skill_name",
                    None,
                ),
                "tool_results": tuple(
                    result.tool_name for result in tool_results
                ),
            },
            final_response=final_response,
        )
        return TaskCompletionPackage(
            context=creation.context,
            summary=f"Completed task: {session.handoff.task_goal}",
            user_visible_output=output,
            tool_results=tool_results,
        )

    def _generate_final_response(
        self,
        creation: TaskSessionCreation,
        tool_results: tuple[ToolResult, ...],
    ) -> str:
        session = creation.session
        handoff = session.handoff
        trigger_payload = handoff.trigger_event.payload
        user_input = trigger_payload.get("text", "")
        if not isinstance(user_input, str):
            user_input = str(user_input)

        if self.final_response_generator is None:
            return self._default_final_response(
                task_goal=handoff.task_goal,
                tool_results=tool_results,
            )

        result = self.final_response_generator.generate(
            trace_id=creation.context.trace_id,
            user_input=user_input,
            task_goal=handoff.task_goal,
            task_constraints=handoff.constraints,
            completion_criteria=handoff.completion_criteria,
            tool_results=tool_results,
            user_preference_summary=handoff.user_preference_summary,
            environment_summary=handoff.environment_summary,
            memory_context=self._memory_context(),
            execution_failures=self._execution_failures(session),
        )
        return result.final_response

    @staticmethod
    def _execution_failures(
        session: TaskSession,
    ) -> tuple[ToolFailureObservation, ...]:
        historical = tuple(
            failure
            for step in session.step_history
            for failure in step.failures
        )
        return (*historical, *session.current_step.failures)

    def _memory_context(self) -> str:
        query = getattr(self._memory_manager, "query", None)
        if query is None:
            return ""
        try:
            result = query()
        except Exception:
            return ""
        content = getattr(result, "content", "")
        if not isinstance(content, str):
            return str(content)
        return content

    @staticmethod
    def _default_final_response(
        *,
        task_goal: str,
        tool_results: tuple[ToolResult, ...],
    ) -> str:
        if tool_results:
            summaries = []
            for result in tool_results:
                summary = result.payload.get("summary") or result.payload.get(
                    "scene_summary"
                )
                if isinstance(summary, str) and summary.strip():
                    summaries.append(f"{result.tool_name}: {summary.strip()}")
                else:
                    summaries.append(result.tool_name)
            return (
                "我已经根据当前信息完成了检查："
                f"{'; '.join(summaries)}。任务目标是：{task_goal}"
            )
        return f"我已经根据当前信息完成了任务。任务目标是：{task_goal}"

    @staticmethod
    def _result(
        creation: TaskSessionCreation,
        steps: int = 0,
        stop_reason: str | None = None,
        blocked: bool = False,
        memory_result: MemoryWriteResult | None = None,
        failure_reason: str | None = None,
    ) -> TaskRuntimeResult:
        return TaskRuntimeResult(
            handle=TaskHandle(
                task_id=creation.session.task_id,
                session_id=creation.session.session_id,
                trace_id=creation.context.trace_id,
            ),
            session=creation.session,
            context=creation.context,
            completion=creation.session.completion,
            steps=steps,
            stop_reason=stop_reason,
            blocked=blocked,
            memory_result=memory_result,
            failure_reason=failure_reason,
            logical_steps=len(creation.session.step_history),
        )
