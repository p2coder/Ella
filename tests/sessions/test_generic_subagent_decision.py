from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent.context import AgentExecutionContext, CapabilityScope
from agent.handoff import HandoffRequest
from events import StandardizedEvent
from prompts.engine import PromptType
from providers.base import ProviderResult
from sessions.decision import CALL_TOOL, COMPLETE, REPLAN, WAIT, ExecutionDecision
from sessions.session_manager import TaskSessionManager
from sessions.strategy import StrategyDecision
from sessions.subagent import SubAgent
from skill.loader import SkillLoader
from skill.manager import SkillManager
from skill.registry import SkillDefinition
from tools.base import ToolDefinition


def make_handoff(
    *,
    goal: str = "Prepare a concise reminder before leaving.",
    text: str = "Ella，我要出门了",
    context_summary: str = "The user is heading out.",
) -> HandoffRequest:
    return HandoffRequest(
        task_goal=goal,
        trigger_event=StandardizedEvent(
            trace_id="trace-generic-react",
            source="test",
            timestamp=datetime(2026, 6, 14, tzinfo=timezone.utc),
            payload={"text": text},
            event_type="USER_UTTERANCE",
            metadata={"trigger_kind": "user_initiated"},
        ),
        user_preference_summary="Prefers concise answers.",
        environment_summary="Mock environment.",
        context_summary=context_summary,
        constraints=("Be concise.",),
        completion_criteria=("The request is answered.",),
    )


def make_creation(
    handoff: HandoffRequest,
    *,
    allowed_tools: tuple[str, ...] = (),
    allowed_skills: tuple[str, ...] = (),
):
    creation = TaskSessionManager(
        allowed_tools=allowed_tools,
        session_id_factory=lambda: "session-generic-react",
        task_id_factory=lambda: "task-generic-react",
    ).create_session(handoff)
    if allowed_skills:
        creation = type(creation)(
            session=creation.session,
            context=AgentExecutionContext(
                agent_id=creation.context.agent_id,
                agent_role=creation.context.agent_role,
                parent_agent_id=creation.context.parent_agent_id,
                session_id=creation.context.session_id,
                task_id=creation.context.task_id,
                trace_id=creation.context.trace_id,
                handoff_goal=creation.context.handoff_goal,
                memory_scope=creation.context.memory_scope,
                permissions=creation.context.permissions,
                capability_scope=CapabilityScope(
                    agent_role=creation.context.agent_role,
                    allowed_skills=allowed_skills,
                    allowed_tools=allowed_tools,
                ),
            ),
        )
    return creation


def make_skill(
    name: str,
    description: str,
    when_to_use: str,
    *,
    required_tools: tuple[str, ...] = (),
    optional_tools: tuple[str, ...] = (),
    path: Path | None = None,
) -> SkillDefinition:
    return SkillDefinition(
        name=name,
        description=description,
        when_to_use=when_to_use,
        path=path or Path(f"skill/skills/{name}/SKILL.md"),
        required_tools=required_tools,
        optional_tools=optional_tools,
    )


def make_manager(*skills: SkillDefinition, loader: SkillLoader | None = None):
    manager = SkillManager(loader=loader or SkillLoader())
    for skill in skills:
        manager.register(skill)
    return manager


def make_strategy(creation, skill_name: str | None = None) -> StrategyDecision:
    return StrategyDecision(
        mode="react",
        skill_name=skill_name,
        reason="Use ReAct with optional skill guidance.",
        initial_plan=None,
        completion_criteria=creation.session.handoff.completion_criteria,
        session_id=creation.context.session_id,
        task_id=creation.context.task_id,
        trace_id=creation.context.trace_id,
    )


def test_default_strategy_is_react_and_going_out_is_selected_from_metadata() -> None:
    skill = make_skill(
        "going_out",
        "Prepare a reminder before leaving.",
        "Use when the user is heading out.",
    )
    creation = make_creation(make_handoff())

    strategy = SubAgent(make_manager(skill)).select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )

    assert strategy.mode == "react"
    assert strategy.skill_name == "going_out"


