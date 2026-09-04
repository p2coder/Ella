from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from time import sleep

from agent.context import AgentExecutionContext, CapabilityScope
from agent.decision import CALL_TOOL, ExecutionDecision
from runtime.executor import CapabilityExecutor
from skill import SkillManager
from tasks.task import Task
from tools import RefreshTool, ToolManager
from tools.base import ToolDefinition, ToolResult


class RecordingTool:
    name = "recording"
    allowed_roles = ("main_agent",)

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description="Record calls.",
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            input_examples=({"value": "one"},),
            output_schema={"type": "object"},
            result_ttl_seconds=60,
        )

    def run(self, context, arguments=None) -> ToolResult:
        values = dict(arguments or {})
        self.calls.append(values)
        return ToolResult(self.name, context.task_id, values)


class BlockingRecordingTool(RecordingTool):
    def __init__(self) -> None:
        super().__init__()
        self._lock = Lock()

    def run(self, context, arguments=None) -> ToolResult:
        with self._lock:
            result = super().run(context, arguments)
        sleep(0.02)
        return result


def _context(*, agent_id: str = "agent-main") -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id=agent_id,
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-refresh",
        memory_scope="task_local",
        capability_scope=CapabilityScope(
            agent_role="main_agent",
            allowed_skills=(),
            allowed_tools=("recording", "refresh"),
        ),
    )


def _decision(tool_name: str, arguments: dict[str, object]) -> ExecutionDecision:
    return ExecutionDecision(CALL_TOOL, tool_name, arguments, "Test refresh.")


def test_refresh_replays_exact_arguments_and_records_source() -> None:
    manager = ToolManager()
    recording = RecordingTool()
    manager.register(recording)
    manager.register(RefreshTool())
    ids = iter(("tool-use-original", "tool-use-refreshed"))
    times = iter(
        datetime(2026, 9, 4, 1, minute, tzinfo=timezone.utc)
        for minute in range(4)
    )
    executor = CapabilityExecutor(
        SkillManager(),
        manager,
        tool_use_id_factory=lambda: next(ids),
        clock=lambda: next(times),
    )
    task = Task("task-refresh")

    original = executor.execute(
        _decision("recording", {"value": "original"}), _context(), task
    )
    refreshed = executor.execute(
        _decision("refresh", {"tool_use_id": "tool-use-original"}),
        _context(),
        task,
    )

    assert original.tool_result is not None
    assert refreshed.tool_result is not None
    assert recording.calls == [{"value": "original"}, {"value": "original"}]
    assert refreshed.decision.tool_name == "refresh"
    assert refreshed.tool_result.tool_name == "recording"
    assert refreshed.tool_result.tool_use_id == "tool-use-refreshed"
    assert refreshed.tool_result.refresh_of_tool_use_id == "tool-use-original"
    assert refreshed.tool_result.result_ttl_seconds == 60


def test_refresh_rejects_unknown_or_other_agent_source() -> None:
    manager = ToolManager()
    manager.register(RecordingTool())
    manager.register(RefreshTool())
    executor = CapabilityExecutor(SkillManager(), manager)
    task = Task("task-refresh")

    missing = executor.execute(
        _decision("refresh", {"tool_use_id": "missing"}), _context(), task
    )
    original = executor.execute(
        _decision("recording", {"value": "private"}), _context(), task
    )
    hidden = executor.execute(
        _decision("refresh", {"tool_use_id": original.tool_result.tool_use_id}),
        _context(agent_id="other-agent"),
        task,
    )

    assert missing.failure is not None
    assert missing.failure.code == "refresh_source_not_found"
    assert hidden.failure is not None
    assert hidden.failure.code == "refresh_source_not_visible"


def test_refresh_revalidates_current_tool_schema_and_permissions() -> None:
    manager = ToolManager()
    manager.register(RecordingTool())
    manager.register(RefreshTool())
    executor = CapabilityExecutor(SkillManager(), manager)
    task = Task("task-refresh")
    original = executor.execute(
        _decision("recording", {"value": "old"}), _context(), task
    )

    restricted = AgentExecutionContext(
        agent_id="agent-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-refresh",
        memory_scope="task_local",
        capability_scope=CapabilityScope(
            agent_role="main_agent",
            allowed_skills=(),
            allowed_tools=("refresh",),
        ),
    )
    result = executor.execute(
        _decision("refresh", {"tool_use_id": original.tool_result.tool_use_id}),
        restricted,
        task,
    )

    assert result.failure is not None
    assert result.failure.code == "tool_not_allowed"
    assert result.failure.refresh_of_tool_use_id == original.tool_result.tool_use_id


def test_concurrent_refreshes_share_one_replay() -> None:
    manager = ToolManager()
    recording = BlockingRecordingTool()
    manager.register(recording)
    manager.register(RefreshTool())
    executor = CapabilityExecutor(SkillManager(), manager)
    task = Task("task-refresh")
    original = executor.execute(
        _decision("recording", {"value": "once"}), _context(), task
    )
    source_id = original.tool_result.tool_use_id
    barrier = Barrier(3)

    def refresh_once():
        barrier.wait()
        return executor.execute(
            _decision("refresh", {"tool_use_id": source_id}), _context(), task
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(refresh_once)
        second = pool.submit(refresh_once)
        barrier.wait()
        results = (first.result(), second.result())

    assert len(recording.calls) == 2
    assert all(item.tool_result is not None for item in results)
    assert results[0].tool_result.tool_use_id == results[1].tool_result.tool_use_id
    assert all(
        item.tool_result.refresh_of_tool_use_id == source_id for item in results
    )
