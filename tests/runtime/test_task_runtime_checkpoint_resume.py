from dataclasses import dataclass
from time import monotonic, sleep

from agent.decision import COMPLETE, ExecutionDecision
from agent.handoff import HandoffRequest
from events import StandardizedEvent
from memory import MemoryManager
from runtime.executor import CapabilityExecutionResult
from runtime.task_queue import TaskQueue
from runtime.task_runtime import TaskRuntime
from runtime.task_store import TaskStore
from runtime.trace import TraceRecorder
from tasks.factory import TaskFactory
from tasks.graph import TaskGraphDefinition, TaskGraphNodeDefinition, TaskGraphNodeType, TaskGraphRun
from tasks.task import TaskState


def _handoff() -> HandoffRequest:
    return HandoffRequest(
        "Reply after recovery",
        StandardizedEvent(
            trace_id="trace-resume",
            source="test",
            payload={"text": "continue after restart"},
            event_type="USER_UTTERANCE",
        ),
        "",
        "",
        "",
        (),
        ("A reply is ready.",),
    )


@dataclass
class _CountingSubAgent:
    calls: int = 0

    def decide_next_action(self, handoff, context, task, **kwargs):
        self.calls += 1
        return ExecutionDecision(
            COMPLETE,
            None,
            None,
            "No capability is required.",
            "Recovered response.",
            (),
        )


class _NoToolManager:
    def get_tool(self, name):
        return None


class _Executor:
    tool_manager = _NoToolManager()

    def execute(self, decision, context, task):
        return CapabilityExecutionResult(decision)


def _runtime(tmp_path, subagent) -> TaskRuntime:
    return TaskRuntime(
        task_factory=TaskFactory(task_id_factory=lambda: "task-resume"),
        subagent=subagent,
        executor=_Executor(),
        memory_manager=MemoryManager(tmp_path / "memory.md"),
        task_store=TaskStore(tmp_path / "tasks"),
        task_queue=TaskQueue(),
        trace_recorder=TraceRecorder.for_directory(tmp_path / "trace"),
    )


def _wait_for_state(runtime, task_id, state, timeout=2.0):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if runtime.get_task(task_id).state is state:
            return
        sleep(0.01)
    raise AssertionError(f"task did not reach {state.value}")


def test_post_reasoning_checkpoint_resumes_saved_decision_without_llm(tmp_path):
    first = _runtime(tmp_path, _CountingSubAgent())
    handle = first.submit(_handoff())
    task = first.get_task(handle.task_id)
    task.transition_to(TaskState.REASONING)
    saved = ExecutionDecision(
        COMPLETE,
        None,
        None,
        "Reasoning finished before interruption.",
        "Use the checkpointed conclusion.",
        (),
    )
    task.task_local_state["current_decision"] = saved.to_dict()
    first._persist(task)

    subagent = _CountingSubAgent()
    restored = _runtime(tmp_path, subagent)
    restored.start()
    try:
        _wait_for_state(restored, handle.task_id, TaskState.SUCCEEDED)
        assert subagent.calls == 0
        assert restored.result_for(handle.task_id).completion is not None
    finally:
        restored.stop()
        assert restored.join(2)

    trace = TraceRecorder.for_directory(tmp_path / "trace").snapshot(handle.task_id)
    assert trace is not None
    boundaries = {(event.boundary, event.event_type) for event in trace.events}
    assert ("recovery", "checkpoint_loaded") in boundaries
    assert ("reasoning.execution_decision", "restored") in boundaries
    assert ("reasoning.final_response", "completed") in boundaries
    assert ("checkpoint", "persisted") in boundaries
    assert ("delivery", "terminal_published") in boundaries


def test_pre_reasoning_checkpoint_repeats_reasoning_once(tmp_path):
    first = _runtime(tmp_path, _CountingSubAgent())
    handle = first.submit(_handoff())
    task = first.get_task(handle.task_id)
    task.transition_to(TaskState.REASONING)
    first._persist(task)

    subagent = _CountingSubAgent()
    restored = _runtime(tmp_path, subagent)
    restored.start()
    try:
        _wait_for_state(restored, handle.task_id, TaskState.SUCCEEDED)
        assert subagent.calls == 1
    finally:
        restored.stop()
        assert restored.join(2)


def test_unsafe_dispatched_capability_restores_as_uncertain(tmp_path):
    first = _runtime(tmp_path, _CountingSubAgent())
    handle = first.submit(_handoff())
    task = first.get_task(handle.task_id)
    task.transition_to(TaskState.REASONING)
    task.transition_to(TaskState.TOOL_EXECUTION)
    task.task_local_state["in_flight_action"] = {
        "attempt_id": "step1_try",
        "tool_name": "external_write",
        "arguments": {"value": 1},
        "safe_to_retry": False,
    }
    first._persist(task)

    restored = _runtime(tmp_path, _CountingSubAgent())
    restored.start()
    try:
        _wait_for_state(restored, handle.task_id, TaskState.UNCERTAIN)
        assert restored.get_task(handle.task_id).failure["code"] == (
            "uncertain_in_flight_action"
        )
    finally:
        restored.stop()
        assert restored.join(2)


def test_task_graph_and_node_runs_survive_checkpoint(tmp_path):
    runtime = _runtime(tmp_path, _CountingSubAgent())
    handle = runtime.submit(_handoff())
    task = runtime.get_task(handle.task_id)
    definition = TaskGraphDefinition(
        "graph",
        "version-1",
        (TaskGraphNodeDefinition("step", TaskGraphNodeType.STEP, {"goal": "Do"}),),
        (),
        ("step",),
        ("step",),
    )
    task.graph = TaskGraphRun(definition, {"step": {"state": "ready"}})
    runtime._persist(task)

    stored = TaskStore(tmp_path / "tasks").load(handle.task_id)

    assert stored is not None
    assert stored.task.graph.definition.version == "version-1"
    assert stored.task.graph.node_runs["step"]["state"] == "ready"
