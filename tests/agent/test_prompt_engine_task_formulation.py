from datetime import datetime, timezone
from pathlib import Path

from agent.formulation import TaskFormulator
from events import StandardizedEvent
from prompts.engine import PromptBuildResult, PromptType
from providers.base import ProviderError, ProviderResult


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def make_event(text: str = "Ella，我要出门了") -> StandardizedEvent:
    return StandardizedEvent(
        trace_id="trace-formulation-prompt",
        source="cli_input",
        timestamp=FIXED_TIME,
        payload={"text": text},
        event_type="USER_UTTERANCE",
        confidence=1.0,
        priority=0.9,
        metadata={"trigger_kind": "user_initiated"},
    )


def test_task_formulator_uses_prompt_engine_for_task_formulation():
    prompt_engine = RecordingPromptEngine(prompt="prompt from engine")
    llm_provider = RecordingLLMProvider(
        output={"goal": "Use the prompt engine to formulate a goal."}
    )

    formulation = TaskFormulator(
        llm_provider=llm_provider,
        prompt_engine=prompt_engine,
    ).formulate(
        trigger_event=make_event("Please help me prepare to leave."),
        user_preference_summary="Prefers concise reminders.",
        environment_summary="No visual context yet.",
    )

    assert prompt_engine.calls == [
        (
            PromptType.TASK_FORMULATION,
            {
                "user_input": "Please help me prepare to leave.",
                "user_preference_summary": "Prefers concise reminders.",
                "environment_summary": "No visual context yet.",
                "event_type": "USER_UTTERANCE",
                "trace_id": "trace-formulation-prompt",
            },
        )
    ]
    assert llm_provider.prompts == ["prompt from engine"]
    assert formulation.goal == "Use the prompt engine to formulate a goal."
    assert formulation.formulation_source == "llm_provider"


def test_llm_provider_receives_exact_prompt_engine_prompt():
    prompt_engine = RecordingPromptEngine(prompt="exact generated prompt")
    llm_provider = RecordingLLMProvider(output={"text": "Goal from exact prompt."})

    TaskFormulator(
        llm_provider=llm_provider,
        prompt_engine=prompt_engine,
    ).formulate(
        trigger_event=make_event("提醒我出门前检查桌面"),
        user_preference_summary="Use Chinese.",
        environment_summary="Desk scene is available.",
    )

    assert llm_provider.prompts == [prompt_engine.results[0].prompt]
    assert llm_provider.metadata == [{"boundary": "task_formulation"}]
    assert llm_provider.trace_ids == ["trace-formulation-prompt"]


def test_formulation_still_works_without_llm_provider():
    formulation = TaskFormulator(prompt_engine=ExplodingPromptEngine()).formulate(
        trigger_event=make_event(),
        user_preference_summary="Prefers concise reminders.",
        environment_summary="No visual context yet.",
    )

    assert formulation.goal == "Give the user a short, necessary reminder before leaving."
    assert formulation.formulation_source == "deterministic"


def test_provider_failure_uses_deterministic_fallback():
    formulation = TaskFormulator(
        llm_provider=FailingLLMProvider(),
        prompt_engine=RecordingPromptEngine(prompt="prompt from engine"),
    ).formulate(
        trigger_event=make_event(),
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


def test_task_formulator_does_not_assemble_full_prompt_internals():
    source = (PROJECT_ROOT / "agent" / "formulation.py").read_text(encoding="utf-8")

    assert "_build_prompt" not in source
    assert "Formulate only what should be done." not in source


def test_formulation_does_not_import_qwen_directly():
    source = (PROJECT_ROOT / "agent" / "formulation.py").read_text(encoding="utf-8")

    assert "providers.qwen" not in source


class RecordingPromptEngine:
    def __init__(self, prompt: str):
        self.prompt = prompt
        self.calls = []
        self.results = []

    def build(self, prompt_type, context):
        copied_context = dict(context)
        self.calls.append((prompt_type, copied_context))
        result = PromptBuildResult(
            prompt=self.prompt,
            prompt_type=prompt_type,
            prompt_name="task_formulation",
            context_keys=tuple(sorted(copied_context)),
        )
        self.results.append(result)
        return result


class ExplodingPromptEngine:
    def build(self, prompt_type, context):
        raise AssertionError("PromptEngine should not be called without llm_provider")


class RecordingLLMProvider:
    provider_name = "recording_llm"
    model_name = "recording-model"

    def __init__(self, output):
        self.output = output
        self.prompts = []
        self.trace_ids = []
        self.metadata = []

    def generate(self, prompt, *, trace_id=None, metadata=None):
        self.prompts.append(prompt)
        self.trace_ids.append(trace_id)
        self.metadata.append(dict(metadata or {}))
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=self.output,
            metadata=dict(metadata or {}),
        )


class FailingLLMProvider:
    provider_name = "failing_llm"
    model_name = "failing-model"

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
