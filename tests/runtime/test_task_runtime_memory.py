from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from memory import MemoryManagementRequest, MemoryWriteResult
from runtime.task_runtime import TaskRuntime
from sessions.decision import COMPLETE, ExecutionDecision
from sessions.executor import CapabilityExecutionResult
from sessions.session import TaskState
from sessions.session_manager import TaskSessionManager
from sessions.strategy import StrategyDecision


def make_handoff() -> HandoffRequest:
    return HandoffRequest(
        task_goal="Give the user a short reminder before leaving.",
        trigger_event=StandardizedEvent(
            trace_id="trace-runtime-memory",
            source="cli_input",
            timestamp=datetime(2026, 6, 13, 14, 0, tzinfo=timezone.utc),
            payload={"text": "Ella，我要出门了"},
            event_type="USER_UTTERANCE",
            metadata={"trigger_kind": "user_initiated"},
        ),
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Mock environment only.",
        context_summary="User is preparing to leave.",
        constraints=("Keep the reminder short.",),
        completion_criteria=("A reminder is ready.",),
    )


def make_strategy() -> StrategyDecision:
    return StrategyDecision(
        mode="skill",
        skill_name="going_out",
        reason="Use the going-out capability.",
        initial_plan=None,
        completion_criteria=("A reminder is ready.",),
        session_id="session-runtime-memory",
        task_id="task-runtime-memory",
        trace_id="trace-runtime-memory",
    )


def complete_decision() -> ExecutionDecision:
    return ExecutionDecision(
        action=COMPLETE,
        tool_name=None,
        tool_input=None,
        reason="The task goal and completion criteria are satisfied.",
        is_complete=True,
    )


@dataclass
class RuntimeSkillManager:
    def refresh(self):
        return ()


@dataclass
class RuntimeToolManager:
    def list_names(self):
        return ()


@dataclass
class CompletingSubAgent:
    skill_manager: RuntimeSkillManager

    def select_strategy(self, handoff, context, task_session):
        return make_strategy()

    def decide_next_action(self, handoff, context, task_session, strategy):
        return complete_decision()


@dataclass
class CompletingExecutor:
    tool_manager: RuntimeToolManager

    def execute(self, decision, strategy, context, task_session):
        return CapabilityExecutionResult(
            decision=decision,
            strategy=strategy,
            tool_result=None,
            replan_required=False,
        )


@dataclass
class RecordingMemoryManager:
    memory_path: Path
    requests: tuple[MemoryManagementRequest, ...] = ()

    def handle(self, request: MemoryManagementRequest) -> MemoryWriteResult:
        self.requests += (request,)
        return MemoryWriteResult(action="recorded", memory_path=self.memory_path)


@dataclass
class FailingMemoryManager:
    calls: int = 0

    def handle(self, request: MemoryManagementRequest) -> MemoryWriteResult:
        self.calls += 1
        raise OSError("memory storage unavailable")


def make_runtime(memory_manager):
    runtime = TaskRuntime(
        session_manager=TaskSessionManager(
            session_id_factory=lambda: "session-runtime-memory",
            task_id_factory=lambda: "task-runtime-memory",
        ),
        subagent=CompletingSubAgent(RuntimeSkillManager()),
        executor=CompletingExecutor(RuntimeToolManager()),
        memory_manager=memory_manager,
    )
    return runtime, runtime.submit(make_handoff())


def test_completed_task_is_submitted_to_memory_manager(tmp_path: Path):
    memory_manager = RecordingMemoryManager(tmp_path / "memory.md")
    runtime, handle = make_runtime(memory_manager)

    result = runtime.run_until_complete(handle.task_id, max_steps=10)

    assert result.session.state is TaskState.COMPLETED
    assert result.completion is not None
    assert result.memory_result == MemoryWriteResult(
        action="recorded",
        memory_path=tmp_path / "memory.md",
    )
    assert len(memory_manager.requests) == 1
    assert memory_manager.requests[0].completion is result.completion


def test_run_until_complete_uses_state_machine_and_reaches_completion(tmp_path: Path):
    memory_manager = RecordingMemoryManager(tmp_path / "memory.md")
    runtime, handle = make_runtime(memory_manager)

    result = runtime.run_until_complete(handle.task_id, max_steps=10)

    assert result.steps == 3
    assert result.stop_reason == "completed"
    assert result.blocked is False
    assert runtime.get_session(handle.task_id).current_strategy == make_strategy()


def test_memory_manager_is_the_only_memory_write_entry_point(tmp_path: Path):
    memory_manager = RecordingMemoryManager(tmp_path / "memory.md")
    runtime, handle = make_runtime(memory_manager)

    result = runtime.run_until_complete(handle.task_id, max_steps=10)

    assert len(memory_manager.requests) == 1
    assert result.completion is not None
    assert not hasattr(result.completion, "write_memory")
    assert not hasattr(result.session, "write_memory")
    assert not (tmp_path / "memory.md").exists()


def test_successful_memory_result_is_saved_without_duplicate_write(tmp_path: Path):
    memory_manager = RecordingMemoryManager(tmp_path / "memory.md")
    runtime, handle = make_runtime(memory_manager)

    first = runtime.run_until_complete(handle.task_id, max_steps=10)
    second = runtime.run_until_complete(handle.task_id, max_steps=10)

    assert second.memory_result is first.memory_result
    assert len(memory_manager.requests) == 1


def test_memory_failure_preserves_completion_and_returns_reason():
    memory_manager = FailingMemoryManager()
    runtime, handle = make_runtime(memory_manager)

    result = runtime.run_until_complete(handle.task_id, max_steps=10)

    assert result.session.state is TaskState.COMPLETED
    assert result.completion is result.session.completion
    assert result.completion is not None
    assert result.completion.user_visible_output.final_response
    assert result.memory_result is None
    assert result.stop_reason == "memory_failed"
    assert result.blocked is True
    assert result.failure_reason == "memory write failed: memory storage unavailable"
    assert memory_manager.calls == 1


def test_max_steps_does_not_bypass_state_machine_or_write_memory(tmp_path: Path):
    memory_manager = RecordingMemoryManager(tmp_path / "memory.md")
    runtime, handle = make_runtime(memory_manager)

    result = runtime.run_until_complete(handle.task_id, max_steps=2)

    assert result.session.state is TaskState.RUNNING
    assert result.stop_reason == "max_steps"
    assert result.completion is None
    assert result.memory_result is None
    assert memory_manager.requests == ()