def test_another_registered_skill_is_selected_without_code_changes() -> None:
    skill = make_skill(
        "study_support",
        "Create a focused study plan for an exam.",
        "Use when the user needs study or exam planning.",
    )
    creation = make_creation(
        make_handoff(
            goal="Create a focused study plan for my exam.",
            text="Help me plan my exam study.",
            context_summary="The user needs exam planning.",
        )
    )

    strategy = SubAgent(make_manager(skill)).select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )

    assert strategy.mode == "react"
    assert strategy.skill_name == "study_support"


def test_llm_may_choose_visible_skill_or_no_skill() -> None:
    skill = make_skill(
        "study_support",
        "Create a focused study plan.",
        "Use for study planning.",
    )
    creation = make_creation(make_handoff(goal="Handle a task."))
    choose_skill = RecordingProvider(
        {"mode": "react", "skill_name": "study_support", "reason": "Useful."}
    )
    no_skill = RecordingProvider(
        {"mode": "react", "skill_name": None, "reason": "No skill needed."}
    )

    selected = SubAgent(make_manager(skill), llm_provider=choose_skill).select_strategy(
        creation.session.handoff, creation.context, creation.session
    )
    plain = SubAgent(make_manager(skill), llm_provider=no_skill).select_strategy(
        creation.session.handoff, creation.context, creation.session
    )

    assert selected.skill_name == "study_support"
    assert plain.skill_name is None
    assert "strategy_selection" in choose_skill.metadata["boundary"]
    assert choose_skill.prompt_types == [PromptType.STRATEGY_SELECTION]


def test_unknown_or_hidden_llm_skill_falls_back_to_no_skill_react() -> None:
    visible = make_skill("visible_skill", "Visible help.", "Use for visible work.")
    hidden = make_skill("hidden_skill", "Hidden help.", "Use for hidden work.")
    creation = make_creation(
        make_handoff(goal="Unmatched request."),
        allowed_skills=("visible_skill",),
    )

    strategy = SubAgent(
        make_manager(visible, hidden),
        llm_provider=RecordingProvider(
            {"mode": "react", "skill_name": "hidden_skill", "reason": "Try it."}
        ),
    ).select_strategy(creation.session.handoff, creation.context, creation.session)

    assert strategy.mode == "react"
    assert strategy.skill_name is None


def test_no_skill_react_can_choose_visible_tool_through_llm() -> None:
    creation = make_creation(
        make_handoff(goal="Look up a useful fact."),
        allowed_tools=("fact_lookup",),
    )
    provider = RecordingProvider(
        {
            "action": "CALL_TOOL",
            "tool_name": "fact_lookup",
            "arguments": {"query": "Ella"},
            "reason": "Need a fact.",
        }
    )
    subagent = SubAgent(
        make_manager(),
        tool_directory=DefinitionDirectory((tool_definition("fact_lookup"),)),
        llm_provider=provider,
    )

    decision = subagent.decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )

    assert decision == ExecutionDecision(
        CALL_TOOL,
        "fact_lookup",
        {"query": "Ella"},
        "Need a fact.",
        False,
    )
    assert provider.prompt_types == [PromptType.EXECUTION_DECISION]


def test_selected_skill_content_tools_and_observations_enter_decision_prompt(
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "research"
    skill_dir.mkdir()
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        "---\n"
        "name: research\n"
        "description: Research a topic.\n"
        "when_to_use: Use for research tasks.\n"
        "required_tools: fact_lookup\n"
        "---\n\n"
        "# research\n\nUse observations before choosing another tool.\n",
        encoding="utf-8",
    )
    loader = SkillLoader(tmp_path)
    skill = loader.load_summary("research")
    creation = make_creation(
        make_handoff(goal="Research Ella runtime."),
        allowed_tools=("fact_lookup",),
    )
    creation.session.tool_trace = (
        {"tool_name": "fact_lookup", "payload": {"summary": "Observed fact."}},
    )
    provider = RecordingProvider({"action": "COMPLETE", "reason": "Enough."})

    decision = SubAgent(
        make_manager(skill, loader=loader),
        tool_directory=DefinitionDirectory((tool_definition("fact_lookup"),)),
        llm_provider=provider,
    ).decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation, "research"),
    )

    assert decision.action == COMPLETE
    assert "Use observations before choosing another tool." in provider.last_prompt
    assert "fact_lookup" in provider.last_prompt
    assert "Observed fact." in provider.last_prompt


