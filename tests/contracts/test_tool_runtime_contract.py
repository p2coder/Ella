import inspect
import json
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path

import demo.cli_demo as cli_demo
from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from devices.camera import MockCameraProvider
from events import StandardizedEvent
from providers.base import ProviderResult
from providers.llm import serialize_tool_definition
from providers.mock import MockLLMProvider, MockMultimodalProvider
from runtime.task_runtime import TaskRuntime
from sessions.decision import CALL_TOOL, REPLAN, WAIT, ExecutionDecision
from sessions.executor import CapabilityExecutor
from sessions.session_manager import TaskSessionManager
from sessions.strategy import StrategyDecision
from sessions.subagent import SubAgent
from skill import SkillDefinition, SkillManager
from tools.base import ToolDefinition, ToolResult
from tools.manager import ToolManager


FIXED_TIME = datetime(2026, 6, 14, 15, 0, tzinfo=timezone.utc)


@dataclass
class CountingTool:
    name: str
    allowed_roles: tuple[str, ...] = ("main_agent",)
    calls: int = 0

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=f"Use {self.name} for deterministic contract testing.",
            schema_version="1",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            input_examples=({},),
            output_schema={
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        )

    def run(self, context: AgentExecutionContext) -> ToolResult:
        self.calls += 1
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            session_id=context.session_id,
            trace_id=context.trace_id,
            payload={"summary": f"{self.name} completed"},
        )


class RecordingDecisionProvider:
    provider_name = "recording_decision"
    model_name = "recording-decision-v1"

    def __init__(self, output) -> None:
        self.output = output
        self.last_prompt = ""

    def generate(self, prompt: str, *, trace_id=None, metadata=None) -> ProviderResult:
        self.last_prompt = prompt
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=self.output,
            metadata={"mock": True},
        )


def make_handoff(text: str = "Ella，我要出门了") -> HandoffRequest:
    return HandoffRequest(
        task_goal="Give the user a short reminder before leaving.",
        trigger_event=StandardizedEvent(
            trace_id="trace-tool-contract",
            source="cli_input",
            timestamp=FIXED_TIME,
            payload={"text": text},
            event_type="USER_UTTERANCE",
            metadata={"trigger_kind": "user_initiated"},
        ),
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Mock environment.",
        context_summary="User is leaving.",
        constraints=("Keep it short.",),
        completion_criteria=("A reminder is ready.",),
    )


def make_skill_manager(
    *,
    required_tools: tuple[str, ...] = (),
    optional_tools: tuple[str, ...] = (),
) -> SkillManager:
    manager = SkillManager()
    manager.register(
        SkillDefinition(
            name="going_out",
            description="Prepare a reminder when the user is leaving.",
            when_to_use="Use when the user is heading out.",
            path=Path("skill/skills/going_out/SKILL.md"),
            required_tools=required_tools,
            optional_tools=optional_tools,
        )
    )
    return manager


def make_strategy(context: AgentExecutionContext) -> StrategyDecision:
    return StrategyDecision(
        mode="skill",
        skill_name="going_out",
        reason="Use skill guidance.",
        initial_plan=None,
        completion_criteria=("A reminder is ready.",),
        session_id=context.session_id,
        task_id=context.task_id,
        trace_id=context.trace_id,
    )


def create_context(
    manager: ToolManager,
    *,
    agent_role: str = "main_agent",
):
    return TaskSessionManager(
        agent_role=agent_role,
        skill_manager=make_skill_manager(),
        tool_manager=manager,
        session_id_factory=lambda: f"session-{agent_role}",
        task_id_factory=lambda: f"task-{agent_role}",
    ).create_session(make_handoff())


def test_demo_registers_tools_once_and_shares_one_process_manager(tmp_path: Path):
    runtime = cli_demo.DemoRuntime.create_default(tmp_path / "memory.md")
    executor_manager = runtime.task_runtime.executor.tool_manager

    assert runtime.task_runtime.session_manager.tool_manager is executor_manager
    assert runtime.task_runtime.subagent.tool_directory is executor_manager
    assert executor_manager.version == len(executor_manager.list_names())
    assert len(executor_manager.list_names()) == len(set(executor_manager.list_names()))
    assert runtime.task_runtime.session_manager.allowed_tools == (
        executor_manager.list_names_for_role("main_agent")
    )
    create_source = inspect.getsource(cli_demo.DemoRuntime.create_default)
    assert 'allowed_tools=("' not in create_source


