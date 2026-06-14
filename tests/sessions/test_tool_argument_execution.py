from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from devices.microphone import DeviceResult
from events import StandardizedEvent
from providers.base import ProviderResult
from sessions.decision import CALL_TOOL, ExecutionDecision
from sessions.executor import CapabilityExecutor
from sessions.session import TaskSession
from sessions.strategy import StrategyDecision
from skill import SkillDefinition, SkillManager
from tools.base import ToolDefinition, ToolResult
from tools.camera_scene import CameraSceneTool
from tools.manager import ToolManager
from tools.mock_tools import MockChecklistTool


def make_handoff() -> HandoffRequest:
    return HandoffRequest(
        task_goal="Inspect one tool invocation.",
        trigger_event=StandardizedEvent(
            trace_id="trace-arguments",
            source="test",
            timestamp=datetime(2026, 6, 14, tzinfo=timezone.utc),
            payload={"text": "Run the selected tool."},
            event_type="USER_UTTERANCE",
            metadata={"trigger_kind": "user_initiated"},
        ),
        user_preference_summary="",
        environment_summary="",
        context_summary="",
        constraints=(),
        completion_criteria=("One action is executed.",),
    )


def make_context(tool_name: str) -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        session_id="session-arguments",
        task_id="task-arguments",
        trace_id="trace-arguments",
        handoff_goal="Inspect one tool invocation.",
        memory_scope="task_local",
        allowed_tools=(tool_name,),
    )


def make_session() -> TaskSession:
    return TaskSession(
        session_id="session-arguments",
        task_id="task-arguments",
        handoff=make_handoff(),
    )


def make_strategy() -> StrategyDecision:
    return StrategyDecision(
        mode="skill",
        skill_name="argument_test",
        reason="Test one argument-aware action.",
        initial_plan=None,
        completion_criteria=("One action is executed.",),
    )


def make_executor(tool: Any) -> CapabilityExecutor:
    tool_manager = ToolManager()
    tool_manager.register(tool)
    skill_manager = SkillManager()
    skill_manager.register(
        SkillDefinition(
            name="argument_test",
            description="Exercise one argument-aware tool.",
            when_to_use="Use in executor argument tests.",
            path=Path("skill/skills/argument_test/SKILL.md"),
        )
    )
    return CapabilityExecutor(
        skill_manager=skill_manager,
        tool_manager=tool_manager,
    )


def execute(tool: Any, arguments: dict[str, object]) -> tuple[Any, TaskSession]:
    session = make_session()
    result = make_executor(tool).execute(
        decision=ExecutionDecision(
            action=CALL_TOOL,
            tool_name=tool.name,
            tool_input=arguments,
            reason="Call one tool.",
            is_complete=False,
        ),
        strategy=make_strategy(),
        context=make_context(tool.name),
        task_session=session,
    )
    return result, session


def test_validated_arguments_reach_tool_and_affect_result() -> None:
    tool = ArgumentRecordingTool()

    result, _ = execute(tool, {"message": "hello"})

    assert tool.received_arguments == [{"message": "hello"}]
    assert result.tool_result is not None
    assert result.tool_result.payload == {"echo": "HELLO"}


def test_input_free_tool_accepts_empty_arguments() -> None:
    result, _ = execute(MockChecklistTool(), {})

    assert result.replan_required is False
    assert result.tool_result is not None


def test_tool_manager_compatibility_execute_forwards_arguments() -> None:
    tool = ArgumentRecordingTool()
    manager = ToolManager()
    manager.register(tool)

    result = manager.execute(
        tool.name,
        make_context(tool.name),
        {"message": "manager"},
    )

    assert tool.received_arguments == [{"message": "manager"}]
    assert result.payload == {"echo": "MANAGER"}


def test_unknown_argument_is_rejected_without_calling_tool() -> None:
    tool = ArgumentRecordingTool()

    result, _ = execute(tool, {"message": "hello", "unknown": True})

    assert result.replan_required is True
    assert result.failure_reason == "invalid_tool_input: arguments has unsupported property unknown"
    assert tool.received_arguments == []


