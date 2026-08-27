from prompts.engine import PromptBuildResult, PromptEngine, PromptType, redact_prompt_text


def test_building_first_decision_prompt_returns_result():
    result = PromptEngine().build(
        PromptType.FIRST_DECISION,
        {
            "trace_id": "trace-prompt",
            "user_input": "Ella，我要出门了",
            "user_preference_summary": "Prefers concise reminders.",
            "environment_summary": "No visual context yet.",
            "event_type": "USER_UTTERANCE",
        },
    )

    assert isinstance(result, PromptBuildResult)
    assert result.prompt_type == PromptType.FIRST_DECISION
    assert result.prompt_name == "first_decision"
    assert isinstance(result.prompt, str)
    assert "Ella" in result.prompt
    assert "Ella，我要出门了" in result.prompt
    assert result.context_keys == (
        "environment_summary",
        "event_type",
        "trace_id",
        "user_input",
        "user_preference_summary",
    )


def test_context_values_change_prompt_without_changing_external_call_shape():
    engine = PromptEngine()

    first = engine.build(
        PromptType.FIRST_DECISION,
        {"user_input": "我要出门了", "environment_summary": "No visual context."},
    )
    second = engine.build(
        PromptType.FIRST_DECISION,
        {"user_input": "提醒我喝水", "environment_summary": "No visual context."},
    )

    assert first.prompt != second.prompt
    assert first.prompt_type == second.prompt_type
    assert first.prompt_name == second.prompt_name
    assert first.context_keys == second.context_keys


def test_unknown_prompt_type_raises_clear_error():
    try:
        PromptEngine().build("UNKNOWN", {"user_input": "hello"})
    except ValueError as error:
        assert "Unsupported prompt type" in str(error)
    else:
        raise AssertionError("Expected unsupported prompt type to raise ValueError")


def test_redaction_replaces_api_key_like_values():
    text = (
        "Authorization: Bearer sk-1234567890abcdef1234567890abcdef "
        "DASHSCOPE_API_KEY=abcdef1234567890abcdef1234567890"
    )

    redacted = redact_prompt_text(text)

    assert "sk-1234567890abcdef1234567890abcdef" not in redacted
    assert "abcdef1234567890abcdef1234567890" not in redacted
    assert "[REDACTED]" in redacted


def test_prompt_engine_does_not_call_external_runtime_services():
    class ExplodingService:
        def __getattr__(self, name):
            raise AssertionError(f"external service was accessed: {name}")

    context = {
        "user_input": "hello",
        "llm_provider": ExplodingService(),
        "camera": ExplodingService(),
        "memory_manager": ExplodingService(),
    }

    result = PromptEngine().build(PromptType.EXECUTION_DECISION, context)

    assert "llm_provider" in result.context_keys
    assert "[UNSUPPORTED_OBJECT]" in result.prompt


def test_system_prompt_is_not_going_out_specific():
    result = PromptEngine().build(
        PromptType.EXECUTION_DECISION,
        {"task_goal": "Summarize the user's request."},
    )

    assert "going_out" not in result.prompt
    assert "出门助手" not in result.prompt