def test_tool_manager_is_reused_across_multiple_task_submissions(tmp_path: Path):
    runtime = cli_demo.DemoRuntime.create_default(tmp_path / "memory.md")
    manager = runtime.task_runtime.executor.tool_manager
    initial_version = manager.version

    first = runtime.event_runtime.publish(
        cli_demo.CLITextSignalSource().create_signal("Ella，我要出门了", "trace-a")
    )
    second = runtime.event_runtime.publish(
        cli_demo.CLITextSignalSource().create_signal("Ella，我要出门了", "trace-b")
    )

    assert first.task_handle is not None
    assert second.task_handle is not None
    assert runtime.task_runtime.session_manager.tool_manager is manager
    assert runtime.task_runtime.executor.tool_manager is manager
    assert manager.version == initial_version


def test_executor_path_does_not_use_tool_manager_execute(monkeypatch):
    manager = ToolManager()
    tool = CountingTool("contract_tool")
    manager.register(tool)
    creation = create_context(manager)
    skill_manager = make_skill_manager(required_tools=("contract_tool",))
    subagent = SubAgent(skill_manager, tool_directory=manager)
    executor = CapabilityExecutor(
        subagent=subagent,
        skill_manager=skill_manager,
        tool_manager=manager,
    )

    def forbidden_execute(*args, **kwargs):
        raise AssertionError("ToolManager.execute must not be the executor path")

    monkeypatch.setattr(ToolManager, "execute", forbidden_execute)
    result = executor.execute(
        ExecutionDecision(CALL_TOOL, "contract_tool", {}, "Use it.", False),
        make_strategy(creation.context),
        creation.context,
        creation.session,
    )

    assert result.tool_result is not None
    assert tool.calls == 1


def test_tool_registry_is_the_only_tool_storage_source():
    manager = ToolManager()
    tool = CountingTool("stored_once")
    manager.register(tool)

    assert {field.name for field in fields(manager)} == {"registry", "version"}
    assert manager.registry.get("stored_once") is tool
    assert not hasattr(manager, "_tools")


def test_subagent_llm_receives_only_visible_tool_definition_snapshot():
    manager = ToolManager()
    visible = CountingTool("visible_tool")
    hidden = CountingTool("hidden_tool", allowed_roles=("specialist",))
    manager.register(visible)
    manager.register(hidden)
    creation = create_context(manager)
    provider = RecordingDecisionProvider(
        {"action": "COMPLETE", "reason": "No tool is needed."}
    )
    subagent = SubAgent(
        make_skill_manager(required_tools=("visible_tool",)),
        tool_directory=manager,
        llm_provider=provider,
    )

    subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation.context),
    )
    prompt = json.loads(provider.last_prompt)

    assert tuple(tool["name"] for tool in prompt["visible_tools"]) == (
        "visible_tool",
    )


def test_llm_tool_metadata_excludes_runtime_and_secret_fields():
    definition = ToolDefinition(
        name="safe_tool",
        description="Safe public tool metadata.",
        schema_version="1",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "api_key": {"type": "string"},
                "local_path": {"type": "string"},
                "raw_media": {"type": "string"},
                "permission_token": {"type": "string"},
                "class_name": {"type": "string"},
            },
        },
        input_examples=({"query": "hello"},),
        output_schema={"type": "object", "properties": {}},
    )

    rendered = repr(serialize_tool_definition(definition))

    for forbidden in (
        "api_key",
        "local_path",
        "raw_media",
        "permission_token",
        "class_name",
        "Authorization",
    ):
        assert forbidden not in rendered


def test_two_agent_roles_receive_different_tool_scopes():
    manager = ToolManager()
    manager.register(CountingTool("main_tool", allowed_roles=("main_agent",)))
    manager.register(CountingTool("specialist_tool", allowed_roles=("specialist",)))

    main = create_context(manager, agent_role="main_agent")
    specialist = create_context(manager, agent_role="specialist")

    assert main.context.allowed_tools == ("main_tool",)
    assert specialist.context.allowed_tools == ("specialist_tool",)


