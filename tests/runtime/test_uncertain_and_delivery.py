from datetime import datetime, timezone

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from events import StandardizedEvent
from runtime.task_runtime import TaskRuntime
from sessions.decision import CALL_TOOL, ExecutionDecision
from sessions.executor import CapabilityExecutor
from sessions.session import Task, TaskState
from sessions.session_manager import TaskCreationResult
from sessions.strategy import StrategyDecision
from skill import SkillManager
from tools.base import (
    ToolDefinition,
    ToolIdempotency,
    ToolUncertainPolicy,
)
from tools.manager import ToolManager


def _handoff() -> HandoffRequest:
    event = StandardizedEvent(
        "trace", "test", datetime.now(timezone.utc), {"text": "do it"}, "USER_UTTERANCE", {}
    )
    return HandoffRequest("perform external action", event, "", "", "", (), ())


def _context() -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="agent", agent_role="main_agent", parent_agent_id=None,
        task_id="task", trace_id="trace", handoff_goal="perform external action",
        memory_scope="task_local", allowed_tools=("side_effect",), permissions=(),
    )


class UncertainTool:
    name = "side_effect"
    allowed_roles = ("main_agent",)
    definition = ToolDefinition(
        name=name,
        description="Changes external state.",
        schema_version="1",
        input_schema={"type": "object", "additionalProperties": False},
        input_examples=({},),
        output_schema={"type": "object"},
        idempotency=ToolIdempotency.NON_IDEMPOTENT,
        side_effecting=True,
        uncertain_policy=ToolUncertainPolicy.POSSIBLE_AFTER_DISPATCH,
    )

    def run(self, *, context, arguments):
        raise TimeoutError("result acknowledgement was lost")


def test_executor_classifies_unconfirmed_side_effect_as_uncertain():
    manager = ToolManager()
    manager.register(UncertainTool())
    executor = CapabilityExecutor(SkillManager(), manager)
    task = Task("task", "task", _handoff())
    result = executor.execute(
        ExecutionDecision(CALL_TOOL, "side_effect", {}, "execute", False),
        StrategyDecision("react", None, "", None, (), task_id="task", trace_id="trace"),
        _context(),
        task,
    )
    assert result.uncertain is True
    assert result.tool_result is None
    assert result.failure.code == "uncertain_tool_outcome"


def _runtime_with_task(state: TaskState) -> tuple[TaskRuntime, Task]:
    task = Task("task", "task", _handoff(), state=state, execution_context=_context())
    runtime = TaskRuntime()
    runtime._tasks[task.task_id] = TaskCreationResult(task)
    return runtime, task


def test_uncertain_resolution_only_records_failure_and_preserves_unknown_detail():
    runtime, task = _runtime_with_task(TaskState.UNCERTAIN)
    task.task_local_state["uncertain_attempt"] = {
        "tool_name": "side_effect",
        "arguments": {"value": 1},
        "possible_side_effects": ("external record may exist",),
    }
    runtime.resolve_uncertain_as_failed("task", "The external result is unknown.")
    assert task.state is TaskState.FAILED
    assert task.uncertain_resolution.tool_name == "side_effect"
    assert task.failure["external_outcome_unknown"] is True


def test_delivery_retry_reuses_exact_payload_without_running_task():
    runtime, task = _runtime_with_task(TaskState.FAILED)
    task.failure_reason = "camera permission denied"
    seen = []

    def fail_once(payload):
        seen.append(payload)
        raise OSError("delivery offline")

    assert runtime.deliver("task", fail_once) is False
    assert task.state is TaskState.FAILED
    first_payload = task.delivery.payload
    assert runtime.deliver("task", seen.append) is True
    assert task.state is TaskState.DELIVERED
    assert seen[0] is first_payload
    assert seen[1] is first_payload
    assert len(task.delivery.attempts) == 2
