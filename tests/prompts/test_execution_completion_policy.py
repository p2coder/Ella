from prompts.templates import EXECUTION_DECISION_TEMPLATE


def test_insufficient_observation_continues_when_information_is_obtainable():
    instruction = EXECUTION_DECISION_TEMPLATE.instruction

    assert (
        "If the missing information can still be obtained through a refined "
        "tool call, another visible tool, or user input, continue execution."
        in instruction
    )
    assert (
        "Do not choose COMPLETE if a visible tool can still reasonably obtain "
        "information required to satisfy the user's request."
        in instruction
    )


def test_completion_policy_prevents_identical_calls_but_not_refined_research():
    instruction = EXECUTION_DECISION_TEMPLATE.instruction

    assert "materially identical arguments" in instruction
    assert (
        "If an observation is insufficient, choose COMPLETE"
        not in instruction
    )