def test_tool_added_after_task_creation_does_not_enter_existing_scope():
    manager = ToolManager()
    manager.register(CountingTool("initial_tool"))
    first = create_context(manager)

    manager.register(CountingTool("later_tool"))
    second = TaskSessionManager(
        skill_manager=make_skill_manager(),
        tool_manager=manager,
        session_id_factory=lambda: "session-later",
        task_id_factory=lambda: "task-later",
    ).create_session(make_handoff())

    assert first.context.allowed_tools == ("initial_tool",)
    assert second.context.allowed_tools == ("initial_tool", "later_tool")


def test_removed_tool_is_unavailable_before_execution_and_replans():
    manager = ToolManager()
    manager.register(CountingTool("removable_tool"))
    creation = create_context(manager)
    skill_manager = make_skill_manager(required_tools=("removable_tool",))
    subagent = SubAgent(skill_manager, tool_directory=manager)
    manager.unregister("removable_tool")

    decision = subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation.context),
    )

    assert decision.action == REPLAN


def test_invalid_llm_action_never_executes_a_tool():
    manager = ToolManager()
    tool = CountingTool("safe_tool")
    manager.register(tool)
    creation = create_context(manager)
    subagent = SubAgent(
        make_skill_manager(required_tools=("safe_tool",)),
        tool_directory=manager,
        llm_provider=RecordingDecisionProvider({"action": "DANCE"}),
    )

    decision = subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation.context),
    )

    assert decision.action == REPLAN
    assert tool.calls == 0


class ReplanningSubAgent:
    def __init__(self, skill_manager: SkillManager) -> None:
        self.skill_manager = skill_manager

    def select_strategy(self, handoff, context, session):
        return make_strategy(context)

    def decide_next_action(self, handoff, context, session, strategy):
        return ExecutionDecision(REPLAN, None, None, "Try again.", False)


def test_replan_loop_is_bounded_by_task_runtime_max_steps(tmp_path: Path):
    manager = ToolManager()
    skill_manager = make_skill_manager()
    subagent = ReplanningSubAgent(skill_manager)
    runtime = TaskRuntime(
        session_manager=TaskSessionManager(
            skill_manager=skill_manager,
            tool_manager=manager,
            session_id_factory=lambda: "session-replan-limit",
            task_id_factory=lambda: "task-replan-limit",
        ),
        subagent=subagent,
        executor=CapabilityExecutor(
            skill_manager=skill_manager,
            tool_manager=manager,
        ),
    )
    handle = runtime.submit(make_handoff())

    result = runtime.run_until_blocked(handle.task_id, max_steps=5)

    assert result.stop_reason == "max_steps"
    assert result.blocked is True
    assert result.steps == 5


def test_skill_required_tools_cannot_bypass_executor_permission_validation():
    manager = ToolManager()
    tool = CountingTool("denied_tool")
    manager.register(tool)
    skill_manager = make_skill_manager(required_tools=("denied_tool",))
    creation = TaskSessionManager(
        allowed_tools=(),
        session_id_factory=lambda: "session-denied",
        task_id_factory=lambda: "task-denied",
    ).create_session(make_handoff())
    executor = CapabilityExecutor(
        skill_manager=skill_manager,
        tool_manager=manager,
    )

    result = executor.execute(
        ExecutionDecision(CALL_TOOL, "denied_tool", {}, "Try denied.", False),
        make_strategy(creation.context),
        creation.context,
        creation.session,
    )

    assert result.replan_required is True
    assert tool.calls == 0


def test_demo_is_deterministic_with_mock_factories(monkeypatch, tmp_path: Path):
    class MockProviderFactory:
        def llm(self):
            return MockLLMProvider()

        def multimodal(self):
            return MockMultimodalProvider()

    class MockDeviceFactory:
        def camera(self):
            return MockCameraProvider()

    class Settings:
        debug_store_raw_media = False

    monkeypatch.setattr(cli_demo, "ProviderFactory", MockProviderFactory)
    monkeypatch.setattr(cli_demo, "DeviceFactory", MockDeviceFactory)
    monkeypatch.setattr(cli_demo, "load_settings", lambda: Settings())

    first = cli_demo.DemoRuntime.create_default(tmp_path / "first.md").run(
        "Ella，我要出门了"
    )
    second = cli_demo.DemoRuntime.create_default(tmp_path / "second.md").run(
        "Ella，我要出门了"
    )

    assert "[Ella Process]" in first
    assert "[Final Answer]" in first
    assert "mock_vision_summary" in first
    assert first.replace("first.md", "memory.md") == second.replace(
        "second.md", "memory.md"
    )
