from datetime import datetime, timezone
from pathlib import Path

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from events import StandardizedEvent
from providers.base import ProviderResult
from sessions.decision import CALL_TOOL, COMPLETE, REPLAN
from sessions.session_manager import TaskSessionManager
from sessions.subagent import SubAgent
from sessions.strategy import StrategyDecision
from skill import SkillDefinition, SkillManager
from tools.base import ToolDefinition


FIXED_TIME = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


class DefinitionDirectory:
    def __init__(self, definitions: tuple[ToolDefinition, ...]) -> None:
        self.definitions = definitions
        self.list_calls = 0

    def list_definitions(self, context: AgentExecutionContext):
        self.list_calls += 1
        return tuple(
            definition
            for definition in self.definitions
            if definition.name in context.allowed_tools
        )


class RecordingProvider:
    provider_name = "recording_llm"
    model_name = "recording"

    def __init__(self, output) -> None:
        self.output = output

    def generate(self, prompt: str, *, trace_id=None, metadata=None) -> ProviderResult:
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=self.output,
            metadata={},
        )


def make_tool_definition(
    name: str,
    description: str | None = None,
    *,
    required: tuple[str, ...] = (),
) -> ToolDefinition:
    properties = {
        field: {"type": "string"}
        for field in required
    }
    return ToolDefinition(
        name=name,
        description=description or f"Use {name} when the task needs it.",
        schema_version="1",
        input_schema={
            "type": "object",
            "properties": properties,
            "required": list(required),
        },
        input_examples=({field: f"{field}-value" for field in required},)
        if required
        else ({},),
        output_schema={"type": "object", "properties": {"summary": {"type": "string"}}},
    )


def make_handoff(*, text: str = "Ella，我要出门了") -> HandoffRequest:
    return HandoffRequest(
        task_goal="Give the user a short, necessary reminder before leaving.",
        trigger_event=StandardizedEvent(
            trace_id="trace-dynamic-tools",
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
        completion_criteria=("Reminder is ready.",),
    )


def make_creation(*, text: str = "Ella，我要出门了", allowed_tools: tuple[str, ...]):
    handoff = make_handoff(text=text)
    return TaskSessionManager(
        allowed_tools=allowed_tools,
        session_id_factory=lambda: "session-dynamic-tools",
        task_id_factory=lambda: "task-dynamic-tools",
    ).create_session(handoff)


def make_strategy(creation) -> StrategyDecision:
    return StrategyDecision(
        mode="skill",
        skill_name="going_out",
        reason="Use skill guidance.",
        initial_plan=None,
        completion_criteria=creation.session.handoff.completion_criteria,
        session_id=creation.context.session_id,
        task_id=creation.context.task_id,
        trace_id=creation.context.trace_id,
    )


def make_skill_manager(skill: SkillDefinition) -> SkillManager:
    manager = SkillManager()
    manager.register(skill)
    return manager


def make_skill(
    *,
    required_tools: tuple[str, ...] = ("mock_weather", "mock_checklist"),
    optional_tools: tuple[str, ...] = ("camera_scene",),
) -> SkillDefinition:
    return SkillDefinition(
        name="going_out",
        description="Prepare a reminder when the user is leaving.",
        when_to_use="Use when the user is heading out.",
        path=Path("skill/skills/going_out/SKILL.md"),
        required_tools=required_tools,
        optional_tools=optional_tools,
    )


def test_subagent_no_longer_depends_on_hardcoded_sequence_constants() -> None:
    source = Path("sessions/subagent.py").read_text(encoding="utf-8")

    assert "GOING_OUT_TOOL_SEQUENCE" not in source
    assert "GOING_OUT_VISUAL_TOOL_SEQUENCE" not in source


def test_subagent_chooses_next_action_from_skill_guidance_and_visible_definitions() -> None:
    creation = make_creation(allowed_tools=("alpha_tool", "beta_tool"))
    directory = DefinitionDirectory(
        (
            make_tool_definition("alpha_tool"),
            make_tool_definition("beta_tool"),
        )
    )
    subagent = SubAgent(
        skill_manager=make_skill_manager(
            make_skill(required_tools=("alpha_tool", "beta_tool"), optional_tools=())
        ),
        tool_directory=directory,
    )

    decision = subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )

    assert decision.action == CALL_TOOL
    assert decision.tool_name == "alpha_tool"
    assert directory.list_calls == 1


