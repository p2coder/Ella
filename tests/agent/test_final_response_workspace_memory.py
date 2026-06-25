from dataclasses import dataclass

from agent.final_response import FinalResponseGenerator
from providers.base import ProviderError, ProviderResult
from prompts.engine import PromptEngine
from tools.base import ToolResult


@dataclass(slots=True)
class RecordingProvider:
    output: object
    failed: bool = False
    calls: int = 0
    last_prompt: str = ""
    provider_name: str = "recording_llm"
    model_name: str = "recording-model"

    def generate(self, prompt, *, trace_id=None, metadata=None):
        self.calls += 1
        self.last_prompt = prompt
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


def make_tool_result(
    tool_name: str = "camera_scene",
    payload: dict | None = None,
) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        task_id="task-final-response",
        session_id="session-final-response",
        trace_id="trace-final-response",
        payload=payload
        or {
            "status": "available",
            "scene_summary": "The user is holding a phone.",
            "visible_items": ("phone", "desk"),
        },
    )


def generate(provider, **kwargs):
    return FinalResponseGenerator(
        prompt_engine=PromptEngine(),
        llm_provider=provider,
    ).generate(
        trace_id="trace-final-response",
        user_input=kwargs.get("user_input", "我手里拿着什么？"),
        task_goal=kwargs.get("task_goal", "Identify what the user is holding."),
        tool_results=kwargs.get("tool_results", (make_tool_result(),)),
        task_constraints=("Be concise.",),
        completion_criteria=("The user receives an answer.",),
        user_preference_summary="Prefers concise answers.",
        environment_summary="Desk scene.",
        memory_context=kwargs.get("memory_context", "User prefers Chinese."),
    )


def test_final_response_prompt_includes_user_input_memory_and_workspace():
    provider = RecordingProvider({"final_response": "你手里拿着手机。"})

    result = generate(provider)

    prompt = result.prompt_trace["prompt_text"]
    assert "user_prompt" in prompt
    assert "我手里拿着什么？" in prompt
    assert "Memory:" in prompt
    assert "User prefers Chinese." in prompt
    assert "WorkSpace:" in prompt
    assert "overall_goal" in prompt
    assert "Identify what the user is holding." in prompt


def test_final_response_prompt_includes_completed_steps_and_tool_summary():
    provider = RecordingProvider({"final_response": "你手里拿着手机。"})

    result = generate(provider)

    prompt = result.prompt_trace["prompt_text"]
    assert "completed_steps" in prompt
    assert "camera_scene: available" in prompt
    assert "tool_results_summary" in prompt
    assert "The user is holding a phone." in prompt
    assert "visible_items" in prompt


def test_current_observations_take_precedence_over_memory_in_prompt_order():
    provider = RecordingProvider({"final_response": "当前画面显示你拿着手机。"})

    result = generate(
        provider,
        memory_context="Earlier memory says the user often forgets their phone.",
    )

    prompt = result.prompt_trace["prompt_text"]
    assert prompt.index("Memory:") < prompt.index("WorkSpace:")
    assert "Earlier memory says" in prompt
    assert "The user is holding a phone." in prompt


def test_unavailable_evidence_is_stated_as_limitation_in_prompt_and_fallback():
    provider = RecordingProvider(None, failed=True)
    unavailable = make_tool_result(
        payload={
            "status": "unavailable",
            "summary": "Visual context is unavailable.",
            "error": "camera unavailable",
        }
    )

    result = generate(provider, tool_results=(unavailable,))

    assert "Visual context is unavailable." in result.prompt_trace["prompt_text"]
    assert "camera unavailable" in result.prompt_trace["prompt_text"]
    assert "视觉上下文当前不可用" in result.final_response


def test_fallback_does_not_use_old_task_completed_template():
    provider = RecordingProvider(None, failed=True)

    result = generate(provider)

    assert not result.final_response.startswith("Task completed:")
    assert "根据当前信息" in result.final_response


def test_final_response_generator_does_not_execute_tools_or_write_memory():
    provider = RecordingProvider({"final_response": "完成。"})
    tool_result = make_tool_result()

    result = generate(provider, tool_results=(tool_result,))

    assert provider.calls == 1
    assert result.final_response == "完成。"
    assert tool_result.payload["scene_summary"] == "The user is holding a phone."
