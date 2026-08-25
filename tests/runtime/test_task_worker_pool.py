from datetime import datetime, timezone
from threading import Barrier, Event
from time import monotonic, sleep

from agent.decision import COMPLETE, ExecutionDecision
from agent.handoff import HandoffRequest
from events import StandardizedEvent
from memory import MemoryManager
from runtime.executor import CapabilityExecutionResult
from runtime.task_queue import TaskQueue
from runtime.task_runtime import TaskRuntime
from tasks.factory import TaskFactory
from tasks.state import TaskControlCommand, TaskControlType
from tasks.task import TaskState


class _NoToolManager:
    def get_tool(self, name):
        return None


class _CompleteExecutor:
    tool_manager = _NoToolManager()

    def execute(self, decision, context, task):
        return CapabilityExecutionResult(decision)


def _handoff(trace_id: str) -> HandoffRequest:
    return HandoffRequest(
        "Reply",
        StandardizedEvent(
            trace_id=trace_id,
            source="test",
            payload={"text": "hello"},
            event_type="USER_UTTERANCE",
        ),
        "",
        "",
        "",
        (),
        ("reply produced",),
    )


def _wait_for(predicate, timeout=2.0):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return
        sleep(0.01)
    raise AssertionError("condition was not reached")


def test_fixed_task_workers_execute_two_tasks_concurrently(tmp_path) -> None:
    barrier = Barrier(2)

    class ConcurrentSubAgent:
        def decide_next_action(self, handoff, context, task):
            barrier.wait(timeout=1)
            return ExecutionDecision(
                COMPLETE,
                None,
                None,
                "No capability is required.",
                f"completed {task.task_id}",
                (),
            )

    ids = iter(("task-a", "task-b"))
    runtime = TaskRuntime(
        task_factory=TaskFactory(task_id_factory=lambda: next(ids)),
        subagent=ConcurrentSubAgent(),
        executor=_CompleteExecutor(),
        memory_manager=MemoryManager(tmp_path / "memory.md"),
        task_queue=TaskQueue(),
        max_task_workers=2,
    )
    runtime.start()
    try:
        first = runtime.submit(_handoff("trace-a"))
        second = runtime.submit(_handoff("trace-b"))
        _wait_for(
            lambda: runtime.get_task(first.task_id).state is TaskState.SUCCEEDED
            and runtime.get_task(second.task_id).state is TaskState.SUCCEEDED
        )
        assert {first.task_id, second.task_id} <= set(runtime._worker_results)
    finally:
        runtime.stop()
        assert runtime.join(2)


def test_paused_task_keeps_its_worker_until_resumed(tmp_path) -> None:
    reasoning_started = Event()
    allow_reasoning_to_finish = Event()

    class PausableSubAgent:
        def decide_next_action(self, handoff, context, task):
            if task.task_id == "task-paused":
                reasoning_started.set()
                allow_reasoning_to_finish.wait(1)
            return ExecutionDecision(
                COMPLETE,
                None,
                None,
                "No capability is required.",
                "done",
                (),
            )

    ids = iter(("task-paused", "task-queued"))
    queue = TaskQueue()
    runtime = TaskRuntime(
        task_factory=TaskFactory(task_id_factory=lambda: next(ids)),
        subagent=PausableSubAgent(),
        executor=_CompleteExecutor(),
        memory_manager=MemoryManager(tmp_path / "memory.md"),
        task_queue=queue,
        max_task_workers=1,
    )
    runtime.start()
    try:
        first = runtime.submit(_handoff("trace-paused"))
        assert reasoning_started.wait(1)
        paused = runtime.apply_control(
            TaskControlCommand(
                "pause-1",
                first.task_id,
                TaskControlType.PAUSE,
                datetime.now(timezone.utc),
                "test",
            )
        )
        assert paused.accepted
        allow_reasoning_to_finish.set()
        _wait_for(lambda: runtime.get_task(first.task_id).state is TaskState.PAUSED)
        second = runtime.submit(_handoff("trace-queued"))
        _wait_for(lambda: second.task_id in queue.snapshot())
        assert first.task_id in runtime._owned_tasks
        assert runtime.get_task(second.task_id).state is TaskState.READY

        resumed = runtime.apply_control(
            TaskControlCommand(
                "resume-1",
                first.task_id,
                TaskControlType.RESUME,
                datetime.now(timezone.utc),
                "test",
            )
        )
        assert resumed.accepted
        assert resumed.current_state == TaskState.REASONING.value
        _wait_for(
            lambda: runtime.get_task(first.task_id).state is TaskState.SUCCEEDED
            and runtime.get_task(second.task_id).state is TaskState.SUCCEEDED
        )
    finally:
        runtime.stop()
        assert runtime.join(2)