def test_going_out_can_call_relevant_tools_through_dynamic_decision() -> None:
    creation = make_creation(
        text="Ella，看看当前画面，我要出门了",
        allowed_tools=("camera_scene", "mock_weather", "mock_checklist"),
    )
    directory = DefinitionDirectory(
        (
            make_tool_definition(
                "camera_scene",
                "Use this visual context tool when the user asks Ella to inspect the current view.",
            ),
            make_tool_definition("mock_weather"),
            make_tool_definition("mock_checklist"),
        )
    )
    subagent = SubAgent(
        skill_manager=make_skill_manager(make_skill()),
        tool_directory=directory,
    )

    decision = subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )

    assert decision.action == CALL_TOOL
    assert decision.tool_name == "camera_scene"


def test_non_going_out_tasks_are_not_forced_into_going_out_behavior() -> None:
    creation = make_creation(allowed_tools=("mock_weather",))
    subagent = SubAgent(skill_manager=make_skill_manager(make_skill()))
    strategy = StrategyDecision(
        mode="plan_to_execute",
        skill_name=None,
        reason="No skill.",
        initial_plan=("Clarify.",),
        completion_criteria=creation.session.handoff.completion_criteria,
        session_id=creation.context.session_id,
        task_id=creation.context.task_id,
        trace_id=creation.context.trace_id,
    )

    decision = subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        strategy,
    )

    assert decision.action == COMPLETE
    assert decision.tool_name is None


def test_invalid_llm_output_does_not_execute_tools() -> None:
    creation = make_creation(allowed_tools=("mock_weather",))
    directory = DefinitionDirectory((make_tool_definition("mock_weather"),))
    subagent = SubAgent(
        skill_manager=make_skill_manager(make_skill(required_tools=("mock_weather",))),
        tool_directory=directory,
        llm_provider=RecordingProvider("not json"),
    )

    decision = subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )

    assert decision.action == REPLAN
    assert creation.session.tool_trace == ()


def test_unknown_tool_decision_does_not_execute_tools() -> None:
    creation = make_creation(allowed_tools=("mock_weather",))
    directory = DefinitionDirectory((make_tool_definition("mock_weather"),))
    subagent = SubAgent(
        skill_manager=make_skill_manager(make_skill(required_tools=("mock_weather",))),
        tool_directory=directory,
        llm_provider=RecordingProvider(
            {"action": "CALL_TOOL", "tool_name": "missing_tool", "arguments": {}}
        ),
    )

    decision = subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )

    assert decision.action == REPLAN
    assert creation.session.tool_trace == ()


def test_deterministic_fallback_works_in_mock_safe_mode() -> None:
    creation = make_creation(allowed_tools=("mock_weather", "mock_checklist"))
    subagent = SubAgent(
        skill_manager=make_skill_manager(
            make_skill(required_tools=("mock_weather", "mock_checklist"), optional_tools=())
        )
    )

    first = subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )
    creation.session.tool_trace = ({"tool_name": "mock_weather", "payload": {}},)
    second = subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )

    assert first.tool_name == "mock_weather"
    assert second.tool_name == "mock_checklist"


def test_subagent_returns_one_decision_and_completes_after_guided_tools() -> None:
    creation = make_creation(allowed_tools=("mock_weather",))
    creation.session.tool_trace = ({"tool_name": "mock_weather", "payload": {}},)
    subagent = SubAgent(
        skill_manager=make_skill_manager(
            make_skill(required_tools=("mock_weather",), optional_tools=())
        )
    )

    decision = subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )

    assert decision.action == COMPLETE
    assert decision.tool_name is None


def test_subagent_does_not_mutate_task_session_state() -> None:
    creation = make_creation(allowed_tools=("mock_weather",))
    subagent = SubAgent(
        skill_manager=make_skill_manager(
            make_skill(required_tools=("mock_weather",), optional_tools=())
        )
    )
    before = (
        creation.session.state,
        creation.session.tool_trace,
        creation.session.current_strategy,
        creation.session.completion,
        creation.session.failure_reason,
    )

    subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )

    after = (
        creation.session.state,
        creation.session.tool_trace,
        creation.session.current_strategy,
        creation.session.completion,
        creation.session.failure_reason,
    )
    assert after == before
