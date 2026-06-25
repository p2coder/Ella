from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from providers.base import ProviderResult
from sessions.decision import CALL_TOOL, COMPLETE, REPLAN
from sessions.session_manager import TaskSessionManager
from sessions.strategy import StrategyDecision
from sessions.subagent import SubAgent
from skill.manager import SkillManager
from skill.registry import SkillDefinition
from tools.base import ToolDefinition


def make_handoff(text: str = "Ella，帮我找一下今天的笔记。") -> HandoffRequest:
    return HandoffRequest(
        task_goal="Help the user with the current request.",
        trigger_event=StandardizedEvent(
            trace_id="trace-workspace-decision",
            source="test",
            timestamp=datetime(2026, 6, 25, tzinfo=timezone.utc),
            payload={"text": text},
            event_type="USER_UTTERANCE",
            metadata={"trigger_kind": "user_initiated"},
        ),
        user_preference_summary="Prefers direct answers.",
        environment_summary="No special environment.",
        context_summary="The user asked for help.",
        constraints=("Be concise.",),
        completion_criteria=("The request is answered.",),
    )


def make_creation(handoff: HandoffRequest | None = None):
    return TaskSessionManager(
        allowed_tools=("note_lookup",),
        session_id_factory=lambda: "session-workspace-decision",
        task_id_factory=lambda: "task-workspace-decision",
    ).create_session(handoff or make_handoff())


def make_strategy(creation) -> StrategyDecision:
    return StrategyDecision(
        mode="react",
        skill_name=None,
        reason="Use ReAct.",
        initial_plan=None,
        completion_criteria=creation.session.handoff.completion_criteria,
        session_id=creation.context.session_id,
        task_id=creation.context.task_id,
        trace_id=creation.context.trace_id,
    )


def make_skill_manager() -> SkillManager:
    manager = SkillManager()
    manager.register(
        SkillDefinition(
            name="note_help",
            description="Help answer questions using note lookup.",
            when_to_use="Use when the user asks about notes.",
            path=Path("skill/skills/note_help/SKILL.md"),
            optional_tools=("note_lookup",),
        )
    )
    return manager


def note_tool_definition() -> ToolDefinition:
    return ToolDefinition(
        name="note_lookup",
        description="Find notes by query.",
        schema_version="1.0",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
        input_examples=({"query": "today"},),
        output_schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
        },
    )


@dataclass(slots=True)
class RecordingProvider:
    output: object
    last_prompt: str = ""
    calls: int = 0

    def generate(self, prompt: str, *, trace_id=None, metadata=None):
        self.calls += 1
        self.last_prompt = prompt
        return ProviderResult(
            provider_name="recording_llm",
            model_name="recording-model",
            trace_id=trace_id,
            output=self.output,
            metadata=dict(metadata or {}),
        )


class DefinitionDirectory:
    def __init__(self, definitions):
        self.definitions = tuple(definitions)
        self.execute_called = False

    def list_definitions(self, context):
        return self.definitions

    def execute(self, *args, **kwargs):
        self.execute_called = True
        raise AssertionError("SubAgent must not execute tools")


def make_subagent(provider: RecordingProvider, directory: DefinitionDirectory):
    return SubAgent(
        skill_manager=make_skill_manager(),
        tool_directory=directory,
        llm_provider=provider,
    )


def test_subagent_places_visible_skills_tools_and_observations_in_workspace():
    provider = RecordingProvider(
        {"action": "COMPLETE", "reason": "Enough information."}
    )
    directory = DefinitionDirectory((note_tool_definition(),))
    creation = make_creation()
    creation.session.tool_trace = (
        {
            "tool_name": "note_lookup",
            "payload": {"summary": "Found today's note."},
        },
    )

    decision = make_subagent(provider, directory).decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )

    assert decision.action == COMPLETE
    assert "WorkSpace:" in provider.last_prompt
    assert "visible_skills" in provider.last_prompt
    assert "note_help" in provider.last_prompt
    assert "visible_tools" in provider.last_prompt
    assert "note_lookup" in provider.last_prompt
    assert "input_examples" in provider.last_prompt
    assert "observations" in provider.last_prompt
    assert "Found today's note." in provider.last_prompt


def test_subagent_can_return_complete_when_no_tool_is_needed():
    provider = RecordingProvider(
        {"action": "COMPLETE", "reason": "No tool is needed."}
    )
    directory = DefinitionDirectory((note_tool_definition(),))
    creation = make_creation(make_handoff("你好"))

    decision = make_subagent(provider, directory).decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )

    assert decision.action == COMPLETE
    assert decision.reason == "No tool is needed."
    assert directory.execute_called is False


def test_subagent_can_return_call_tool_using_visible_tool():
    provider = RecordingProvider(
        {
            "action": "CALL_TOOL",
            "tool_name": "note_lookup",
            "arguments": {"query": "today"},
            "reason": "Lookup is useful.",
        }
    )
    directory = DefinitionDirectory((note_tool_definition(),))
    creation = make_creation()

    decision = make_subagent(provider, directory).decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )

    assert decision.action == CALL_TOOL
    assert decision.tool_name == "note_lookup"
    assert decision.tool_input == {"query": "today"}
    assert directory.execute_called is False


def test_subagent_replans_unknown_tool_without_execution():
    provider = RecordingProvider(
        {
            "action": "CALL_TOOL",
            "tool_name": "missing_tool",
            "arguments": {},
            "reason": "Try a missing tool.",
        }
    )
    directory = DefinitionDirectory((note_tool_definition(),))
    creation = make_creation()

    decision = make_subagent(provider, directory).decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )

    assert decision.action == REPLAN
    assert "Unknown tool" in decision.reason
    assert directory.execute_called is False


def test_subagent_does_not_repeat_tool_when_observation_is_sufficient():
    provider = RecordingProvider(
        {"action": "COMPLETE", "reason": "Observation is enough."}
    )
    directory = DefinitionDirectory((note_tool_definition(),))
    creation = make_creation()
    creation.session.tool_trace = (
        {
            "tool_name": "note_lookup",
            "payload": {"summary": "The user has one meeting today."},
        },
    )

    decision = make_subagent(provider, directory).decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )

    assert decision.action == COMPLETE
    assert decision.tool_name is None
    assert "The user has one meeting today." in provider.last_prompt
    assert directory.execute_called is False
