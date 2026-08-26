from prompts.engine import (
    PromptBlock,
    PromptBuildResult,
    PromptEngine,
    PromptFrame,
    PromptType,
    redact_prompt_text,
)


def test_prompt_frame_can_be_built_from_structured_blocks():
    frame = PromptFrame.from_blocks(
        prompt_type=PromptType.FINAL_RESPONSE,
        blocks=(
            PromptBlock("SystemPrompt", "Be helpful."),
            PromptBlock("UserPrompt", {"text": "hello"}),
        ),
        output_contract="Return natural language.",
    )

    assert frame.prompt_type == PromptType.FINAL_RESPONSE
    assert tuple(block.name for block in frame.blocks) == (
        "SystemPrompt",
        "UserPrompt",
    )
    assert frame.output_contract == "Return natural language."


def test_prompt_block_requires_name():
    try:
        PromptBlock("", "content")
    except ValueError as error:
        assert "name" in str(error)
    else:
        raise AssertionError("Expected empty PromptBlock name to fail")


def test_prompt_engine_build_still_returns_prompt_build_result():
    result = PromptEngine().build(
        PromptType.FINAL_RESPONSE,
        {"user_input": "hello", "memory_context": "none"},
    )

    assert isinstance(result, PromptBuildResult)
    assert isinstance(result.prompt, str)
    assert result.prompt_type == PromptType.FINAL_RESPONSE
    assert result.prompt_name == "final_response"
    assert result.context_keys == ("memory_context", "user_input")


def test_prompt_context_keys_are_deterministic():
    first = PromptEngine().build(
        PromptType.FINAL_RESPONSE,
        {"b": "second", "a": "first"},
    )
    second = PromptEngine().build(
        PromptType.FINAL_RESPONSE,
        {"a": "first", "b": "second"},
    )

    assert first.context_keys == ("a", "b")
    assert second.context_keys == ("a", "b")
    assert first.prompt == second.prompt


def test_callers_do_not_need_to_know_block_order_or_separators():
    result = PromptEngine().build(
        PromptType.FIRST_DECISION,
        {"user_input": "我有点乱，不知道先做什么"},
    )

    assert "我有点乱" in result.prompt
    assert "SystemPrompt" in result.prompt
    assert "OutputContract" in result.prompt


def test_redaction_still_removes_api_key_like_text():
    redacted = redact_prompt_text(
        "Authorization: Bearer sk-1234567890abcdef1234567890abcdef"
    )

    assert "[REDACTED]" in redacted
    assert "sk-1234567890abcdef" not in redacted


def test_prompt_frame_does_not_call_external_runtime_services():
    class ExplodingService:
        def __getattr__(self, name):
            raise AssertionError(f"external service was accessed: {name}")

    result = PromptEngine().build(
        PromptType.EXECUTION_DECISION,
        {
            "llm_provider": ExplodingService(),
            "tool_manager": ExplodingService(),
            "memory_manager": ExplodingService(),
        },
    )

    assert isinstance(result.prompt, str)
    assert "[UNSUPPORTED_OBJECT]" in result.prompt
