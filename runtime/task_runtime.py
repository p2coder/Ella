from dataclasses import dataclass, field, replace
from collections.abc import Mapping
from datetime import datetime, timezone
from threading import Event, Lock, Thread
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from queue import Empty, Queue
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from agent.context import AgentExecutionContext
from agent.final_response import FinalResponseGenerator
from agent.handoff import HandoffRequest
from memory import MemoryManagementRequest, MemoryManager, MemoryWriteResult
from tasks.completion import FailureDeliveryPayload, TaskCompletionPackage
from agent.decision import CALL_TOOL, COMPLETE, ExecutionDecision
from tasks.state import (
    StepExecutionState,
    DeliveryAttempt,
    DeliveryOutcome,
    DeliveryPayloadType,
    TaskDeliveryRecord,
    TaskControlCommand,
    TaskControlResult,
    TaskControlType,
    ToolFailureKind,
    ToolFailureObservation,
    UncertainResolutionRecord,
)
from runtime.executor import CapabilityExecutor
from sessions.output import UserVisibleAgentOutput
from tasks.task import Task, TaskState
from tasks.graph import (
    GraphEdge,
    TaskGraphDefinition,
    TaskGraphNodeDefinition,
    TaskGraphRun,
    TaskGraphNodeType,
    ToolGraphRun,
)
from tasks.factory import TaskCreationResult, TaskFactory
from agent.subagent import DecisionValidationError, SubAgent
from tools import ToolResult
from tools.base import ToolUncertainPolicy
from .timing import (
    NoOpRuntimeTimingRecorder,
    RuntimeTimingRecorder,
    RuntimeTimingSnapshot,
)
from .task_queue import TaskQueue
from .task_store import TaskStore
from .step_runtime import StepRuntime, ToolNodeRun, ToolNodeRunState
from .trace import NoOpTraceRecorder, TraceRecorder
from .task_events import TaskEventPublisher, TERMINAL_TASK_STATES
from .interactions import InteractionBroker, UserAnswer


@dataclass(frozen=True, slots=True)
class TaskHandle:
    task_id: str
    trace_id: str

