from dataclasses import dataclass
from datetime import datetime, timezone

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from runtime.task_runtime import TaskRuntime
from sessions.completion import TaskCompletionPackage
from sessions.decision import COMPLETE, ExecutionDecision
from sessions.executor import CapabilityExecutionResult
from sessions.output import UserVisibleAgentOutput
from sessions.session import TaskState
from sessions.session_manager import TaskSessionManager
from sessions.strategy import StrategyDecision
from tools import ToolResult


def make_handoff() -> HandoffRequest:
    return HandoffRequest(
        task_goal="Give the user a short reminder before leaving.",
        trigger_event=StandardizedEvent(
            trace_id="trace-runtime-completion",
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
        session_id="session-runtime-completion",
        task_id="task-runtime-completion",
        trace_id="trace-runtime-completion",
    )


def complete_decision() -> ExecutionDecision:
    return ExecutionDecision(
        action=COMPLETE,
        tool_name=None,
        tool_input=None,
        reason="The required going-out context has been collected.",
        is_complete=True,
    )


@dataclass
class CompletionSkillManager:
    def refresh(self):
        return ()


@dataclass
class CompletionToolManager:
    def list_names(self):
        return ()


@dataclass
class CompletionSubAgent:
    skill_manager: CompletionSkillManager

    def select_strategy(self, handoff, context, task_session):
        return make_strategy()

    def decide_next_action(self, handoff, context, task_session, strategy):
        return complete_decision()


@dataclass
class CompletionExecutor:
    tool_manager: CompletionToolManager

    def execute(self, decision, strategy, context, task_session):
        return CapabilityExecutionResult(
            decision=decision,
            strategy=strategy,
            tool_result=None,
            replan_required=False,
        )


def make_runtime():
    runtime = TaskRuntime(
        session_manager=TaskSessionManager(
            allowed_tools=("mock_weather",),
            session_id_factory=lambda: "session-runtime-completion",
            task_id_factory=lambda: "task-runtime-completion",
        ),
        subagent=CompletionSubAgent(CompletionSkillManager()),
        executor=CompletionExecutor(CompletionToolManager()),
    )
    handle = runtime.submit(make_handoff())
    session = runtime.get_session(handle.task_id)
    session.tool_trace = (
        ToolResult(
            tool_name="mock_weather",
            task_id=handle.task_id,
            session_id=handle.session_id,
            trace_id=handle.trace_id,
            payload={"summary": "Light rain is possible."},
        ).to_dict(),
    )
    return runtime, handle


def advance_to_running(runtime: TaskRuntime, task_id: str) -> None:
    runtime.step(task_id)
    runtime.step(task_id)


def test_complete_decision_creates_visible_output_and_completion_package():
    runtime, handle = make_runtime()
    advance_to_running(runtime, handle.task_id)

    result = runtime.step(handle.task_id)

    assert isinstance(result.completion, TaskCompletionPackage)
    assert isinstance(result.completion.user_visible_output, UserVisibleAgentOutput)
    assert result.completion.user_visible_output.final_response
    assert result.session.completion is result.completion


def test_completion_uses_same_context_and_includes_session_tool_results():
    runtime, handle = make_runtime()
    context = runtime.get_context(handle.task_id)
    advance_to_running(runtime, handle.task_id)

    result = runtime.step(handle.task_id)

    assert result.completion is not None
    assert result.completion.context is context
    assert len(result.completion.tool_results) == 1
    assert result.completion.tool_results[0].tool_name == "mock_weather"
    assert result.completion.tool_results[0].payload == {
        "summary": "Light rain is possible."
    }


def test_complete_decision_transitions_session_to_completed():
    runtime, handle = make_runtime()
    advance_to_running(runtime, handle.task_id)

    result = runtime.step(handle.task_id)

    assert result.session.state is TaskState.SUCCEEDED
    assert result.stop_reason == "completed"
    assert result.blocked is False


def test_completion_does_not_call_or_own_memory_manager(tmp_path):
    runtime, handle = make_runtime()
    advance_to_running(runtime, handle.task_id)

    runtime.step(handle.task_id)

    assert list(tmp_path.iterdir()) == []
    assert not hasattr(runtime, "memory_manager")
