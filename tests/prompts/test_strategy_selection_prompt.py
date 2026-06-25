from prompts.engine import PromptEngine
from prompts.templates import STRATEGY_SELECTION_TEMPLATE


def test_strategy_selection_prompt_is_mode_only():
    instruction = STRATEGY_SELECTION_TEMPLATE.instruction

    assert "execution mode selection only" in instruction
    assert "mode must be react or plan_and_execute" in instruction
    assert "needs_decomposition" in instruction
    assert "plan_summary" in instruction


def test_strategy_selection_prompt_does_not_ask_for_skill_name():
    instruction = STRATEGY_SELECTION_TEMPLATE.instruction

    assert "Do not return skill_name" in instruction
    assert "Do not select a Skill in this phase" in instruction
    assert "visible skill name" not in instruction


def test_strategy_selection_prompt_forbids_tool_calls():
    instruction = STRATEGY_SELECTION_TEMPLATE.instruction

    assert "Do not call Tool" in instruction
    assert "Do not" in instruction
    assert "executable Tool calls" in instruction


def test_strategy_selection_builds_prompt_without_visible_skills():
    result = PromptEngine().build(
        "STRATEGY_SELECTION",
        {
            "task": {
                "goal": "Help the user understand the current problem.",
                "user_input": "我有点迷茫",
            }
        },
    )

    assert result.prompt_name == "strategy_selection"
    assert "Strategy" not in result.prompt
    assert "skill_name" in result.prompt
    assert "visible_skills" not in result.prompt
