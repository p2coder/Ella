from prompts.engine import PromptEngine, PromptType
from prompts.templates import ELLA_SYSTEM_PROMPT, TEMPLATES_BY_TYPE


def test_system_prompt_contains_companionship_guidance():
    assert "companion-style assistant" in ELLA_SYSTEM_PROMPT
    assert "emotion" in ELLA_SYSTEM_PROMPT
    assert "ambiguity" in ELLA_SYSTEM_PROMPT
    assert "naturally" in ELLA_SYSTEM_PROMPT


def test_system_prompt_contains_task_execution_guidance():
    assert "task execution assistant" in ELLA_SYSTEM_PROMPT
    assert "real goal" in ELLA_SYSTEM_PROMPT
    assert "decomposition" in ELLA_SYSTEM_PROMPT
    assert "use Skill and Tool only when helpful" in ELLA_SYSTEM_PROMPT


def test_system_prompt_contains_truthfulness_and_safety_limits():
    assert "Never fabricate" in ELLA_SYSTEM_PROMPT
    assert "Never claim" in ELLA_SYSTEM_PROMPT
    assert "State uncertainty" in ELLA_SYSTEM_PROMPT
    assert "Do not expose API keys" in ELLA_SYSTEM_PROMPT


def test_system_prompt_is_not_scenario_specific():
    forbidden_terms = (
        "going_out",
        "出门助手",
        "camera_scene",
        "mock_weather",
        "mock_checklist",
        "umbrella",
        "Qwen",
    )

    for term in forbidden_terms:
        assert term not in ELLA_SYSTEM_PROMPT


def test_system_prompt_does_not_include_credentials_or_paths():
    forbidden_terms = (
        "DASHSCOPE_API_KEY",
        "QWEN_API_KEY",
        "Authorization",
        "/Users/",
        "Bearer ",
    )

    for term in forbidden_terms:
        assert term not in ELLA_SYSTEM_PROMPT


def test_prompt_engine_output_includes_system_prompt_for_all_prompt_types():
    engine = PromptEngine()

    for prompt_type in TEMPLATES_BY_TYPE:
        result = engine.build(prompt_type, {"user_input": "hello"})
        assert "companion-style assistant" in result.prompt
        assert "task execution assistant" in result.prompt


def test_prompt_type_instructions_remain_separate_from_system_prompt():
    strategy = PromptEngine().build(
        PromptType.STRATEGY_SELECTION,
        {"overall_goal": "answer a question"},
    )
    execution = PromptEngine().build(
        PromptType.EXECUTION_DECISION,
        {"overall_goal": "answer a question"},
    )

    assert "strict JSON" in strategy.prompt
    assert "CALL_TOOL" in execution.prompt
    assert strategy.prompt != execution.prompt
