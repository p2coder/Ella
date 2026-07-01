from dataclasses import dataclass
from datetime import datetime, timezone

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from runtime.task_runtime import TaskRuntime
from sessions.decision import CALL_TOOL, COMPLETE, ExecutionDecision
from sessions.execution_state import ToolFailureKind, ToolFailureObservation
from sessions.executor import CapabilityExecutionResult
from sessions.session import TaskState
from sessions.session_manager import TaskSessionManager
from sessions.strategy import StrategyDecision
from tools.base import ToolResult


def make_handoff():
    return HandoffRequest(
        task_goal="Run a test tool.",
        trigger_event=StandardizedEvent(
            trace_id="trace-retry",
            source="test",
            timestamp=datetime(2026, 7, 2, tzinfo=timezone.utc),
            payload={"text": "run it"},
            event_type="USER_UTTERANCE",
        ),
        user_preference_summary="",
        environment_summary="",
        context_summary="",
        constraints=(),
        completion_criteria=("Done.",),
    )


def strategy():
    return StrategyDecision("react", None, "test", None, ("Done.",))


def call(tool_name="schema_tool", arguments=None):
    return ExecutionDecision(
        CALL_TOOL,
        tool_name,
        arguments if arguments is not None else {"value": "bad"},
        "test",
        False,
    )


@dataclass
class SequenceSubAgent:
    decisions: list[ExecutionDecision]

    def decide_next_action(self, *args):
        return self.decisions.pop(0)

    def select_strategy(self, *args):
        return strategy()


@dataclass
class SequenceExecutor:
    results: list[CapabilityExecutionResult]
    calls: list[ExecutionDecision]

    def execute(self, decision, strategy, context, task_session):
        self.calls.append(decision)
        return self.results.pop(0)


def failure_result(decision, kind=ToolFailureKind.INVALID_ARGUMENTS):
    failure = ToolFailureObservation(
        attempt_id="step1_try",
        tool_name=decision.tool_name or "schema_tool",
        kind=kind,
        code=kind.value,
        message="arguments are invalid",
        arguments=decision.tool_input or {},
        retryable=kind is ToolFailureKind.INVALID_ARGUMENTS,
    )
    return CapabilityExecutionResult(
        decision,
        strategy(),
        None,
        True,
        failure_reason=failure.message,
        failure=failure,
    )


def success_result(decision):
    result = ToolResult(
        decision.tool_name or "schema_tool",
        "task-retry",
        "session-retry",
        "trace-retry",
        {"status": "available", "summary": "done"},
    )
    return CapabilityExecutionResult(decision, strategy(), result, False)


def make_runtime(decisions, results, max_argument_retries=2):
    subagent = SequenceSubAgent(list(decisions))
    executor = SequenceExecutor(list(results), [])
    runtime = TaskRuntime(
        session_manager=TaskSessionManager(
            session_id_factory=lambda: "session-retry",
            task_id_factory=lambda: "task-retry",
        ),
        subagent=subagent,
        executor=executor,
        max_argument_retries=max_argument_retries,
    )
    handle = runtime.submit(make_handoff())
    session = runtime.get_session(handle.task_id)
    session.state = TaskState.RUNNING
    session.current_strategy = strategy()
    return runtime, handle, session, executor


def test_invalid_arguments_advance_retry_attempts_then_next_step():
    decisions = [call(), call(), call()]
    results = [failure_result(item) for item in decisions]
    runtime, handle, session, _ = make_runtime(decisions, results)

    runtime.step(handle.task_id)
    assert session.current_step.attempt_id == "step1_retry1"
    assert session.current_step.active_tool_name == "schema_tool"

    runtime.step(handle.task_id)
    assert session.current_step.attempt_id == "step1_retry2"

    runtime.step(handle.task_id)
    assert session.current_step.attempt_id == "step2_try"
    assert session.step_history[0].blacklisted_tools == ("schema_tool",)
    assert session.step_history[0].failures[-1].code == "parameter_generation_failed"


def test_repair_switch_is_violation_and_never_reaches_executor():
    first = call("schema_tool")
    switched = call("other_tool", {})
    runtime, handle, session, executor = make_runtime(
        [first, switched],
        [failure_result(first)],
    )

    runtime.step(handle.task_id)
    runtime.step(handle.task_id)

    assert executor.calls == [first]
    assert session.current_step.attempt_id == "step1_retry2"
    assert session.current_step.active_tool_name == "schema_tool"
    assert (
        session.current_step.failures[-1].kind
        is ToolFailureKind.INVALID_ARGUMENTS_REPAIR_VIOLATION
    )


def test_non_retryable_failure_advances_step_without_tool_trace():
    decision = call("camera_scene")
    runtime, handle, session, _ = make_runtime(
        [decision],
        [failure_result(decision, ToolFailureKind.PERMISSION_DENIED)],
    )

    runtime.step(handle.task_id)

    assert session.current_step.attempt_id == "step2_try"
    assert session.tool_trace == ()
    assert session.step_history[0].blacklisted_tools == ("camera_scene",)


def test_success_records_result_and_advances_step():
    decision = call()
    runtime, handle, session, _ = make_runtime(
        [decision],
        [success_result(decision)],
    )

    result = runtime.step(handle.task_id)

    assert session.current_step.attempt_id == "step2_try"
    assert len(session.tool_trace) == 1
    assert result.logical_steps == 1


def test_complete_archives_current_step_without_executing_tool():
    complete = ExecutionDecision(COMPLETE, None, None, "done", True)
    runtime, handle, session, executor = make_runtime(
        [complete],
        [CapabilityExecutionResult(complete, strategy(), None, False)],
    )

    runtime.step(handle.task_id)

    assert session.state is TaskState.COMPLETED
    assert len(session.step_history) == 1
    assert executor.calls == [complete]
