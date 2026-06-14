from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from providers.base import ProviderResult
from sessions.decision import CALL_TOOL, COMPLETE, REPLAN, WAIT, ExecutionDecision
from sessions.session_manager import TaskSessionManager
from sessions.strategy import StrategyDecision
from sessions.subagent import SubAgent
from skill import SkillDefinition, SkillManager
from tools import ToolManager
from tools.base import ToolDefinition, ToolResult


FIXED_TIME = datetime(2026, 6, 13, 18, 0, tzinfo=timezone.utc)


def make_handoff() -> HandoffRequest:
    return HandoffRequest(
        task_goal="Give the user a short reminder before leaving.",
        trigger_event=StandardizedEvent(
            trace_id="trace-llm-tool-decision",
            source="cli_input",
            timestamp=FIXED_TIME,
            payload={"text": "Ella，我要出门了"},
            event_type="USER_UTTERANCE",
            metadata={"trigger_kind": "user_initiated"},
        ),
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Mock environment only.",
        context_summary="User is leaving.",
        constraints=("Keep it short.",),
        completion_criteria=("A reminder is ready.",),
    )


def make_skill_manager() -> SkillManager:
    manager = SkillManager()
    manager.register(
        SkillDefinition(
            name="going_out",
            description="Prepare a concise reminder before leaving.",
            when_to_use="Use when the user is heading out.",
            path=Path("skill/skills/going_out/SKILL.md"),
        )
    )
    return manager


def make_creation():
    return TaskSessionManager(
        allowed_tools=("schema_tool", "other_tool", "mock_vision_summary"),
        session_id_factory=lambda: "session-llm-tool-decision",
        task_id_factory=lambda: "task-llm-tool-decision",
    ).create_session(make_handoff())


def make_strategy() -> StrategyDecision:
    return StrategyDecision(
        mode="skill",
        skill_name="going_out",
        reason="Use going_out.",
        initial_plan=None,
        completion_criteria=("A reminder is ready.",),
        session_id="session-llm-tool-decision",
        task_id="task-llm-tool-decision",
        trace_id="trace-llm-tool-decision",
    )


def make_tool_directory() -> ToolManager:
    manager = ToolManager()
    manager.register(SchemaTool("schema_tool"))
    manager.register(SchemaTool("other_tool"))
    return manager


def make_subagent(response: object) -> SubAgent:
    return SubAgent(
        skill_manager=make_skill_manager(),
        tool_directory=make_tool_directory(),
        llm_provider=RecordingLLMProvider(response),
    )


def decide(subagent: SubAgent) -> ExecutionDecision:
    creation = make_creation()
    return subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(),
    )


def test_subagent_sends_visible_tool_definitions_to_llm() -> None:
    subagent = make_subagent(
        '{"action": "CALL_TOOL", "tool_name": "schema_tool", '
        '"arguments": {"location": "Tokyo"}, "reason": "Need context."}'
    )
    creation = make_creation()

    decision = subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(),
    )

    provider = subagent.llm_provider
    assert isinstance(provider, RecordingLLMProvider)
    assert "schema_tool" in provider.last_prompt
    assert "other_tool" in provider.last_prompt
    assert "Give the user a short reminder before leaving." in provider.last_prompt
    assert "tool_results" in provider.last_prompt
    assert decision.tool_name == "schema_tool"


def test_llm_internal_json_call_tool_becomes_execution_decision() -> None:
    decision = decide(
        make_subagent(
            {
                "action": "CALL_TOOL",
                "tool_name": "schema_tool",
                "arguments": {"location": "Tokyo"},
                "reason": "Need weather-like context.",
            }
        )
    )

    assert decision == ExecutionDecision(
        action=CALL_TOOL,
        tool_name="schema_tool",
        tool_input={"location": "Tokyo"},
        reason="Need weather-like context.",
        is_complete=False,
    )


