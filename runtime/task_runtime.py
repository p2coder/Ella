from dataclasses import dataclass, field, replace
from collections.abc import Mapping

from agent.context import AgentExecutionContext
from agent.final_response import FinalResponseGenerator
from agent.handoff import HandoffRequest
from memory import MemoryManagementRequest, MemoryManager, MemoryWriteResult
from sessions.completion import TaskCompletionPackage
from sessions.decision import CALL_TOOL, COMPLETE, WAIT
from sessions.execution_state import (
    StepExecutionState,
    TaskControlCommand,
    TaskControlResult,
    TaskControlType,
    ToolFailureKind,
    ToolFailureObservation,
)
from sessions.executor import CapabilityExecutor
from sessions.output import UserVisibleAgentOutput
from sessions.session import TaskSession, TaskState
from sessions.session import Task
from sessions.graph import TaskGraphRun, TaskGraphNodeType, ToolGraphRun
from sessions.session_manager import (
    TaskCreationResult,
    TaskSessionCreation,
    TaskSessionManager,
)
from sessions.strategy import StrategyDecision
from sessions.subagent import SubAgent
from tools import ToolResult
from .timing import (
    NoOpRuntimeTimingRecorder,
    RuntimeTimingRecorder,
    RuntimeTimingSnapshot,
)
from .task_queue import TaskQueue
from .task_store import TaskStore
from .step_runtime import StepRuntime


@dataclass(frozen=True, slots=True)
class TaskHandle:
    task_id: str
    trace_id: str

    @property
    def session_id(self) -> str:
        return self.task_id


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
    timing: RuntimeTimingSnapshot | None = None


