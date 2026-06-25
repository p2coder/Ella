from prompts.engine import PromptEngine
from prompts.templates import (
    DECISION_POLICY_PROMPT,
    EXECUTION_DECISION_TEMPLATE,
    SKILL_POLICY_PROMPT,
    STRATEGY_SELECTION_TEMPLATE,
    TOOL_POLICY_PROMPT,
)


def test_skill_policy_treats_skill_as_guidance_not_engine():
    assert "guidance for behavior" in SKILL_POLICY_PROMPT
    assert "not an independent execution engine" in SKILL_POLICY_PROMPT
    assert "not a fixed execution plan" in SKILL_POLICY_PROMPT
    assert "continue without Skill" in SKILL_POLICY_PROMPT


def test_tool_policy_treats_tool_as_optional_capability():
    assert "optional capability" in TOOL_POLICY_PROMPT
    assert "not a mandatory step" in TOOL_POLICY_PROMPT
    assert "answer directly" in TOOL_POLICY_PROMPT
    assert "Tool failures are not successful facts" in TOOL_POLICY_PROMPT


def test_execution_decision_includes_skill_and_tool_policies():
    instruction = EXECUTION_DECISION_TEMPLATE.instruction

    assert SKILL_POLICY_PROMPT in instruction
    assert TOOL_POLICY_PROMPT in instruction
    assert DECISION_POLICY_PROMPT in instruction


def test_strategy_selection_does_not_select_skill_in_strategy_phase():
    instruction = STRATEGY_SELECTION_TEMPLATE.instruction

    assert "mode must be react or plan_and_execute" in instruction
    assert "Do not select a Skill in this phase" in instruction
    assert "Do not return skill_name" in instruction


def test_policy_prompts_do_not_list_concrete_skill_or_tool_names():
    combined = " ".join(
        (
            SKILL_POLICY_PROMPT,
            TOOL_POLICY_PROMPT,
            DECISION_POLICY_PROMPT,
            STRATEGY_SELECTION_TEMPLATE.instruction,
            EXECUTION_DECISION_TEMPLATE.instruction,
        )
    ).lower()

    for concrete_name in (
        "going_out",
        "mock_weather",
        "mock_checklist",
        "umbrella",
        "qwen",
    ):
        assert concrete_name not in combined


def test_prompt_engine_renders_policy_without_exposing_specific_capabilities():
    result = PromptEngine().build(
        "EXECUTION_DECISION",
        {
            "user_input": "你好",
            "workspace": {
                "available_skills": (),
                "available_tools": (),
                "observations": (),
            },
        },
    )

    assert "Tool is an optional capability" in result.prompt
    assert "Skill is guidance for behavior" in result.prompt
    assert "COMPLETE is valid" in result.prompt
    assert "going_out" not in result.prompt


def test_tool_failure_policy_is_visible_to_execution_prompt():
    result = PromptEngine().build(
        "EXECUTION_DECISION",
        {
            "workspace": {
                "observations": (
                    {
                        "tool_name": "example_tool",
                        "status": "failed",
                        "reason": "permission denied",
                    },
                )
            }
        },
    )

    assert "Tool failures are not successful facts" in result.prompt
    assert "Invalid parameters" in result.prompt
    assert "permission denied" in result.prompt
