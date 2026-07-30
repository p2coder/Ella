from datetime import datetime, timezone

from agent.context import AgentExecutionContext, CapabilityScope
from events import StandardizedEvent
from memory.manager import MemoryManagementRequest, MemoryManager
from runtime.event_router import SessionAwareEventRouter
from runtime.timing import RuntimeTimingRecorder
from sessions.completion import TaskCompletionPackage
from sessions.output import UserVisibleAgentOutput
from sessions.strategy import StrategyDecision
from tools.base import ToolResult


def context() -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-identity",
        trace_id="trace-identity",
        handoff_goal="respond",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ()),
        session_id="old-session",
    )


def test_context_and_tool_serialization_emit_task_identity_only():
    ctx = context()
    result = ToolResult(
        "tool",
        "task-identity",
        "trace-identity",
        {"value": 1},
        session_id="old-session",
    )

    assert ctx.session_id == "task-identity"
    assert "session_id" not in ctx.to_dict()
    assert result.session_id == "task-identity"
    assert "session_id" not in result.to_dict()


def test_strategy_legacy_session_is_normalized_to_task_id():
    strategy = StrategyDecision(
        "react", None, "reason", None, ("done",), session_id="old-task"
    )

    assert strategy.task_id == "old-task"
    assert strategy.session_id == strategy.task_id
    assert "session_id" not in strategy.__slots__


def test_timing_snapshot_and_memory_record_do_not_emit_session_id(tmp_path):
    recorder = RuntimeTimingRecorder()
    recorder.record_task_submitted("trace-identity", task_id="task-identity")
    snapshot = recorder.snapshot("trace-identity")
    tool_result = ToolResult(
        "tool", "task-identity", "trace-identity", {"value": 1}
    )
    completion = TaskCompletionPackage(
        context=context(),
        summary="done",
        user_visible_output=UserVisibleAgentOutput({}, "done"),
        tool_results=(tool_result,),
    )
    manager = MemoryManager(tmp_path / "memory.md")
    manager.handle(MemoryManagementRequest.from_completion(completion))

    assert snapshot is not None
    assert "session_id" not in snapshot.to_dict()
    assert "session_id" not in manager.memory_path.read_text(encoding="utf-8")


def test_router_targets_tasks_not_sessions():
    event = StandardizedEvent(
        trace_id="trace-route",
        source="test",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        payload={},
        event_type="TASK_EVENT",
        metadata={},
        caused_by_task_id="task-identity",
    )
    route = SessionAwareEventRouter(
        active_task_ids={"task-identity"}
    ).route(event)

    assert route.target_task_id == "task-identity"
    assert "session_id" not in route.__slots__
