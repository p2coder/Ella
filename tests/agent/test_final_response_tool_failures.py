from dataclasses import dataclass, field

from agent.final_response import FinalResponseGenerator
from prompts.engine import PromptBuildResult
from providers.base import ProviderResult
from sessions.execution_state import ToolFailureKind, ToolFailureObservation


@dataclass
class RecordingPromptEngine:
    contexts: list[dict] = field(default_factory=list)

    def build(self, prompt_type, context):
        self.contexts.append(context)
        return PromptBuildResult("safe prompt", prompt_type, "final_response", ())


@dataclass
class AnswerProvider:
    provider_name: str = "answer"
    model_name: str = "answer-v1"

    def generate(self, prompt, *, trace_id=None, metadata=None):
        return ProviderResult(
            self.provider_name,
            self.model_name,
            trace_id,
            {"text": "摄像头权限不足，因此我无法查看当前画面。"},
        )


def permission_failure():
    return ToolFailureObservation(
        attempt_id="step1_try",
        tool_name="camera_scene",
        kind=ToolFailureKind.PERMISSION_DENIED,
        code="permission_denied",
        message="camera permission was denied",
        arguments={},
        retryable=False,
    )


def test_failure_summary_enters_prompt_without_raw_result():
    prompt_engine = RecordingPromptEngine()
    generator = FinalResponseGenerator(prompt_engine, AnswerProvider())

    result = generator.generate(
        trace_id="trace-failure-answer",
        user_input="看看我面前有什么",
        task_goal="Inspect the current scene.",
        tool_results=(),
        execution_failures=(permission_failure(),),
    )

    context = prompt_engine.contexts[0]
    assert context["execution_failure_summary"]
    assert "permission_denied" in context["execution_failure_summary"]
    assert "raw_result" not in repr(context)
    assert "internal secret" not in repr(context)
    assert "权限不足" in result.final_response


def test_failure_summary_is_user_safe_and_deterministic():
    generator = FinalResponseGenerator(RecordingPromptEngine(), AnswerProvider())

    summary = generator.summarize_execution_failures((permission_failure(),))

    assert summary == (
        "camera_scene: permission_denied "
        "(permission_denied) - camera permission was denied; retryable=false"
    )