def test_missing_required_argument_is_rejected_without_calling_tool() -> None:
    tool = ArgumentRecordingTool()

    result, _ = execute(tool, {})

    assert result.replan_required is True
    assert result.failure_reason == "invalid_tool_input: arguments.message is required"
    assert tool.received_arguments == []


def test_camera_scene_uses_requested_bounded_frame_count() -> None:
    camera = CountingCamera()
    tool = CameraSceneTool(
        camera_provider=camera,
        multimodal_provider=SceneProvider(),
        max_frames=3,
        max_duration_seconds=3,
    )

    result, _ = execute(
        tool,
        {"max_frames": 1, "max_duration_seconds": 2},
    )

    assert result.replan_required is False
    assert camera.capture_count == 1
    assert result.tool_result is not None
    assert result.tool_result.payload["frames_captured"] == 1


def test_camera_scene_rejects_runtime_limits_above_configured_safety_bounds() -> None:
    camera = CountingCamera()
    tool = CameraSceneTool(
        camera_provider=camera,
        multimodal_provider=SceneProvider(),
        max_frames=2,
        max_duration_seconds=3,
    )

    result, _ = execute(
        tool,
        {"max_frames": 3, "max_duration_seconds": 4},
    )

    assert result.replan_required is True
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("invalid_tool_input:")
    assert camera.capture_count == 0


def test_executor_executes_one_action_without_mutating_session() -> None:
    tool = ArgumentRecordingTool()
    session = make_session()
    before = (
        session.state,
        dict(session.task_local_state),
        session.message_history,
        session.tool_trace,
        session.current_strategy,
        session.completion,
        session.failure_reason,
    )
    executor = make_executor(tool)

    result = executor.execute(
        ExecutionDecision(
            CALL_TOOL,
            tool.name,
            {"message": "once"},
            "Call one tool.",
            False,
        ),
        make_strategy(),
        make_context(tool.name),
        session,
    )

    after = (
        session.state,
        dict(session.task_local_state),
        session.message_history,
        session.tool_trace,
        session.current_strategy,
        session.completion,
        session.failure_reason,
    )
    assert result.tool_result is not None
    assert tool.received_arguments == [{"message": "once"}]
    assert after == before


@dataclass(slots=True)
class ArgumentRecordingTool:
    name: str = "argument_recording"
    allowed_roles: tuple[str, ...] = ("main_agent",)
    received_arguments: list[dict[str, object]] = field(default_factory=list)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description="Echo one required message for argument execution tests.",
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
                "additionalProperties": False,
            },
            input_examples=({"message": "hello"},),
            output_schema={
                "type": "object",
                "properties": {"echo": {"type": "string"}},
                "required": ["echo"],
                "additionalProperties": False,
            },
        )

    def run(
        self,
        *,
        context: AgentExecutionContext,
        arguments: dict[str, object],
    ) -> ToolResult:
        self.received_arguments.append(dict(arguments))
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            session_id=context.session_id,
            trace_id=context.trace_id,
            payload={"echo": str(arguments["message"]).upper()},
        )


class CountingCamera:
    device_name = "counting_camera"

    def __init__(self) -> None:
        self.capture_count = 0

    def capture_frame(self, *, trace_id=None, metadata=None) -> DeviceResult:
        self.capture_count += 1
        return DeviceResult(
            device_name=self.device_name,
            trace_id=trace_id,
            output={"type": "image", "frame": self.capture_count},
        )


class SceneProvider:
    provider_name = "scene_provider"

    def describe(self, inputs, *, trace_id=None, metadata=None) -> ProviderResult:
        return ProviderResult(
            provider_name=self.provider_name,
            model_name="scene-v1",
            trace_id=trace_id,
            output={
                "scene_summary": "A bounded test scene.",
                "visible_items": (),
            },
        )
