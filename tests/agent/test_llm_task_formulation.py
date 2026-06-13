from datetime import datetime, timezone
from pathlib import Path

from agent.formulation import TaskFormulation, TaskFormulator
from events import StandardizedEvent
from providers.base import ProviderError, ProviderResult
from providers.mock import MockLLMProvider


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def make_user_event(text: str = "Ella，我要出门了") -> StandardizedEvent:
    return StandardizedEvent(
        trace_id="trace-llm-formulation",
        source="cli_input",
        timestamp=FIXED_TIME,
        payload={"text": text},
        event_type="USER_UTTERANCE",
        confidence=1.0,
        priority=0.9,
        metadata={"trigger_kind": "user_initiated"},
    )


def test_formulation_still_works_without_provider():
    formulation = TaskFormulator().formulate(
        trigger_event=make_user_event(),
        user_preference_summary="Prefers concise reminders.",
        environment_summary="No visual context yet.",
    )

    assert formulation.goal == "Give the user a short, necessary reminder before leaving."
    assert formulation.provider_error is None
    assert formulation.formulation_source == "deterministic"


def test_formulation_can_use_mock_llm_provider():
    formulation = TaskFormulator(llm_provider=MockLLMProvider()).formulate(
        trigger_event=make_user_event("Remind me before I leave"),
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Scene summary unavailable.",
    )

    assert isinstance(formulation, TaskFormulation)
    assert formulation.formulation_source == "llm_provider"
    assert formulation.provider_error is None
    assert formulation.goal.startswith("Mock response for:")


def test_provider_output_influences_goal_and_context_summary():
    formulation = TaskFormulator(llm_provider=StructuredLLMProvider()).formulate(
        trigger_event=make_user_event(),
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Umbrella is not visible.",
    )

    assert formulation.goal == "Give a short umbrella and essentials reminder."
    assert formulation.context_summary == "LLM summarized the user as leaving soon."
    assert formulation.completion_criteria == (
        "A provider-generated task goal is ready for handoff.",
    )


def test_provider_failure_is_handled_without_breaking_runtime_state():
    formulation = TaskFormulator(llm_provider=FailingLLMProvider()).formulate(
        trigger_event=make_user_event(),
        user_preference_summary="Prefers concise reminders.",
        environment_summary="No visual context yet.",
    )

    assert formulation.goal == "Give the user a short, necessary reminder before leaving."
    assert formulation.formulation_source == "deterministic_fallback"
    assert formulation.provider_error == {
        "provider_name": "failing_llm",
        "code": "provider_unavailable",
        "message": "llm unavailable",
    }


def test_formulation_does_not_import_qwen_directly():
    source = (PROJECT_ROOT / "agent" / "formulation.py").read_text(encoding="utf-8")

    assert "providers.qwen" not in source


class StructuredLLMProvider:
    provider_name = "structured_llm"
    model_name = "structured-llm"

    def generate(self, prompt, *, trace_id=None, metadata=None):
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output={
                "goal": "Give a short umbrella and essentials reminder.",
                "context_summary": "LLM summarized the user as leaving soon.",
            },
        )


class FailingLLMProvider:
    provider_name = "failing_llm"
    model_name = "failing-llm"

    def generate(self, prompt, *, trace_id=None, metadata=None):
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=None,
            error=ProviderError(
                provider_name=self.provider_name,
                message="llm unavailable",
                code="provider_unavailable",
            ),
        )
