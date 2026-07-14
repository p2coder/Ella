from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent.handoff import HandoffRequest
from events import StandardizedEvent
from providers.base import ProviderResult
from sessions.session_manager import TaskSessionManager
from sessions.subagent import SubAgent
from skill.manager import SkillManager
from skill.registry import SkillDefinition


def make_handoff(text: str = "Ella，帮我整理一下今天的计划。") -> HandoffRequest:
    return HandoffRequest(
        task_goal="Help the user with the current request.",
        trigger_event=StandardizedEvent(
            trace_id="trace-mode-only",
            source="test",
            timestamp=datetime(2026, 6, 25, tzinfo=timezone.utc),
            payload={"text": text},
            event_type="USER_UTTERANCE",
            metadata={"trigger_kind": "user_initiated"},
        ),
        user_preference_summary="Prefers concise answers.",
        environment_summary="No special environment.",
        context_summary="The user asked for help.",
        constraints=("Be practical.",),
        completion_criteria=("The request is answered.",),
    )


def make_creation(handoff: HandoffRequest | None = None):
    return TaskSessionManager(
        session_id_factory=lambda: "session-mode-only",
        task_id_factory=lambda: "task-mode-only",
    ).create_session(handoff or make_handoff())


def make_skill_manager() -> SkillManager:
    manager = SkillManager()
    manager.register(
        SkillDefinition(
            name="planning",
            description="Help plan multi-step tasks.",
            when_to_use="Use when a task needs planning.",
            path=Path("skill/skills/planning/SKILL.md"),
        )
    )
    return manager


@dataclass(slots=True)
class RecordingProvider:
    output: object
    calls: int = 0
    last_prompt: str = ""
    metadata: dict[str, object] | None = None
    provider_name: str = "recording_llm"
    model_name: str = "recording-model"

    def generate(self, prompt: str, *, trace_id=None, metadata=None):
        self.calls += 1
        self.last_prompt = prompt
        self.metadata = dict(metadata or {})
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=self.output,
            metadata=self.metadata,
        )


def test_subagent_accepts_react_strategy_output():
    provider = RecordingProvider(
        {
            "mode": "react",
            "reason": "The request can be handled step by step.",
            "needs_decomposition": False,
            "plan_summary": None,
        }
    )
    creation = make_creation()

    strategy = SubAgent(
        make_skill_manager(),
        llm_provider=provider,
    ).select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )

    assert strategy.mode == "react"
    assert strategy.skill_name is None
    assert strategy.reason == "The request can be handled step by step."
    assert strategy.initial_plan is None
    assert provider.metadata == {"boundary": "strategy_selection"}
    assert creation.session.task_local_state[
        "strategy_selection_prompt_text"
    ] == provider.last_prompt


def test_subagent_falls_back_from_plan_and_execute_to_react():
    provider = RecordingProvider(
        {
            "mode": "plan_and_execute",
            "reason": "This needs a longer plan.",
            "needs_decomposition": True,
            "plan_summary": "Clarify, gather context, then answer.",
        }
    )
    creation = make_creation()

    strategy = SubAgent(
        make_skill_manager(),
        llm_provider=provider,
    ).select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )

    assert strategy.mode == "react"
    assert strategy.skill_name is None
    assert "only supports ReAct" in strategy.reason
    assert strategy.initial_plan == ("Clarify, gather context, then answer.",)


def test_subagent_ignores_skill_name_returned_by_model():
    provider = RecordingProvider(
        {
            "mode": "react",
            "skill_name": "planning",
            "reason": "Model tried to select a skill too early.",
            "needs_decomposition": False,
            "plan_summary": None,
        }
    )
    creation = make_creation()

    strategy = SubAgent(
        make_skill_manager(),
        llm_provider=provider,
    ).select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )

    assert strategy.mode == "react"
    assert strategy.skill_name is None
    assert strategy.reason == "Model tried to select a skill too early."
    assert "planning" not in provider.last_prompt


def test_strategy_selection_does_not_execute_tools_or_mutate_session():
    provider = RecordingProvider({"mode": "react", "reason": "Proceed."})
    creation = make_creation()
    before_state = creation.session.state
    before_trace = tuple(creation.session.tool_trace)

    strategy = SubAgent(
        make_skill_manager(),
        llm_provider=provider,
    ).select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )

    assert strategy.mode == "react"
    assert provider.calls == 1
    assert creation.session.state == before_state
    assert tuple(creation.session.tool_trace) == before_trace
    assert "CALL_TOOL" not in provider.last_prompt


def test_subagent_defaults_to_react_without_llm_provider():
    creation = make_creation()

    strategy = SubAgent(make_skill_manager()).select_strategy(
        creation.session.handoff,
        creation.context,
        creation.session,
    )

    assert strategy.mode == "react"
    assert strategy.skill_name is None
    assert strategy.reason == "Use ReAct as the default execution mode."