def test_generic_mock_safe_fallback_completes_without_skill_or_observation() -> None:
    creation = make_creation(
        make_handoff(goal="Handle an unmatched request."),
        allowed_tools=("fact_lookup",),
    )

    decision = SubAgent(make_manager()).decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )

    assert decision.action == COMPLETE
    assert decision.tool_name is None


def test_generic_mock_safe_fallback_completes_when_observation_exists() -> None:
    creation = make_creation(make_handoff(goal="Handle an unmatched request."))
    creation.session.tool_trace = (
        {"tool_name": "fact_lookup", "payload": {"summary": "Done."}},
    )

    decision = SubAgent(make_manager()).decide_next_action(
        creation.session.handoff,
        creation.context,
        creation.session,
        make_strategy(creation),
    )

    assert decision.action == COMPLETE


def test_mock_safe_skill_fallback_is_deterministic_and_generic() -> None:
    skill = make_skill(
        "departure_assistant",
        "Prepare a reminder before leaving.",
        "Use when the user is heading out.",
        required_tools=("weather", "checklist"),
    )
    creation = make_creation(
        make_handoff(),
        allowed_tools=("weather", "checklist"),
    )
    subagent = SubAgent(make_manager(skill))
    strategy = make_strategy(creation, "departure_assistant")

    first = subagent.decide_next_action(
        creation.session.handoff, creation.context, creation.session, strategy
    )
    creation.session.tool_trace = (
        {"tool_name": "weather", "payload": {"summary": "Clear."}},
    )
    second = subagent.decide_next_action(
        creation.session.handoff, creation.context, creation.session, strategy
    )

    assert first.tool_name == "weather"
    assert second.tool_name == "checklist"
    assert "going-out" not in first.reason.lower()


def test_invalid_llm_action_returns_one_replan_without_mutating_session() -> None:
    creation = make_creation(
        make_handoff(),
        allowed_tools=("fact_lookup",),
    )
    before = (
        creation.session.state,
        creation.session.tool_trace,
        creation.session.current_strategy,
        creation.session.completion,
    )
    subagent = SubAgent(
        make_manager(),
        tool_directory=DefinitionDirectory((tool_definition("fact_lookup"),)),
        llm_provider=RecordingProvider("not json"),
    )

    decision = subagent.decide_next_action(
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
    )
    assert isinstance(decision, ExecutionDecision)
    assert decision.action == REPLAN
    assert after == before


def test_subagent_source_has_no_direct_going_out_gate_or_manual_prompt_json() -> None:
    source = Path("sessions/subagent.py").read_text(encoding="utf-8")

    assert 'get_summary("going_out")' not in source
    assert 'strategy.skill_name != "going_out"' not in source
    assert 'mode="skill"' not in source
    assert 'mode="plan_to_execute"' not in source
    assert "json.dumps(" not in source


@dataclass(slots=True)
class RecordingProvider:
    response: object
    provider_name: str = "recording_llm"
    model_name: str = "recording-v1"
    last_prompt: str = ""
    metadata: dict[str, object] | None = None
    prompt_types: list[str] = None

    def __post_init__(self) -> None:
        self.prompt_types = []

    def generate(self, prompt: str, *, trace_id=None, metadata=None) -> ProviderResult:
        self.last_prompt = prompt
        self.metadata = dict(metadata or {})
        boundary = str(self.metadata.get("boundary", ""))
        if boundary:
            self.prompt_types.append(boundary.upper())
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=self.response,
            metadata=self.metadata,
        )


class DefinitionDirectory:
    def __init__(self, definitions: tuple[ToolDefinition, ...]) -> None:
        self.definitions = definitions

    def list_definitions(self, context: AgentExecutionContext):
        return tuple(
            definition
            for definition in self.definitions
            if definition.name in context.allowed_tools
        )


def tool_definition(name: str) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"Use {name} when its information is required.",
        schema_version="1.0",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "additionalProperties": False,
        },
        input_examples=({"query": "Ella"},),
        output_schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    )