@dataclass(slots=True, init=False)
class TaskRuntime:
    session_manager: TaskSessionManager = field(default_factory=TaskSessionManager)
    subagent: SubAgent | None = None
    executor: CapabilityExecutor | None = None
    final_response_generator: FinalResponseGenerator | None = None
    timing_recorder: RuntimeTimingRecorder | NoOpRuntimeTimingRecorder
    max_argument_retries: int = 2
    task_store: TaskStore | None = None
    task_queue: TaskQueue | None = None
    step_runtime: StepRuntime | None = None
    max_runtime_ticks: int = 100
    max_steps: int = 20
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
        timing_recorder: RuntimeTimingRecorder | NoOpRuntimeTimingRecorder | None = None,
        max_argument_retries: int = 2,
        task_store: TaskStore | None = None,
        task_queue: TaskQueue | None = None,
        step_runtime: StepRuntime | None = None,
        max_runtime_ticks: int = 100,
        max_steps: int = 20,
    ) -> None:
        if max_argument_retries < 0:
            raise ValueError("max_argument_retries must be non-negative")
        self.session_manager = session_manager or TaskSessionManager()
        self.subagent = subagent
        self.executor = executor
        self.final_response_generator = final_response_generator
        self.timing_recorder = timing_recorder or NoOpRuntimeTimingRecorder()
        self.max_argument_retries = max_argument_retries
        self.task_store = task_store
        self.task_queue = task_queue
        self.step_runtime = step_runtime
        self.max_runtime_ticks = max_runtime_ticks
        self.max_steps = max_steps
        self._memory_manager = memory_manager or MemoryManager()
        self._tasks = {}
        self._sessions = {}
        self._memory_results = {}

    def create_task(self, source_event) -> TaskHandle:
        task_id = self.session_manager._new_task_id()
        scope = self.session_manager._resolve_capability_scope()
        context = AgentExecutionContext(
            agent_id=self.session_manager.agent_id,
            agent_role=self.session_manager.agent_role,
            parent_agent_id=self.session_manager.parent_agent_id,
            task_id=task_id,
            trace_id=source_event.trace_id,
            handoff_goal="",
            memory_scope=self.session_manager.memory_scope,
            permissions=self.session_manager.permissions,
            capability_scope=scope,
        )
        task = Task(
            task_id,
            task_id,
            trace_id=source_event.trace_id,
            source_event=source_event,
            execution_context=context,
        )
        creation = TaskCreationResult(task)
        self._tasks[task_id] = creation
        self._sessions[task_id] = creation
        self._persist(task)
        return TaskHandle(task_id, source_event.trace_id)

    def begin_formulation(self, task_id: str) -> None:
        task = self._tasks[task_id].task
        task.transition_to(TaskState.FORMULATING)
        self._persist(task)

    def submit_formulated(
        self, task_id: str, handoff: HandoffRequest
    ) -> TaskHandle:
        creation = self._tasks[task_id]
        task = creation.task
        task.handoff = handoff
        old = task.execution_context
        task.execution_context = AgentExecutionContext(
            agent_id=old.agent_id,
            agent_role=old.agent_role,
            parent_agent_id=old.parent_agent_id,
            task_id=task.task_id,
            trace_id=task.trace_id,
            handoff_goal=handoff.task_goal,
            memory_scope=old.memory_scope,
            permissions=old.permissions,
            capability_scope=old.capability_scope,
        )
        task.transition_to(TaskState.READY)
        self._persist(task)
        if self.task_queue is not None:
            self.task_queue.enqueue(task_id)
        self.timing_recorder.record_task_submitted(
            task.trace_id, task_id=task_id
        )
        return TaskHandle(task_id, task.trace_id)

    def fail_formulation(self, task_id: str, reason: str) -> None:
        task = self._tasks[task_id].task
        task.failure = {"code": "task_formulation_failed", "message": reason}
        task.failure_reason = reason
        task.transition_to(TaskState.FAILED)
        self._persist(task)

    def _persist(self, task: Task) -> None:
        if self.task_store is None:
            return
        current = self.task_store.version(task.task_id)
        self.task_store.save(task, expected_version=current)

    def apply_control(self, command: TaskControlCommand) -> TaskControlResult:
        creation = self._tasks.get(command.task_id)
        if creation is None and self.task_store is not None:
            stored = self.task_store.load(command.task_id)
            if stored is not None:
                creation = TaskCreationResult(stored.task)
                self._tasks[command.task_id] = creation
        if creation is None:
            return TaskControlResult(command.command_id, command.task_id, False, "missing", "missing", "task_not_found", "Task does not exist.")
        task = creation.task
        handled = task.task_local_state.setdefault("handled_control_commands", {})
        if command.command_id in handled:
            previous = handled[command.command_id]
            return TaskControlResult(**previous)
        previous_state = task.state
        accepted, code, message = True, "accepted", "Control command accepted."
        if command.command_type is TaskControlType.KILL:
            if task.state in {TaskState.SUCCEEDED, TaskState.FAILED, TaskState.KILLED, TaskState.DELIVERED}:
                accepted, code, message = False, "terminal_task", "Terminal Task cannot be killed."
            else:
                task.control_request = command
                if task.state is not TaskState.KILL_REQUESTED:
                    task.transition_to(TaskState.KILL_REQUESTED)
                task.transition_to(TaskState.KILLED)
        elif command.command_type is TaskControlType.PAUSE:
            if task.state in {TaskState.KILL_REQUESTED, TaskState.KILLED}:
                accepted, code, message = False, "kill_has_priority", "Kill has priority over pause."
            elif task.state not in {TaskState.CREATED, TaskState.FORMULATING, TaskState.READY, TaskState.RUNNING, TaskState.WAITING}:
                accepted, code, message = False, "invalid_state", "Task cannot be paused from its current state."
            else:
                task.paused_from_state = task.state
                task.control_request = command
                task.transition_to(TaskState.PAUSE_REQUESTED)
                self._persist(task)
                task.transition_to(TaskState.PAUSED)
        elif command.command_type is TaskControlType.RESUME:
            if task.state is not TaskState.PAUSED or task.paused_from_state is None:
                accepted, code, message = False, "invalid_state", "Only a paused Task can resume."
            else:
                destination = task.paused_from_state
                task.control_request = command
                task.transition_to(destination)
                task.paused_from_state = None
                if destination is TaskState.READY and self.task_queue is not None:
                    self.task_queue.enqueue(task.task_id)
        else:
            accepted, code, message = False, "unsupported_command", "Command is not handled by the control plane."
        result = TaskControlResult(command.command_id, task.task_id, accepted, previous_state.value, task.state.value, code, message)
        handled[command.command_id] = {
            "command_id": result.command_id, "task_id": result.task_id, "accepted": result.accepted,
            "previous_state": result.previous_state, "current_state": result.current_state,
            "code": result.code, "message": result.message,
        }
        if accepted:
            self._persist(task)
        return result

    def submit(self, handoff: HandoffRequest) -> TaskHandle:
        
        creation = self.session_manager.create_session(handoff)
        creation.session.current_step = replace(
            creation.session.current_step,
            max_argument_retries=self.max_argument_retries,
        )
        task_id = creation.session.task_id
        print("[task_runtime.py]submit:submit event ",task_id)
        if task_id in self._tasks:
            raise ValueError(f"duplicate task_id: {task_id}")
        self._tasks[task_id] = creation
        self._sessions[task_id] = creation
        self.timing_recorder.record_task_submitted(
            creation.context.trace_id,
            task_id=task_id,
        )
        return TaskHandle(
            task_id=task_id,
            trace_id=creation.context.trace_id,
        )

    def get_session(self, task_id: str) -> TaskSession:
        return self._tasks[task_id].session

    def get_context(self, task_id: str) -> AgentExecutionContext:
        return self._tasks[task_id].context

    def step(self, task_id: str) -> TaskRuntimeResult:
        creation = self._tasks[task_id]
        session = creation.session
        if session.graph is not None and session.state is TaskState.RUNNING:
            return self._step_task_graph(creation)
        self.timing_recorder.record_task_processing_started(
            creation.context.trace_id
        )

        if session.state in {
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }:
            raise ValueError(f"cannot step terminal task: {session.state.value}")
        if session.state is TaskState.CREATED:
            session.transition_to(TaskState.PLANNING)
            return self._result(creation)
        if session.state is TaskState.READY:
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

        self.timing_recorder.record_execution_started(creation.context.trace_id)
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
            self.timing_recorder.record_execution_completed(
                creation.context.trace_id
            )
            session.completion = self._build_completion(creation)
            self.timing_recorder.record_task_completed(creation.context.trace_id)
            session.transition_to(TaskState.COMPLETED)
            return self._result(creation, stop_reason="completed")

        return self._result(creation)

    def _step_task_graph(
        self, creation: TaskCreationResult
    ) -> TaskRuntimeResult:
        task = creation.task
        ticks = int(task.task_local_state.get("runtime_ticks", 0)) + 1
        task.task_local_state["runtime_ticks"] = ticks
        if ticks > self.max_runtime_ticks:
            return self._fail_graph_task(
                creation, "max_runtime_ticks_exhausted"
            )
        graph = task.graph
        runs = {key: value for key, value in graph.node_runs.items()}
        completed_steps = sum(
            1
            for value in runs.values()
            if _graph_run_state(value) == "succeeded"
        )
        if completed_steps >= self.max_steps:
            return self._fail_graph_task(creation, "max_steps_exhausted")
        ready = []
        for node in graph.definition.nodes:
            if node.node_type is not TaskGraphNodeType.STEP:
                continue
            if _graph_run_state(runs.get(node.node_id)) not in {None, "pending", "ready", "running"}:
                continue
            if all(
                _graph_run_state(runs.get(predecessor)) == "succeeded"
                for predecessor in graph.definition.predecessors(node.node_id)
            ):
                ready.append(node.node_id)
        ordered = graph.definition.stable_ready_order(ready)
        if not ordered:
            terminal_states = {
                _graph_run_state(runs.get(node_id))
                for node_id in graph.definition.terminal_node_ids
            }
            if "succeeded" in terminal_states:
                task.transition_to(TaskState.SUCCEEDED)
                self._persist(task)
                return self._result(creation, stop_reason="completed")
            return self._fail_graph_task(creation, "no_reachable_success_terminal")
        node_id = ordered[0]
        node = next(item for item in graph.definition.nodes if item.node_id == node_id)
        payload = node.payload
        tool_graph = payload.get("tool_graph_run") if isinstance(payload, dict) else None
        if not isinstance(tool_graph, ToolGraphRun) or self.step_runtime is None:
            runs[node_id] = {"state": "failed", "code": "step_graph_unavailable"}
        else:
            strategy = task.current_strategy or StrategyDecision(
                "react", None, "graph execution", None, (), task_id=task.task_id, trace_id=task.trace_id
            )
            tick = self.step_runtime.tick(
                tool_graph,
                task=task,
                context=task.execution_context,
                strategy=strategy,
            )
            runs[node_id] = {
                "state": tick.step_state,
                "tool_graph_run": tick.graph_run,
            }
        task.graph = TaskGraphRun(graph.definition, runs)
        if any(
            _graph_run_state(runs.get(item)) == "succeeded"
            for item in graph.definition.terminal_node_ids
        ):
            for candidate in graph.definition.nodes:
                if _graph_run_state(runs.get(candidate.node_id)) in {None, "pending", "ready"}:
                    runs[candidate.node_id] = {"state": "skipped"}
            task.graph = TaskGraphRun(graph.definition, runs)
            task.transition_to(TaskState.SUCCEEDED)
        self._persist(task)
        return self._result(creation)

    def _fail_graph_task(self, creation, code: str) -> TaskRuntimeResult:
        task = creation.task
        task.failure = {"code": code, "message": code.replace("_", " ")}
        task.failure_reason = code
        task.transition_to(TaskState.FAILED)
        self._persist(task)
        return self._result(creation, stop_reason=code, blocked=True, failure_reason=code)

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
        user_input = session.handoff.trigger_event.payload.get("text", "")
        if not isinstance(user_input, str):
            user_input = str(user_input)
        tool_results = tuple(
            ToolResult(
                tool_name=entry["tool_name"],
                task_id=entry["task_id"],
                trace_id=entry["trace_id"],
                payload=entry["payload"],
            )
            for entry in session.tool_trace
        )
        final_response, final_response_prompt_text = self._generate_final_response(
            creation,
            tool_results,
        )
        output = UserVisibleAgentOutput(
            process={
                "task_goal": session.handoff.task_goal,
                "user_input": user_input,
                "strategy": getattr(
                    session.current_strategy,
                    "skill_name",
                    None,
                ),
                "tool_results": tuple(
                    result.tool_name for result in tool_results
                ),
                "task_formulation_prompt_text": (
                    session.handoff.task_formulation_prompt_text
                ),
                "strategy_selection_prompt_text": session.task_local_state.get(
                    "strategy_selection_prompt_text",
                    "",
                ),
                "execution_decision_prompt_text": session.task_local_state.get(
                    "execution_decision_prompt_text",
                    "",
                ),
                "final_response_prompt_text": final_response_prompt_text,
                "timing": self._timing_dict(creation),
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
    ) -> tuple[str, str]:
        session = creation.session
        handoff = session.handoff
        trigger_payload = handoff.trigger_event.payload
        user_input = trigger_payload.get("text", "")
        if not isinstance(user_input, str):
            user_input = str(user_input)

        if self.final_response_generator is None:
            return (
                self._default_final_response(
                    task_goal=handoff.task_goal,
                    tool_results=tool_results,
                ),
                "",
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
        prompt_text = result.prompt_trace.get("prompt_text", "")
        return result.final_response, (
            prompt_text if isinstance(prompt_text, str) else str(prompt_text)
        )

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

    def _result(
        self,
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
            timing=self.timing_recorder.snapshot(creation.context.trace_id),
        )

    def _timing_dict(self, creation: TaskSessionCreation) -> dict:
        snapshot = self.timing_recorder.snapshot(creation.context.trace_id)
        return {} if snapshot is None else snapshot.to_dict()


def _graph_run_state(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        state = value.get("state")
    else:
        state = getattr(value, "state", None)
    return None if state is None else str(getattr(state, "value", state)).lower()
