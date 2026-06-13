from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from runtime.task_runtime import TaskRuntime
from sessions.decision import CALL_TOOL, COMPLETE, WAIT, ExecutionDecision
from sessions.executor import CapabilityExecutionResult
from sessions.session import TaskState
from sessions.session_manager import TaskSessionManager
from sessions.strategy import StrategyDecision
from tools import ToolResult


def make_handoff() -> HandoffRequest:
    return HandoffRequest(
        task_goal="Give the user a short reminder before leaving.",
        trigger_event=StandardizedEvent(
            trace_id="trace-runtime-step",
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
        session_id="session-runtime-step",
        task_id="task-runtime-step",
        trace_id="trace-runtime-step",
    )


def make_decision(
    action: str = CALL_TOOL,
    tool_name: str | None = "mock_checklist",
) -> ExecutionDecision:
    return ExecutionDecision(
        action=action,
        tool_name=tool_name,
        tool_input=None,
        reason="Take one deterministic step.",
        is_complete=action == COMPLETE,
    )


@dataclass
class RecordingSkillManager:
    refresh_count: int = 0

    def refresh(self):
        self.refresh_count += 1
        return ()


@dataclass
class RecordingToolManager:
    read_count: int = 0

    def list_names(self):
        self.read_count += 1
        return ()


@dataclass
class RecordingSubAgent:
    decision: ExecutionDecision
    skill_manager: RecordingSkillManager
    select_count: int = 0
    decide_count: int = 0

    def select_strategy(self, handoff, context, task_session):
        self.select_count += 1
        return make_strategy()

    def decide_next_action(self, handoff, context, task_session, strategy):
        self.decide_count += 1
        return self.decision


@dataclass
class RecordingExecutor:
    result: CapabilityExecutionResult
    tool_manager: RecordingToolManager
    execute_count: int = 0

    def execute(self, decision, strategy, context, task_session):
        self.execute_count += 1
        return self.result


def make_runtime(
    decision: ExecutionDecision | None = None,
    *,
    replan_required: bool = False,
    tool_result: ToolResult | None = None,
):
    decision = decision or make_decision()
    strategy = make_strategy()
    skill_manager = RecordingSkillManager()
    tool_manager = RecordingToolManager()
    subagent = RecordingSubAgent(decision, skill_manager)
    executor = RecordingExecutor(
        CapabilityExecutionResult(
            decision=decision,
            strategy=strategy,
            tool_result=tool_result,
            replan_required=replan_required,
        ),
        tool_manager,
    )
    runtime = TaskRuntime(
        session_manager=TaskSessionManager(
            allowed_tools=("mock_checklist",),
            session_id_factory=lambda: "session-runtime-step",
            task_id_factory=lambda: "task-runtime-step",
        ),
        subagent=subagent,
        executor=executor,
    )
    handle = runtime.submit(make_handoff())
    return runtime, handle, subagent, executor


def advance_to_running(runtime: TaskRuntime, task_id: str) -> None:
    runtime.step(task_id)
    runtime.step(task_id)


def test_created_step_only_transitions_to_planning():
    runtime, handle, subagent, executor = make_runtime()

    result = runtime.step(handle.task_id)

    assert result.session.state is TaskState.PLANNING
    assert subagent.select_count == 0
    assert subagent.decide_count == 0
    assert executor.execute_count == 0


def test_planning_step_selects_strategy_and_moves_to_running():
    runtime, handle, subagent, executor = make_runtime()
    runtime.step(handle.task_id)

    result = runtime.step(handle.task_id)

    assert result.session.state is TaskState.RUNNING
    assert result.session.current_strategy == make_strategy()
    assert subagent.select_count == 1
    assert subagent.decide_count == 0
    assert executor.execute_count == 0


def test_running_step_executes_exactly_one_decision_and_appends_tool_result():
    tool_result = ToolResult(
        tool_name="mock_checklist",
        task_id="task-runtime-step",
        session_id="session-runtime-step",
        trace_id="trace-runtime-step",
        payload={"items": ("phone", "keys")},
    )
    runtime, handle, subagent, executor = make_runtime(tool_result=tool_result)
    advance_to_running(runtime, handle.task_id)

    result = runtime.step(handle.task_id)

    assert result.session.state is TaskState.RUNNING
    assert subagent.decide_count == 1
    assert executor.execute_count == 1
    assert result.session.tool_trace == (tool_result.to_dict(),)


def test_executor_replan_required_moves_task_to_replanning():
    runtime, handle, subagent, executor = make_runtime(replan_required=True)
    advance_to_running(runtime, handle.task_id)

    result = runtime.step(handle.task_id)

    assert result.session.state is TaskState.REPLANNING
    assert subagent.decide_count == 1
    assert executor.execute_count == 1


def test_replanning_refreshes_capabilities_and_selects_new_strategy():
    runtime, handle, subagent, executor = make_runtime(replan_required=True)
    advance_to_running(runtime, handle.task_id)
    runtime.step(handle.task_id)

    result = runtime.step(handle.task_id)

    assert result.session.state is TaskState.RUNNING
    assert subagent.skill_manager.refresh_count == 1
    assert executor.tool_manager.read_count == 1
    assert subagent.select_count == 2


def test_wait_decision_moves_task_to_waiting_without_tool_result():
    runtime, handle, subagent, executor = make_runtime(
        make_decision(action=WAIT, tool_name=None)
    )
    advance_to_running(runtime, handle.task_id)

    result = runtime.step(handle.task_id)

    assert result.session.state is TaskState.WAITING
    assert result.session.tool_trace == ()
    assert executor.execute_count == 1


def test_complete_decision_only_records_completion_readiness():
    decision = make_decision(action=COMPLETE, tool_name=None)
    runtime, handle, subagent, executor = make_runtime(decision)
    advance_to_running(runtime, handle.task_id)

    result = runtime.step(handle.task_id)

    assert result.session.state is TaskState.RUNNING
    assert result.session.task_local_state["completion_ready"] is True
    assert result.session.task_local_state["completion_decision"] == decision
    assert result.session.completion is None


@pytest.mark.parametrize(
    "terminal_state",
    (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED),
)
def test_terminal_states_reject_step(terminal_state: TaskState):
    runtime, handle, subagent, executor = make_runtime()
    session = runtime.get_session(handle.task_id)
    session.state = terminal_state

    with pytest.raises(ValueError, match=f"cannot step terminal task: {terminal_state.value}"):
        runtime.step(handle.task_id)
