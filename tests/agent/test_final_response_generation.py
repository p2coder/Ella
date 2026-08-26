from agent.final_response import FinalResponseGenerator
from prompts.engine import PromptBuildResult, PromptType
from providers.base import ProviderError, ProviderResult
from tools.base import ToolResult


def test_final_response_generator_builds_prompt_through_prompt_engine():
    prompt_engine = RecordingPromptEngine(prompt="final response prompt")
    llm_provider = RecordingLLMProvider(output={"text": "Remember your phone."})

    result = FinalResponseGenerator(
        prompt_engine=prompt_engine,
        llm_provider=llm_provider,
    ).generate(
        trace_id="trace-final",
        user_input="Ella，我要出门了",
        task_goal="Give a short leaving reminder.",
        tool_results=[
            ToolResult(
                tool_name="camera_scene",
                task_id="task-1",
                trace_id="trace-final",
                payload={
                    "scene_summary": "Phone is visible on the desk.",
                    "visible_items": ["phone", "keys"],
                },
            )
        ],
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Desk scene available.",
    )

    assert len(prompt_engine.calls) == 1
    prompt_type, context = prompt_engine.calls[0]
    assert prompt_type == PromptType.FINAL_RESPONSE
    assert context.items() >= {
                "trace_id": "trace-final",
                "user_input": "Ella，我要出门了",
                "task_goal": "Give a short leaving reminder.",
                "task_constraints": (),
                "completion_criteria": (),
                "tool_results_summary": (
                    "camera_scene:\n"
                    "- scene_summary: Phone is visible on the desk.\n"
                    "- visible_items: phone, keys"
                ),
                "scene_summary": "Phone is visible on the desk.",
                "visible_items": ("phone", "keys"),
                "user_preference_summary": "Prefers concise reminders.",
                "environment_summary": "Desk scene available.",
                "memory_context": "",
                "provider_or_tool_errors": (),
            }.items()
    assert llm_provider.prompts == ["final response prompt"]
    assert result.final_response == "Remember your phone."
    assert result.prompt_trace == {
        "trace_id": "trace-final",
        "prompt_type": PromptType.FINAL_RESPONSE,
        "prompt_name": "final_response",
        "prompt_text": "final response prompt",
        "provider_name": "recording_llm",
        "model_name": "recording-model",
        "llm_output": {"text": "Remember your phone."},
    }


def test_llm_provider_receives_exact_prompt_engine_prompt():
    prompt_engine = RecordingPromptEngine(prompt="exact prompt text")
    llm_provider = RecordingLLMProvider(output={"final_response": "Exact answer."})

    FinalResponseGenerator(prompt_engine=prompt_engine, llm_provider=llm_provider).generate(
        trace_id="trace-exact",
        user_input="检查桌面",
        task_goal="Check the desk.",
        tool_results=[],
    )

    assert llm_provider.prompts == [prompt_engine.results[0].prompt]
    assert llm_provider.trace_ids == ["trace-exact"]
    assert llm_provider.metadata == [{"boundary": "final_response"}]


def test_tool_results_are_summarized_without_python_repr():
    generator = FinalResponseGenerator(
        prompt_engine=RecordingPromptEngine(prompt="prompt"),
        llm_provider=RecordingLLMProvider(output={"text": "Done."}),
    )
    tool_result = ToolResult(
        tool_name="camera_scene",
        task_id="task-1",
        trace_id="trace-summary",
        payload={
            "scene_summary": "Umbrella is not visible.",
            "visible_items": ["phone", "wallet"],
            "error": None,
        },
    )

    summary = generator.summarize_tool_results([tool_result])

    assert "camera_scene:" in summary
    assert "scene_summary: Umbrella is not visible." in summary
    assert "visible_items: phone, wallet" in summary
    assert "ToolResult(" not in summary


def test_provider_failure_returns_deterministic_fallback_not_old_template():
    result = FinalResponseGenerator(
        prompt_engine=RecordingPromptEngine(prompt="prompt"),
        llm_provider=FailingLLMProvider(),
    ).generate(
        trace_id="trace-fallback",
        user_input="我要出门了",
        task_goal="Check essentials before leaving.",
        tool_results=[
            {
                "tool_name": "camera_scene",
                "payload": {"scene_summary": "Visual context is unavailable."},
            }
        ],
    )

    assert result.final_response.startswith("我已经根据当前可用信息完成了处理")
    assert not result.final_response.startswith("Task completed:")
    assert "Check essentials before leaving." not in result.final_response
    assert "Visual context is unavailable." in result.final_response
    assert result.provider_error == {
        "provider_name": "failing_llm",
        "code": "provider_unavailable",
        "message": "llm unavailable",
    }


def test_provider_failure_greeting_does_not_expose_internal_task_goal():
    result = FinalResponseGenerator(
        prompt_engine=RecordingPromptEngine(prompt="prompt"),
        llm_provider=FailingLLMProvider(),
    ).generate(
        trace_id="trace-greeting-fallback",
        user_input="你好",
        task_goal="Respond naturally to the user's greeting.",
        tool_results=[],
    )

    assert result.final_response == "你好！有什么我可以帮你的吗？"
    assert "Respond naturally" not in result.final_response
    assert "工具结果" not in result.final_response


def test_memory_context_is_passed_into_final_response_prompt():
    prompt_engine = RecordingPromptEngine(prompt="prompt with memory")
    llm_provider = RecordingLLMProvider(output={"text": "Use remembered context."})

    FinalResponseGenerator(
        prompt_engine=prompt_engine,
        llm_provider=llm_provider,
    ).generate(
        trace_id="trace-memory-prompt",
        user_input="继续",
        task_goal="Answer using prior context.",
        tool_results=[],
        memory_context="## Task old\n- final_response: User prefers tea.\n",
    )

    assert prompt_engine.calls[0][1]["memory_context"] == (
        "## Task old\n- final_response: User prefers tea.\n"
    )


def test_unavailable_visual_context_is_reflected_in_context_and_fallback():
    prompt_engine = RecordingPromptEngine(prompt="prompt")

    result = FinalResponseGenerator(
        prompt_engine=prompt_engine,
        llm_provider=FailingLLMProvider(),
    ).generate(
        trace_id="trace-visual",
        user_input="看看桌上有没有伞",
        task_goal="Check visible items.",
        tool_results=[
            ToolResult(
                tool_name="camera_scene",
                task_id="task-1",
                trace_id="trace-visual",
                payload={"available": False, "summary": "Visual context is unavailable."},
            )
        ],
    )

    assert prompt_engine.calls[0][1]["provider_or_tool_errors"] == (
        "camera_scene: Visual context is unavailable.",
    )
    assert "Visual context is unavailable." in result.final_response


def test_generator_does_not_execute_tools_mutate_sessions_or_write_memory():
    result = FinalResponseGenerator(
        prompt_engine=RecordingPromptEngine(prompt="prompt"),
        llm_provider=RecordingLLMProvider(output={"text": "No side effects."}),
    ).generate(
        trace_id="trace-side-effects",
        user_input="hello",
        task_goal="Answer briefly.",
        tool_results=[],
    )

    assert result.final_response == "No side effects."


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
            prompt_name="final_response",
            context_keys=tuple(sorted(copied_context)),
        )
        self.results.append(result)
        return result


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
