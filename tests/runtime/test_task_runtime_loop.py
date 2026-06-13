from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from runtime.task_runtime import TaskRuntime
from sessions.decision import COMPLETE, WAIT, ExecutionDecision
from sessions.executor import CapabilityExecutionResult
from sessions.session import TaskState
from sessions.session_manager import TaskSessionManager
from sessions.strategy import StrategyDecision


def make_handoff() -> HandoffRequest:
    return HandoffRequest(
        task_goal="Give the user a short reminder before leaving.",
        trigger_event=StandardizedEvent(
            trace_id="trace-runtime-loop",
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
        session_id="session-runtime-loop",
        task_id="task-runtime-loop",
        trace_id="trace-runtime-loop",
    )


def make_decision(action: str) -> ExecutionDecision:
    return ExecutionDecision(
        action=action,
        tool_name=None,
        tool_input=None,
        reason="Stop at the requested lifecycle boundary.",
        is_complete=action == COMPLETE,
    )


@dataclass
class LoopSkillManager:
    def refresh(self):
        return ()


@dataclass
class LoopToolManager:
    def list_names(self):
        return ()


@dataclass
class LoopSubAgent:
    decision: ExecutionDecision
    skill_manager: LoopSkillManager
    select_count: int = 0
    decide_count: int = 0

    def select_strategy(self, handoff, context, task_session):
        self.select_count += 1
        return make_strategy()

    def decide_next_action(self, handoff, context, task_session, strategy):
        self.decide_count += 1
        return self.decision


@dataclass
class LoopExecutor:
    decision: ExecutionDecision
    tool_manager: LoopToolManager
    execute_count: int = 0

    def execute(self, decision, strategy, context, task_session):
        self.execute_count += 1
        return CapabilityExecutionResult(
            decision=decision,
            strategy=strategy,
            tool_result=None,
            replan_required=False,
        )


def make_runtime(action: str = WAIT):
    decision = make_decision(action)
    subagent = LoopSubAgent(decision, LoopSkillManager())
    executor = LoopExecutor(decision, LoopToolManager())
    runtime = TaskRuntime(
        session_manager=TaskSessionManager(
            session_id_factory=lambda: "session-runtime-loop",
            task_id_factory=lambda: "task-runtime-loop",
        ),
        subagent=subagent,
        executor=executor,
    )
    handle = runtime.submit(make_handoff())
    return runtime, handle, subagent, executor


def test_run_until_blocked_repeatedly_calls_step_until_waiting():
    runtime, handle, subagent, executor = make_runtime(WAIT)

    result = runtime.run_until_blocked(handle.task_id, max_steps=10)

    assert result.session.state is TaskState.WAITING
    assert result.steps == 3
    assert result.stop_reason == "waiting"
    assert result.blocked is True
    assert subagent.select_count == 1
    assert subagent.decide_count == 1
    assert executor.execute_count == 1


@pytest.mark.parametrize(
    ("terminal_state", "stop_reason"),
    (
        (TaskState.COMPLETED, "completed"),
        (TaskState.FAILED, "failed"),
        (TaskState.CANCELLED, "cancelled"),
    ),
)
def test_run_until_blocked_stops_on_existing_terminal_state(
    terminal_state: TaskState,
    stop_reason: str,
):
    runtime, handle, subagent, executor = make_runtime()
    runtime.get_session(handle.task_id).state = terminal_state

    result = runtime.run_until_blocked(handle.task_id, max_steps=10)

    assert result.steps == 0
    assert result.stop_reason == stop_reason
    assert result.blocked is False
    assert subagent.select_count == 0
    assert executor.execute_count == 0


def test_run_until_blocked_stops_when_no_executable_action_remains():
    runtime, handle, subagent, executor = make_runtime(COMPLETE)

    result = runtime.run_until_blocked(handle.task_id, max_steps=10)

    assert result.session.state is TaskState.RUNNING
    assert result.session.task_local_state["completion_ready"] is True
    assert result.steps == 3
    assert result.stop_reason == "no_executable_action"
    assert result.blocked is True


def test_run_until_blocked_stops_at_max_steps_without_looping_forever():
    runtime, handle, subagent, executor = make_runtime(WAIT)

    result = runtime.run_until_blocked(handle.task_id, max_steps=2)

    assert result.session.state is TaskState.RUNNING
    assert result.steps == 2
    assert result.stop_reason == "max_steps"
    assert result.blocked is True
    assert subagent.decide_count == 0
    assert executor.execute_count == 0


def test_run_until_blocked_rejects_negative_max_steps():
    runtime, handle, subagent, executor = make_runtime()

    with pytest.raises(ValueError, match="max_steps must be non-negative"):
        runtime.run_until_blocked(handle.task_id, max_steps=-1)


def test_run_loop_has_no_memory_side_effect(tmp_path):
    runtime, handle, subagent, executor = make_runtime(WAIT)

    runtime.run_until_blocked(handle.task_id, max_steps=10)

    assert list(tmp_path.iterdir()) == []
    assert not hasattr(runtime, "memory_manager")