@dataclass(frozen=True, slots=True)
class TaskRuntimeResult:
    handle: TaskHandle
    task: Task
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
    task_factory: TaskFactory = field(default_factory=TaskFactory)
    subagent: SubAgent | None = None
    executor: CapabilityExecutor | None = None
    final_response_generator: FinalResponseGenerator | None = None
    timing_recorder: RuntimeTimingRecorder | NoOpRuntimeTimingRecorder
    max_step_retries: int = 2
    task_store: TaskStore | None = None
    task_queue: TaskQueue | None = None
    step_runtime: StepRuntime | None = None
    max_runtime_ticks: int = 100
    max_steps: int = 20
    max_task_workers: int = 500
    max_parallel_steps_per_task: int = 8
    wave_incremental_checkpoint_threshold: int = 20
    trace_recorder: TraceRecorder | NoOpTraceRecorder
    formulation_handler: Callable[[Task], HandoffRequest] | None
    event_publisher: TaskEventPublisher
    _memory_manager: MemoryManager = field(init=False, repr=False)
    _tasks: dict[str, TaskCreationResult] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _memory_results: dict[str, MemoryWriteResult] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _worker_thread: Thread | None = field(init=False, default=None, repr=False)
    _control_thread: Thread | None = field(init=False, default=None, repr=False)
    _task_worker_pool: ThreadPoolExecutor | None = field(init=False, default=None, repr=False)
    _stop_event: Event = field(init=False, repr=False)
    _wake_event: Event = field(init=False, repr=False)
    _worker_lock: Lock = field(init=False, repr=False)
    _persistence_lock: Lock = field(init=False, repr=False)
    _worker_errors: dict[str, str] = field(init=False, repr=False)
    _worker_results: dict[str, TaskRuntimeResult] = field(init=False, repr=False)
    _owned_tasks: dict[str, Future] = field(init=False, repr=False)
    _control_queue: Queue = field(init=False, repr=False)

    def __init__(
        self,
        task_factory: TaskFactory | None = None,
        subagent: SubAgent | None = None,
        executor: CapabilityExecutor | None = None,
        memory_manager: MemoryManager | None = None,
        final_response_generator: FinalResponseGenerator | None = None,
        timing_recorder: RuntimeTimingRecorder | NoOpRuntimeTimingRecorder | None = None,
        max_step_retries: int = 2,
        task_store: TaskStore | None = None,
        task_queue: TaskQueue | None = None,
        step_runtime: StepRuntime | None = None,
        max_runtime_ticks: int = 100,
        max_steps: int = 20,
        max_task_workers: int = 500,
        max_parallel_steps_per_task: int = 8,
        wave_incremental_checkpoint_threshold: int = 20,
        trace_recorder: TraceRecorder | NoOpTraceRecorder | None = None,
        formulation_handler: Callable[[Task], HandoffRequest] | None = None,
        event_publisher: TaskEventPublisher | None = None,
    ) -> None:
        if max_step_retries < 0:
            raise ValueError("max_step_retries must be non-negative")
        if max_task_workers < 1:
            raise ValueError("max_task_workers must be positive")
        self.task_factory = task_factory or TaskFactory()
        self.subagent = subagent
        self.executor = executor
        self.final_response_generator = final_response_generator
        self.timing_recorder = timing_recorder or NoOpRuntimeTimingRecorder()
        self.max_step_retries = max_step_retries
        self.task_store = task_store
        self.task_queue = task_queue
        self.step_runtime = step_runtime
        self.max_runtime_ticks = max_runtime_ticks
        self.max_steps = max_steps
        self.max_task_workers = max_task_workers
        self.max_parallel_steps_per_task = max_parallel_steps_per_task
        self.wave_incremental_checkpoint_threshold = (
            wave_incremental_checkpoint_threshold
        )
        self.trace_recorder = trace_recorder or NoOpTraceRecorder()
        self.formulation_handler = formulation_handler
        self.event_publisher = event_publisher or TaskEventPublisher()
        self._memory_manager = memory_manager or MemoryManager()
        self._tasks = {}
        self._memory_results = {}
        self._worker_thread = None
        self._control_thread = None
        self._task_worker_pool = None
        self._stop_event = Event()
        self._wake_event = Event()
        self._worker_lock = Lock()
        self._persistence_lock = Lock()
        self._worker_errors = {}
        self._worker_results = {}
        self._owned_tasks = {}
        self._control_queue = Queue()

    @property
    def is_running(self) -> bool:
        thread = self._worker_thread
        return thread is not None and thread.is_alive()

    def configure_formulation(
        self, handler: Callable[[Task], HandoffRequest]
    ) -> None:
        self.formulation_handler = handler

    def start(self) -> None:
        with self._worker_lock:
            if self.is_running:
                return
            self._stop_event.clear()
            self._restore_from_checkpoints()
            self._task_worker_pool = ThreadPoolExecutor(
                max_workers=self.max_task_workers,
                thread_name_prefix="ella-task-worker",
            )
            self._control_thread = Thread(
                target=self._control_loop,
                name="ella-control-worker",
                daemon=True,
            )
            self._control_thread.start()
            self._worker_thread = Thread(
                target=self._execution_loop,
                name="ella-task-runtime",
                daemon=True,
            )
            self._worker_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        broker = self._interaction_broker()
        if broker is not None:
            for task_id in tuple(self._owned_tasks):
                broker.cancel_task(task_id)

    def join(self, timeout: float | None = None) -> bool:
        thread = self._worker_thread
        if thread is None:
            return True
        thread.join(timeout)
        control = self._control_thread
        if control is not None:
            control.join(timeout)
        pool = self._task_worker_pool
        if pool is not None and not thread.is_alive():
            pool.shutdown(wait=True, cancel_futures=False)
            self._task_worker_pool = None
        return not thread.is_alive() and (control is None or not control.is_alive())

    def schedule(self, task_id: str) -> bool:
        if task_id in self._owned_tasks:
            self._wake_event.set()
            return True
        if self.task_queue is None:
            self.task_queue = TaskQueue()
        enqueued = self.task_queue.enqueue(task_id)
        self._wake_event.set()
        return enqueued

    def result_for(self, task_id: str) -> TaskRuntimeResult:
        result = self._worker_results.get(task_id)
        if result is not None:
            return result
        creation = self._tasks.get(task_id)
        if creation is None:
            raise KeyError(task_id)
        return self._result(
            creation,
            stop_reason=self._stop_reason(creation.task),
            memory_result=self._memory_results.get(task_id),
            failure_reason=self._worker_errors.get(task_id),
            record_trace=False,
        )

    def _execution_loop(self) -> None:
        while not self._stop_event.is_set():
            self._reap_task_workers()
            if len(self._owned_tasks) >= self.max_task_workers:
                self._wake_event.wait(0.05)
                self._wake_event.clear()
                continue
            queue = self.task_queue
            task_id = None if queue is None else queue.dequeue()
            if task_id is None:
                self._wake_event.wait(0.1)
                self._wake_event.clear()
                continue
            creation = self._tasks.get(task_id)
            if creation is None:
                continue
            if task_id in self._owned_tasks:
                continue
            pool = self._task_worker_pool
            if pool is None:
                return
            future = pool.submit(self._run_task_worker, creation)
            self._owned_tasks[task_id] = future

    def _reap_task_workers(self) -> None:
        completed = tuple(
            task_id
            for task_id, future in self._owned_tasks.items()
            if future.done()
        )
        for task_id in completed:
            future = self._owned_tasks.pop(task_id)
            try:
                future.result()
            except Exception as error:
                self._worker_errors[task_id] = str(error)
            self._wake_event.set()

    def _run_task_worker(self, creation: TaskCreationResult) -> None:
        task = creation.task
        self._trace_task(
            task,
            "runtime.worker",
            "claimed",
            {"state": task.state.value},
        )
        try:
            while not self._stop_event.is_set():
                if task.state in TERMINAL_TASK_STATES:
                    return
                if task.state is TaskState.PAUSED:
                    self._wake_event.wait(0.05)
                    self._wake_event.clear()
                    continue
                self._process_scheduled_task(creation)
        except Exception as error:
            self._worker_errors[task.task_id] = str(error)
            self._handle_worker_exception(task, error)
        finally:
            self._publish_terminal(task)
            self._trace_task(
                task,
                "runtime.worker",
                "released",
                {"state": task.state.value},
            )

    def _process_scheduled_task(self, creation: TaskCreationResult) -> None:
        task = creation.task
        if task.state in {TaskState.CREATED, TaskState.FORMULATING}:
            if self.formulation_handler is None:
                raise RuntimeError("TaskRuntime has no formulation handler")
            if task.state is TaskState.CREATED:
                self.begin_formulation(task.task_id)
            handoff = self.formulation_handler(task)
            if task.state in {
                TaskState.PAUSE_REQUESTED,
                TaskState.KILL_REQUESTED,
            }:
                self._reach_control_safe_point(task)
                return
            self._trace_task(
                task,
                "reasoning.formulation",
                "completed",
                {
                    "task_goal": handoff.task_goal,
                    "prompt_text": handoff.task_formulation_prompt_text,
                },
            )
            self.submit_formulated(task.task_id, handoff)
            return
        if task.state not in {TaskState.READY, TaskState.REASONING, TaskState.TOOL_EXECUTION}:
            return
        result = self.run_until_complete(task.task_id, self.max_steps)
        reached_control_safe_point = self._reach_control_safe_point(task)
        self._worker_results[task.task_id] = (
            self._result(
                creation,
                steps=result.steps,
                stop_reason=self._stop_reason(task),
                blocked=result.blocked,
            )
            if reached_control_safe_point
            else result
        )
        if result.stop_reason == "max_steps" and task.state is TaskState.REASONING:
            task.failure = {
                "code": "max_steps_exhausted",
                "message": "Task execution exhausted its step budget.",
            }
            task.failure_reason = task.failure["message"]
            task.transition_to(TaskState.FAILED)
            self._persist(task)
            self._trace_task(task, "task", "failed", task.failure)
            self._worker_results[task.task_id] = self._result(
                creation,
                stop_reason="failed",
                failure_reason=task.failure_reason,
            )

    def _handle_worker_exception(self, task: Task, error: Exception) -> None:
        in_flight = task.task_local_state.get("in_flight_action")
        if in_flight and task.state is TaskState.TOOL_EXECUTION:
            task.failure = {
                "code": "uncertain_in_flight_action",
                "message": (
                    "Runtime stopped after dispatching a Tool and could not "
                    "confirm its external outcome."
                ),
                "tool_name": in_flight.get("tool_name"),
            }
            task.failure_reason = task.failure["message"]
            task.transition_to(TaskState.UNCERTAIN)
            self._persist(task)
            self._trace_task(
                task,
                "recovery",
                "in_flight_action_uncertain",
                {"error": str(error), **dict(in_flight)},
            )
            return
        if task.state is TaskState.CREATED:
            task.transition_to(TaskState.FORMULATING)
        if task.state in {
            TaskState.FORMULATING,
            TaskState.READY,
            TaskState.REASONING,
            TaskState.TOOL_EXECUTION,
        }:
            task.failure = {
                "code": "runtime_worker_failed",
                "message": str(error),
            }
            task.failure_reason = str(error)
            task.transition_to(TaskState.FAILED)
            self._persist(task)
        self._trace_task(
            task,
            "runtime.worker",
            "failed",
            {"error": str(error), "state": task.state.value},
        )

    def _restore_from_checkpoints(self) -> None:
        if self.task_store is None:
            return
        for stored in self.task_store.list():
            task = stored.task
            if task.execution_context is None:
                continue
            self._tasks[task.task_id] = TaskCreationResult(task)
            self._trace_task(
                task,
                "recovery",
                "checkpoint_loaded",
                {"state": task.state.value, "version": stored.version},
            )
            in_flight = task.task_local_state.get("in_flight_action")
            if in_flight and task.state is TaskState.TOOL_EXECUTION:
                if bool(in_flight.get("safe_to_retry")):
                    task.task_local_state.pop("in_flight_action", None)
                    self._persist(task)
                    self._trace_task(
                        task,
                        "recovery",
                        "safe_action_requeued",
                        dict(in_flight),
                    )
                else:
                    task.failure = {
                        "code": "uncertain_in_flight_action",
                        "message": (
                            "A Tool may have changed external state before the "
                            "previous process stopped."
                        ),
                        "tool_name": in_flight.get("tool_name"),
                    }
                    task.failure_reason = task.failure["message"]
                    task.transition_to(TaskState.UNCERTAIN)
                    self._persist(task)
                    self._trace_task(
                        task,
                        "recovery",
                        "in_flight_action_uncertain",
                        dict(in_flight),
                    )
                    self._publish_terminal(task)
                    continue
            if task.state is TaskState.PAUSE_REQUESTED:
                task.transition_to(TaskState.PAUSED)
                self._persist(task)
            elif task.state is TaskState.KILL_REQUESTED:
                task.transition_to(TaskState.KILLED)
                self._persist(task)
            elif task.state in {
                TaskState.CREATED,
                TaskState.FORMULATING,
                TaskState.READY,
                TaskState.REASONING,
                TaskState.TOOL_EXECUTION,
            }:
                self.schedule(task.task_id)
            self._trace_task(
                task,
                "recovery",
                "restored",
                {"state": task.state.value},
            )

    def create_task(self, source_event) -> TaskHandle:
        task_id = self.task_factory._new_task_id()
        scope = self.task_factory._resolve_capability_scope()
        context = AgentExecutionContext(
            agent_id=self.task_factory.agent_id,
            agent_role=self.task_factory.agent_role,
            parent_agent_id=self.task_factory.parent_agent_id,
            task_id=task_id,
            trace_id=source_event.trace_id,
            handoff_goal="",
            memory_scope=self.task_factory.memory_scope,
            permissions=self.task_factory.permissions,
            capability_scope=scope,
        )
        task = Task(
            task_id=task_id,
            trace_id=source_event.trace_id,
            source_event=source_event,
            execution_context=context,
        )
        creation = TaskCreationResult(task)
        self._tasks[task_id] = creation
        self._persist(task)
        self._trace_task(task, "task", "created")
        if self.is_running:
            self.schedule(task_id)
        return TaskHandle(task_id, source_event.trace_id)

    def begin_formulation(self, task_id: str) -> None:
        task = self._tasks[task_id].task
        task.transition_to(TaskState.FORMULATING)
        self._persist(task)
        self._trace_task(task, "reasoning.formulation", "started")

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
        self._trace_task(task, "task", "submitted")
        if self.task_queue is not None or self.is_running:
            self.schedule(task_id)
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
        self._trace_task(task, "reasoning.formulation", "failed", task.failure)
        self._publish_terminal(task)

    def _persist(self, task: Task) -> None:
        with self._persistence_lock:
            if self.task_store is not None:
                current = self.task_store.version(task.task_id)
                self.task_store.save(task, expected_version=current)
            self.event_publisher.publish_checkpoint(task)

    def list_tasks(self) -> tuple[Task, ...]:
        return tuple(
            creation.task
            for _, creation in sorted(self._tasks.items())
        )

    def provide_input(
        self,
        task_id: str,
        *,
        correlation_key: str,
        value: str,
    ) -> bool:
        broker = self._interaction_broker()
        if broker is None:
            return False
        question = next(
            (
                item
                for item in broker.pending_for_task(task_id)
                if item.question_id == correlation_key
            ),
            None,
        )
        if question is None:
            return False
        accepted = broker.answer(
            UserAnswer(
                question_id=question.question_id,
                task_id=task_id,
                user_id=question.user_id,
                answer=value,
                metadata={},
            )
        )
        if accepted:
            task = self._tasks[task_id].task
            self._trace_task(
                task,
                "interaction.ask_user_question",
                "answered",
                {"question_id": question.question_id},
            )
        return accepted

    def _interaction_broker(self) -> InteractionBroker | None:
        if self.executor is None:
            return None
        tool = self.executor.tool_manager.get_tool("ask_user_question")
        broker = getattr(tool, "broker", None)
        return broker if isinstance(broker, InteractionBroker) else None

    def apply_control(self, command: TaskControlCommand) -> TaskControlResult:
        control = self._control_thread
        if control is None or not control.is_alive():
            return self._apply_control_now(command)
        completed = Event()
        result_box: list[TaskControlResult | Exception] = []
        self._control_queue.put((command, completed, result_box))
        self._wake_event.set()
        completed.wait()
        result = result_box[0]
        if isinstance(result, Exception):
            raise result
        return result

    def _control_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                command, completed, result_box = self._control_queue.get(
                    timeout=0.05
                )
            except Empty:
                continue
            try:
                result_box.append(self._apply_control_now(command))
            except Exception as error:
                result_box.append(error)
            finally:
                completed.set()

    def _apply_control_now(
        self, command: TaskControlCommand
    ) -> TaskControlResult:
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
            if task.state in {
                TaskState.SUCCEEDED,
                TaskState.FAILED,
                TaskState.UNCERTAIN,
                TaskState.PAUSE_REQUESTED,
                TaskState.KILLED,
                TaskState.DELIVERED,
            }:
                accepted, code, message = False, "terminal_task", "Terminal Task cannot be killed."
            else:
                task.control_request = command
                broker = self._interaction_broker()
                if broker is not None:
                    broker.cancel_task(task.task_id)
                if task.state is not TaskState.KILL_REQUESTED:
                    task.transition_to(TaskState.KILL_REQUESTED)
                if previous_state not in {
                    TaskState.FORMULATING,
                    TaskState.REASONING,
                    TaskState.TOOL_EXECUTION,
                }:
                    task.failure = {
                        "code": "task_killed",
                        "message": (
                            command.reason
                            or "Task was cancelled before completion."
                        ),
                    }
                    task.failure_reason = task.failure["message"]
                    task.transition_to(TaskState.KILLED)
        elif command.command_type is TaskControlType.PAUSE:
            if task.state in {TaskState.KILL_REQUESTED, TaskState.KILLED}:
                accepted, code, message = False, "kill_has_priority", "Kill has priority over pause."
            elif task.state not in {TaskState.CREATED, TaskState.FORMULATING, TaskState.READY, TaskState.REASONING, TaskState.TOOL_EXECUTION}:
                accepted, code, message = False, "invalid_state", "Task cannot be paused from its current state."
            else:
                task.paused_from_state = task.state
                task.control_request = command
                broker = self._interaction_broker()
                if broker is not None:
                    broker.cancel_task(task.task_id)
                task.transition_to(TaskState.PAUSE_REQUESTED)
                if previous_state not in {
                    TaskState.FORMULATING,
                    TaskState.REASONING,
                    TaskState.TOOL_EXECUTION,
                }:
                    task.transition_to(TaskState.PAUSED)
        elif command.command_type is TaskControlType.RESUME:
            if task.state is not TaskState.PAUSED or task.paused_from_state is None:
                accepted, code, message = False, "invalid_state", "Only a paused Task can resume."
            else:
                task.control_request = command
                resume_state = task.paused_from_state
                task.transition_to(resume_state)
                task.paused_from_state = None
                broker = self._interaction_broker()
                if broker is not None:
                    broker.reset_task(task.task_id)
                if self.task_queue is not None or self.is_running:
                    self.schedule(task.task_id)
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
            self._trace_task(
                task,
                "control",
                command.command_type.value,
                {"previous_state": previous_state.value, "state": task.state.value},
            )
            self._publish_terminal(task)
        return result

    def _reach_control_safe_point(self, task: Task) -> bool:
        if task.state is TaskState.PAUSE_REQUESTED:
            task.transition_to(TaskState.PAUSED)
            self._persist(task)
            self._trace_task(
                task,
                "control",
                "paused_at_safe_point",
                {
                    "paused_from_state": (
                        None
                        if task.paused_from_state is None
                        else task.paused_from_state.value
                    )
                },
            )
            return True
        if task.state is TaskState.KILL_REQUESTED:
            reason = getattr(task.control_request, "reason", None)
            task.failure = {
                "code": "task_killed",
                "message": reason or "Task was cancelled before completion.",
            }
            task.failure_reason = task.failure["message"]
            task.transition_to(TaskState.KILLED)
            self._persist(task)
            self._trace_task(task, "control", "killed_at_safe_point")
            self._publish_terminal(task)
            return True
        return False

    def resolve_uncertain_as_failed(self, task_id: str, reason: str) -> None:
        task = self._tasks[task_id].task
        if task.state is not TaskState.UNCERTAIN:
            raise ValueError("only an UNCERTAIN Task can be resolved")
        attempt = task.task_local_state.get("uncertain_attempt", {})
        task.uncertain_resolution = UncertainResolutionRecord(
            resolution="treated_as_failed",
            tool_name=str(attempt.get("tool_name", "unknown_tool")),
            arguments=dict(attempt.get("arguments", {})),
            invoked_at=attempt.get("invoked_at"),
            reason=reason,
            possible_side_effects=tuple(
                attempt.get("possible_side_effects", ("external outcome unknown",))
            ),
            resolved_at=datetime.now(timezone.utc),
        )
        task.failure = {
            "code": "uncertain_outcome_treated_as_failed",
            "message": reason,
            "external_outcome_unknown": True,
        }
        task.failure_reason = reason
        task.transition_to(TaskState.FAILED)
        self._persist(task)
        self._publish_terminal(task)

    def deliver(self, task_id: str, sender) -> bool:
        task = self._tasks[task_id].task
        if task.state not in {TaskState.SUCCEEDED, TaskState.FAILED}:
            raise ValueError("only SUCCEEDED or FAILED Tasks can be delivered")
        delivery = task.delivery
        if delivery is None:
            delivery = self._new_delivery_record(task)
        attempted_at = datetime.now(timezone.utc)
        failure_code = None
        try:
            sender(delivery.payload)
            succeeded = True
        except Exception as error:
            succeeded = False
            failure_code = type(error).__name__
        attempt = DeliveryAttempt(
            attempt_id=f"delivery-{uuid4().hex}",
            succeeded=succeeded,
            attempted_at=attempted_at,
            failure_code=failure_code,
        )
        task.delivery = replace(
            delivery,
            attempts=(*delivery.attempts, attempt),
            delivered_at=attempted_at if succeeded else None,
        )
        if succeeded:
            task.transition_to(TaskState.DELIVERED)
        self._persist(task)
        self._publish_terminal(task)
        return succeeded

    @staticmethod
    def _new_delivery_record(task: Task) -> TaskDeliveryRecord:
        if task.state is TaskState.SUCCEEDED:
            payload = (
                task.completion.to_dict()
                if task.completion is not None
                else {"task_goal": task.handoff.task_goal, "outcome": "succeeded"}
            )
            return TaskDeliveryRecord(
                DeliveryOutcome.SUCCEEDED,
                DeliveryPayloadType.SUCCESS_RESULT,
                payload,
            )
        failure = task.failure if isinstance(task.failure, Mapping) else {}
        unknown = ()
        payload_type = DeliveryPayloadType.FAILURE_REPORT
        if failure.get("external_outcome_unknown"):
            payload_type = DeliveryPayloadType.UNCERTAIN_FAILURE_REPORT
            unknown = tuple(
                getattr(task.uncertain_resolution, "possible_side_effects", ())
            )
        payload = FailureDeliveryPayload(
            task_goal=task.handoff.task_goal if task.handoff is not None else "",
            reason=task.failure_reason or str(failure.get("message", "task failed")),
            unknown_side_effects=unknown,
        ).to_dict()
        payload["message"] = FinalResponseGenerator.failure_report_text(payload)
        return TaskDeliveryRecord(
            DeliveryOutcome.FAILED,
            payload_type,
            payload,
        )

    def submit(self, handoff: HandoffRequest) -> TaskHandle:
        
        creation = self.task_factory.create_task(handoff)
        creation.task.current_step = replace(
            creation.task.current_step,
            max_step_retries=self.max_step_retries,
        )
        task_id = creation.task.task_id
        if task_id in self._tasks:
            raise ValueError(f"duplicate task_id: {task_id}")
        creation.task.transition_to(TaskState.READY)
        self._tasks[task_id] = creation
        self._persist(creation.task)
        if self.task_queue is not None or self.is_running:
            self.schedule(task_id)
        self._trace_task(creation.task, "task", "submitted")
        self.timing_recorder.record_task_submitted(
            creation.context.trace_id,
            task_id=task_id,
        )
        return TaskHandle(
            task_id=task_id,
            trace_id=creation.context.trace_id,
        )

    def get_task(self, task_id: str) -> Task:
        return self._tasks[task_id].task

    def get_context(self, task_id: str) -> AgentExecutionContext:
        return self._tasks[task_id].context

    def step(self, task_id: str) -> TaskRuntimeResult:
        creation = self._tasks[task_id]
        task = creation.task
        if task.graph is not None and task.state is TaskState.REASONING:
            return self._step_task_graph(creation)
        self.timing_recorder.record_task_processing_started(
            creation.context.trace_id
        )

        if task.state in {
            TaskState.SUCCEEDED,
            TaskState.FAILED,
            TaskState.KILLED,
            TaskState.DELIVERED,
        }:
            raise ValueError(f"cannot step terminal task: {task.state.value}")
        if task.state is TaskState.CREATED:
            raise ValueError("CREATED task must be formulated before execution")

        subagent, executor = self._execution_components()

        if task.state is TaskState.READY:
            task.transition_to(TaskState.REASONING)
            self._persist(task)
            self._trace_task(
                task,
                "reasoning.execution_decision",
                "ready",
                {"state": task.state.value},
            )
            return self._result(creation)

        self.timing_recorder.record_execution_started(creation.context.trace_id)
        self._persist(task)
        saved_decision = task.task_local_state.get("current_decision")
        if isinstance(saved_decision, Mapping):
            decision = ExecutionDecision.from_dict(saved_decision)
            self._trace_task(
                task,
                "reasoning.execution_decision",
                "restored",
                {"action": decision.action, "tool_name": decision.tool_name},
            )
        else:
            try:
                decision = subagent.decide_next_action(
                    task.handoff,
                    creation.context,
                    task,
                )
            except DecisionValidationError as error:
                self._handle_decision_failure(task, str(error))
                self._persist(task)
                return self._result(creation)
            task.task_local_state["current_decision"] = decision.to_dict()
            self._persist(task)
            self._trace_task(
                task,
                "reasoning.execution_decision",
                "completed",
                {
                    "action": decision.action,
                    "tool_name": decision.tool_name,
                    "decision_reason": decision.decision_reason,
                    "completion_summary": decision.completion_summary,
                    "evidence_refs": decision.evidence_refs,
                    "prompt_text": task.task_local_state.get(
                        "execution_decision_prompt_text",
                        "",
                    ),
                },
            )
        if task.state in {
            TaskState.PAUSE_REQUESTED,
            TaskState.PAUSED,
            TaskState.KILL_REQUESTED,
            TaskState.KILLED,
        }:
            return self._result(creation, stop_reason=self._stop_reason(task))

        repair_violation = self._repair_violation(task, decision)
        if repair_violation is not None:
            task.task_local_state.pop("current_decision", None)
            self._handle_failure(task, repair_violation)
            self._persist(task)
            return self._result(creation)

        in_flight = None
        if decision.action == CALL_TOOL and decision.tool_name is not None:
            tool = executor.tool_manager.get_tool(decision.tool_name)
            definition = None if tool is None else tool.definition
            in_flight = {
                "attempt_id": task.current_step.attempt_id,
                "tool_name": decision.tool_name,
                "arguments": decision.tool_input or {},
                "safe_to_retry": bool(
                    definition is not None
                    and definition.uncertain_policy is ToolUncertainPolicy.NEVER
                    and not definition.side_effecting
                ),
            }
            task.task_local_state["in_flight_action"] = in_flight
            if task.state is TaskState.REASONING:
                task.transition_to(TaskState.TOOL_EXECUTION)
            self._persist(task)
            self._trace_task(
                task,
                f"tool_attempt.{decision.tool_name}",
                "dispatched",
                in_flight,
            )
            self.event_publisher.publish_progress(
                task,
                execution_stage="tool_execution",
                tool_name=decision.tool_name,
            )
        execution = executor.execute(decision, creation.context, task)
        if in_flight is not None:
            task.task_local_state.pop("in_flight_action", None)
            if task.state is TaskState.TOOL_EXECUTION:
                task.transition_to(TaskState.REASONING)
            self._persist(task)
            self._trace_task(
                task,
                f"tool_attempt.{decision.tool_name}",
                "failed" if execution.failure is not None else "completed",
                {
                    "attempt_id": in_flight["attempt_id"],
                    "failure": (
                        None
                        if execution.failure is None
                        else execution.failure.to_dict()
                    ),
                },
            )
        if task.state in {
            TaskState.PAUSE_REQUESTED,
            TaskState.PAUSED,
            TaskState.KILL_REQUESTED,
            TaskState.KILLED,
        }:
            return self._result(creation, stop_reason=self._stop_reason(task))
        if execution.failure is not None:
            task.task_local_state.pop("current_decision", None)
            self._trace_task(
                task,
                f"tool_attempt.{decision.tool_name or 'none'}",
                "rejected",
                execution.failure.to_dict(),
            )
            self._handle_failure(task, execution.failure)
            return self._result(creation)

        if execution.tool_result is not None:
            observation = execution.tool_result.to_dict()
            observation["observation_id"] = (
                f"{task.task_id}:observation:{len(task.tool_trace) + 1}"
            )
            task.tool_trace += (observation,)
            self._observe_capability_result(task, execution.tool_result)
            task.task_local_state.pop("current_decision", None)
            self._archive_and_advance(task)
            self._persist(task)

        if decision.action == COMPLETE:
            task.task_local_state.pop("current_decision", None)
            task.task_local_state["completion_summary"] = decision.completion_summary
            task.task_local_state["completion_evidence_refs"] = decision.evidence_refs
            self._archive_and_advance(task)
            self.timing_recorder.record_execution_completed(
                creation.context.trace_id
            )
            task.completion = self._build_completion(creation)
            self.timing_recorder.record_task_completed(creation.context.trace_id)
            task.transition_to(TaskState.SUCCEEDED)
            self._trace_task(
                task,
                "task",
                "succeeded",
                {"state": task.state.value},
            )
            return self._result(creation, stop_reason="completed")

        return self._result(creation)

    def _handle_decision_failure(self, task: Task, message: str) -> None:
        step = task.current_step
        if step.retry_index < step.max_step_retries:
            task.current_step = replace(
                step,
                retry_index=step.retry_index + 1,
            )
            self._trace_task(
                task,
                "reasoning.execution_decision",
                "repair_requested",
                {"message": message, "retry_index": task.current_step.retry_index},
            )
            return
        task.failure = {
            "code": "decision_repair_exhausted",
            "message": message,
        }
        task.failure_reason = message
        task.transition_to(TaskState.FAILED)

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
        ready = []
        for node in graph.definition.nodes:
            if node.node_type is not TaskGraphNodeType.STEP:
                continue
            if _graph_run_state(runs.get(node.node_id)) not in {None, "pending", "ready"}:
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
        wave_id = int(task.task_local_state.get("wave_number", 0)) + 1
        task.task_local_state["wave_number"] = wave_id
        node_by_id = {node.node_id: node for node in graph.definition.nodes}
        for node_id in ordered:
            runs[node_id] = {"state": "running", "wave_id": wave_id}
        task.graph = TaskGraphRun(graph.definition, runs)
        self._persist(task)

        results: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(
            max_workers=min(self.max_parallel_steps_per_task, len(ordered)),
            thread_name_prefix=f"ella-{task.task_id}-wave-{wave_id}",
        ) as pool:
            futures = {
                pool.submit(
                    self._execute_graph_node,
                    creation,
                    node_by_id[node_id],
                    wave_id,
                ): node_id
                for node_id in ordered
            }
            for future in as_completed(futures):
                node_id = futures[future]
                try:
                    results[node_id] = future.result()
                except Exception as error:
                    results[node_id] = {
                        "state": "failed",
                        "code": "node_execution_failed",
                        "message": str(error),
                        "wave_id": wave_id,
                    }
                if len(ordered) > self.wave_incremental_checkpoint_threshold:
                    runs[node_id] = results[node_id]
                    task.graph = TaskGraphRun(graph.definition, runs)
                    self._persist(task)

        plan_payload = None
        for node_id in graph.definition.stable_ready_order(results):
            runs[node_id] = results[node_id]
            for observation in results[node_id].get("observations", ()):
                task.tool_trace += (observation,)
                if observation.get("tool_name") == "plan_written":
                    plan_payload = observation.get("payload")
        task.graph = TaskGraphRun(graph.definition, runs)
        task.task_local_state["wave_completed"] = wave_id
        if isinstance(plan_payload, Mapping):
            self._activate_plan(task, plan_payload)
            self._persist(task)
            return self._result(creation)
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

    def _execute_graph_node(self, creation, node, wave_id: int) -> dict[str, Any]:
        task = creation.task
        payload = dict(node.payload) if isinstance(node.payload, Mapping) else {}
        goal = str(payload.get("goal") or node.node_id)
        criteria = tuple(payload.get("completion_criteria", ()))
        local = Task(
            task_id=task.task_id,
            handoff=task.handoff,
            state=TaskState.REASONING,
            trace_id=task.trace_id,
            source_event=task.source_event,
            execution_context=task.execution_context,
            tool_trace=task.tool_trace,
            current_step=StepExecutionState(max_step_retries=self.max_step_retries),
        )
        subagent, executor = self._execution_components()
        start_trace_len = len(local.tool_trace)
        for _ in range(self.max_steps):
            try:
                decision = subagent.decide_next_action(
                    task.handoff,
                    creation.context,
                    local,
                    current_goal=goal,
                    completion_criteria=criteria,
                )
            except DecisionValidationError as error:
                if local.current_step.retry_index >= local.current_step.max_step_retries:
                    return {"state": "failed", "code": "decision_repair_exhausted", "message": str(error), "wave_id": wave_id}
                local.current_step = replace(local.current_step, retry_index=local.current_step.retry_index + 1)
                continue
            if decision.action == COMPLETE:
                return {
                    "state": "succeeded",
                    "wave_id": wave_id,
                    "completion_summary": decision.completion_summary,
                    "evidence_refs": decision.evidence_refs,
                    "observations": local.tool_trace[start_trace_len:],
                }
            local.state = TaskState.TOOL_EXECUTION
            execution = executor.execute(decision, creation.context, local)
            local.state = TaskState.REASONING
            if execution.uncertain:
                return {"state": "uncertain", "wave_id": wave_id, "failure": None if execution.failure is None else execution.failure.to_dict()}
            if execution.failure is not None:
                local.current_step = replace(local.current_step, failures=(*local.current_step.failures, execution.failure))
                continue
            observation = execution.tool_result.to_dict()
            observation["observation_id"] = f"{task.task_id}:{node.node_id}:observation:{len(local.tool_trace) + 1}"
            local.tool_trace += (observation,)
        return {"state": "failed", "code": "max_steps_exhausted", "wave_id": wave_id}

    def _observe_capability_result(self, task: Task, result: ToolResult) -> None:
        if result.tool_name == "plan_written":
            self._activate_plan(task, result.payload)

    @staticmethod
    def _activate_plan(task: Task, payload: Mapping[str, Any]) -> None:
        if payload.get("task_id") != task.task_id:
            raise ValueError("plan result task_id does not match Task")
        version_id = payload.get("version_id")
        raw_steps = payload.get("steps")
        if not isinstance(version_id, str) or not version_id:
            raise ValueError("plan result requires version_id")
        if not isinstance(raw_steps, (list, tuple)) or not raw_steps:
            raise ValueError("plan result requires steps")
        nodes = tuple(
            TaskGraphNodeDefinition(
                node_id=str(item["step_id"]),
                node_type=TaskGraphNodeType.STEP,
                payload={
                    "goal": str(item["goal"]),
                    "completion_criteria": tuple(item["completion_criteria"]),
                },
            )
            for item in raw_steps
        )
        edges = tuple(
            GraphEdge(str(dependency), str(item["step_id"]))
            for item in raw_steps
            for dependency in item.get("depends_on", ())
        )
        depended_on = {edge.from_node_id for edge in edges}
        entries = tuple(
            str(item["step_id"])
            for item in raw_steps
            if not item.get("depends_on")
        )
        terminals = tuple(
            str(item["step_id"])
            for item in raw_steps
            if str(item["step_id"]) not in depended_on
        )
        definition = TaskGraphDefinition(
            graph_id=f"plan-{task.task_id}",
            version=version_id,
            nodes=nodes,
            edges=edges,
            entry_node_ids=entries,
            terminal_node_ids=terminals,
        )
        previous_runs = {} if task.graph is None else task.graph.node_runs
        migrated = {
            node.node_id: previous_runs[node.node_id]
            for node in nodes
            if node.node_id in previous_runs
            and _graph_run_state(previous_runs[node.node_id]) == "succeeded"
        }
        task.graph = TaskGraphRun(definition, migrated)
        task.task_local_state["active_plan_version"] = version_id

    def _fail_graph_task(self, creation, code: str) -> TaskRuntimeResult:
        task = creation.task
        task.failure = {"code": code, "message": code.replace("_", " ")}
        task.failure_reason = code
        task.transition_to(TaskState.FAILED)
        self._persist(task)
        return self._result(creation, stop_reason=code, blocked=True, failure_reason=code)

    def _repair_violation(
        self,
        session: Task,
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
        session: Task,
        failure: ToolFailureObservation,
    ) -> None:
        step = session.current_step
        failures = (*step.failures, failure)
        if failure.kind in {
            ToolFailureKind.INVALID_ARGUMENTS,
            ToolFailureKind.INVALID_ARGUMENTS_REPAIR_VIOLATION,
        }:
            active_tool = step.active_tool_name or failure.tool_name
            if step.retry_index < step.max_step_retries:
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
    def _archive_and_advance(session: Task) -> None:
        archived = session.current_step
        session.step_history += (archived,)
        session.current_step = StepExecutionState(
            step_number=archived.step_number + 1,
            max_step_retries=archived.max_step_retries,
        )

    def run_until_blocked(
        self,
        task_id: str,
        max_steps: int,
    ) -> TaskRuntimeResult:
        if max_steps < 0:
            raise ValueError("max_steps must be non-negative")

        creation = self._tasks[task_id]
        stop_reason = self._stop_reason(creation.task)
        if stop_reason is not None:
            return self._result(
                creation,
                stop_reason=stop_reason,
                blocked=self._is_blocked_reason(stop_reason),
            )

        for steps in range(1, max_steps + 1):
            task = creation.task
            self._persist(task)
            self._trace_task(
                task,
                f"step.{task.current_step.attempt_id}",
                "started",
                {"state": task.state.value},
            )
            self.step(task_id)
            self._persist(task)
            self._trace_task(
                task,
                f"step.{task.current_step.attempt_id}",
                "checkpointed",
                {"state": task.state.value},
            )
            stop_reason = self._stop_reason(creation.task)
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
            runtime_result.task.state is not TaskState.SUCCEEDED
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
            self._trace_task(
                runtime_result.task,
                "memory",
                "written",
                {"action": getattr(memory_result, "action", "written")},
            )

        self._publish_terminal(
            runtime_result.task,
            memory_result=memory_result,
        )

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
    def _stop_reason(task: Task) -> str | None:
        if task.state in {TaskState.PAUSE_REQUESTED, TaskState.PAUSED}:
            return "paused"
        if task.state is TaskState.SUCCEEDED:
            return "completed"
        if task.state is TaskState.FAILED:
            return "failed"
        if task.state is TaskState.KILLED:
            return "killed"
        if task.state is TaskState.UNCERTAIN:
            return "uncertain"
        if task.state is TaskState.DELIVERED:
            return "delivered"
        return None

    @staticmethod
    def _is_blocked_reason(stop_reason: str) -> bool:
        return stop_reason == "max_steps"

    def _build_completion(
        self,
        creation: TaskCreationResult,
    ) -> TaskCompletionPackage:
        session = creation.task
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
        self._trace_task(
            session,
            "reasoning.final_response",
            "started",
            {"tool_result_count": len(tool_results)},
        )
        final_response, final_response_prompt_text = self._generate_final_response(
            creation,
            tool_results,
        )
        self._trace_task(
            session,
            "reasoning.final_response",
            "completed",
            {
                "response_length": len(final_response),
                "prompt_text": final_response_prompt_text,
                "final_response": final_response,
            },
        )
        output = UserVisibleAgentOutput(
            process={
                "task_goal": session.handoff.task_goal,
                "user_input": user_input,
                "strategy": None,
                "tool_results": tuple(
                    result.tool_name for result in tool_results
                ),
                "task_formulation_prompt_text": (
                    session.handoff.task_formulation_prompt_text
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
        creation: TaskCreationResult,
        tool_results: tuple[ToolResult, ...],
    ) -> tuple[str, str]:
        session = creation.task
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
            completion_summary=str(
                session.task_local_state.get("completion_summary", "")
            ),
            evidence_refs=tuple(
                session.task_local_state.get("completion_evidence_refs", ())
            ),
        )
        prompt_text = result.prompt_trace.get("prompt_text", "")
        return result.final_response, (
            prompt_text if isinstance(prompt_text, str) else str(prompt_text)
        )

    @staticmethod
    def _execution_failures(
        session: Task,
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
        creation: TaskCreationResult,
        steps: int = 0,
        stop_reason: str | None = None,
        blocked: bool = False,
        memory_result: MemoryWriteResult | None = None,
        failure_reason: str | None = None,
        record_trace: bool = True,
    ) -> TaskRuntimeResult:
        timing = self.timing_recorder.snapshot(creation.context.trace_id)
        if record_trace:
            self._trace_task(
                creation.task,
                "task_node.runtime",
                "state_observed",
                {
                    "state": creation.task.state.value,
                    "stop_reason": stop_reason,
                    "timing": None if timing is None else timing.to_dict(),
                },
            )
        return TaskRuntimeResult(
            handle=TaskHandle(
                task_id=creation.task.task_id,
                trace_id=creation.context.trace_id,
            ),
            task=creation.task,
            context=creation.context,
            completion=creation.task.completion,
            steps=steps,
            stop_reason=stop_reason,
            blocked=blocked,
            memory_result=memory_result,
            failure_reason=failure_reason,
            logical_steps=len(creation.task.step_history),
            timing=timing,
        )

    def _trace_task(
        self,
        task: Task,
        boundary: str,
        event_type: str,
        payload: Mapping | None = None,
    ) -> None:
        self.trace_recorder.record(
            task_id=task.task_id,
            trace_id=task.trace_id,
            boundary=boundary,
            event_type=event_type,
            payload=payload or {},
        )

    def _publish_terminal(
        self,
        task: Task,
        *,
        memory_result: MemoryWriteResult | None = None,
    ) -> None:
        if task.state not in TERMINAL_TASK_STATES:
            return
        self.event_publisher.publish_terminal(
            task,
            memory_status=(
                None
                if memory_result is None
                else getattr(memory_result, "action", None)
            ),
        )

    def _timing_dict(self, creation: TaskCreationResult) -> dict:
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