def test_llm_internal_json_complete_becomes_execution_decision() -> None:
    decision = decide(
        make_subagent(
            '{"action": "COMPLETE", "reason": "All required facts are ready."}'
        )
    )

    assert decision.action == COMPLETE
    assert decision.tool_name is None
    assert decision.is_complete is True


def test_llm_wait_and_replan_actions_are_single_decisions() -> None:
    wait = decide(make_subagent({"action": "WAIT", "reason": "Need user input."}))
    replan = decide(make_subagent({"action": "REPLAN", "reason": "Need a new plan."}))

    assert wait.action == WAIT
    assert wait.tool_name is None
    assert replan.action == REPLAN
    assert replan.tool_name is None


def test_invalid_json_returns_replan_without_executing_tools() -> None:
    tool = SchemaTool("schema_tool")
    directory = ToolManager()
    directory.register(tool)
    subagent = SubAgent(
        skill_manager=make_skill_manager(),
        tool_directory=directory,
        llm_provider=RecordingLLMProvider("not json"),
    )

    decision = decide(subagent)

    assert decision.action == REPLAN
    assert "invalid" in decision.reason.lower()
    assert tool.calls == 0


def test_unknown_action_returns_replan() -> None:
    decision = decide(make_subagent({"action": "DANCE", "reason": "Nope."}))

    assert decision.action == REPLAN
    assert "unsupported" in decision.reason.lower()


def test_missing_tool_name_for_call_tool_returns_replan() -> None:
    decision = decide(
        make_subagent({"action": "CALL_TOOL", "arguments": {"location": "Tokyo"}})
    )

    assert decision.action == REPLAN
    assert "tool_name" in decision.reason


def test_unknown_tool_name_returns_replan_without_execution() -> None:
    decision = decide(
        make_subagent(
            {
                "action": "CALL_TOOL",
                "tool_name": "not_registered",
                "arguments": {},
            }
        )
    )

    assert decision.action == REPLAN
    assert "unknown tool" in decision.reason.lower()


def test_missing_required_parameters_returns_replan() -> None:
    decision = decide(
        make_subagent(
            {
                "action": "CALL_TOOL",
                "tool_name": "schema_tool",
                "arguments": {},
            }
        )
    )

    assert decision.action == REPLAN
    assert "missing required" in decision.reason.lower()


def test_mock_safe_fallback_remains_deterministic_without_llm() -> None:
    creation = TaskSessionManager(
        allowed_tools=("mock_vision_summary", "mock_weather", "mock_checklist"),
        session_id_factory=lambda: "session-fallback",
        task_id_factory=lambda: "task-fallback",
    ).create_session(make_handoff())
    subagent = SubAgent(skill_manager=make_skill_manager())
    strategy = subagent.select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )

    decision = subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        strategy,
    )

    assert decision.action == CALL_TOOL
    assert decision.tool_name == "mock_vision_summary"
    assert not hasattr(subagent, "tool_manager")


def test_existing_select_strategy_behavior_remains_compatible() -> None:
    creation = make_creation()
    subagent = SubAgent(skill_manager=make_skill_manager())

    strategy = subagent.select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )

    assert strategy.mode == "skill"
    assert strategy.skill_name == "going_out"


@dataclass(slots=True)
class RecordingLLMProvider:
    response: object
    provider_name: str = "recording_llm"
    model_name: str = "recording-tool-decision"
    last_prompt: str = ""

    def generate(self, prompt: str, *, trace_id=None, metadata=None):
        self.last_prompt = prompt
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=self.response,
            metadata=metadata or {},
        )


@dataclass(slots=True)
class SchemaTool:
    name: str
    allowed_roles: tuple[str, ...] = ("main_agent",)
    calls: int = 0

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Use for LLM tool decision tests. Do not use as a real "
                "capability."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
                "additionalProperties": False,
            },
            input_examples=({"location": "Tokyo"},),
            output_schema={
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
            },
        )

    def run(self, context) -> ToolResult:
        self.calls += 1
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            session_id=context.session_id,
            trace_id=context.trace_id,
            payload={"summary": "Should not be called by SubAgent."},
        )
