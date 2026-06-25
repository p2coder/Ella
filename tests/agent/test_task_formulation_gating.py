from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent.formulation import TaskFormulator
from events import StandardizedEvent
from providers.base import ProviderError, ProviderResult


def make_event(text: str) -> StandardizedEvent:
    return StandardizedEvent(
        trace_id="trace-formulation-gating",
        source="test",
        timestamp=datetime(2026, 6, 25, tzinfo=timezone.utc),
        payload={"text": text},
        event_type="USER_UTTERANCE",
        metadata={"trigger_kind": "user_initiated"},
    )


@dataclass(slots=True)
class RecordingProvider:
    output: object
    failed: bool = False
    calls: int = 0
    provider_name: str = "recording_llm"
    model_name: str = "recording-model"

    def generate(self, prompt, *, trace_id=None, metadata=None):
        self.calls += 1
        error = None
        if self.failed:
            error = ProviderError(
                provider_name=self.provider_name,
                message="provider unavailable",
                code="provider_unavailable",
            )
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=self.output,
            metadata=dict(metadata or {}),
            error=error,
        )


def formulate(text: str, provider: RecordingProvider | None = None):
    return TaskFormulator(llm_provider=provider).formulate(
        trigger_event=make_event(text),
        user_preference_summary="Prefers concise answers.",
        environment_summary="No special environment.",
    )


def test_greeting_does_not_become_forced_reminder_task_goal():
    provider = RecordingProvider({"goal": "Forced provider goal."})

    formulation = formulate("你好", provider)

    assert provider.calls == 0
    assert formulation.goal == "Respond naturally to the user's greeting."
    assert "reminder" not in formulation.goal.lower()
    assert "提醒" not in formulation.goal


def test_ordinary_question_bypasses_task_formulation_prompt():
    provider = RecordingProvider({"goal": "Forced provider goal."})

    formulation = formulate("Python 的 dataclass 是什么？", provider)

    assert provider.calls == 0
    assert formulation.goal == "Answer the user's question directly."
    assert formulation.formulation_source == "deterministic"


def test_clear_direct_instruction_can_proceed_without_llm_formulation():
    provider = RecordingProvider({"goal": "Forced provider goal."})

    formulation = formulate("请总结这句话：今天早点休息。", provider)

    assert provider.calls == 0
    assert formulation.goal == "Complete the user's direct instruction."
    assert formulation.completion_criteria == (
        "The direct instruction is handled.",
    )


def test_ambiguous_request_uses_task_formulation():
    provider = RecordingProvider(
        {
            "goal": "Help the user clarify what is making them stuck.",
            "context_summary": "The user feels uncertain.",
        }
    )

    formulation = formulate("我有点迷茫，不知道下一步要做什么", provider)

    assert provider.calls == 1
    assert formulation.goal == "Help the user clarify what is making them stuck."
    assert formulation.context_summary == "The user feels uncertain."
    assert formulation.formulation_source == "llm_provider"


def test_task_formulation_constraints_do_not_choose_skill_or_tool():
    formulation = formulate("我有点迷茫，不知道下一步要做什么")
    constraints = " ".join(formulation.constraints)

    assert "Do not choose a skill" in constraints
    assert "Do not choose or call tools during task formulation." in constraints


def test_provider_failure_falls_back_safely_for_ambiguous_request():
    provider = RecordingProvider(None, failed=True)

    formulation = formulate("我不知道怎么办", provider)

    assert provider.calls == 1
    assert formulation.goal == "Clarify the user's intent and prepare a useful response."
    assert formulation.formulation_source == "deterministic_fallback"
    assert formulation.provider_error == {
        "provider_name": "recording_llm",
        "code": "provider_unavailable",
        "message": "provider unavailable",
    }


def test_formulation_does_not_import_qwen_directly():
    source = (Path(__file__).resolve().parents[2] / "agent" / "formulation.py").read_text(
        encoding="utf-8"
    )

    assert "providers.qwen" not in source
