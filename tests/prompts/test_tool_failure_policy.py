from prompts.templates import EXECUTION_DECISION_TEMPLATE, TOOL_POLICY_PROMPT


def test_tool_policy_separates_successful_results_from_failures():
    policy = TOOL_POLICY_PROMPT

    assert "ToolResult" in policy
    assert "ToolFailureObservation" in policy
    assert "must not be treated as successful facts" in policy


def test_repair_policy_binds_the_active_tool():
    instruction = EXECUTION_DECISION_TEMPLATE.instruction

    assert "active_tool_name" in instruction
    assert "same Tool" in instruction
    assert "blacklisted_tools" in instruction
    assert "must not switch" in instruction


def test_non_retryable_failures_are_not_blindly_retried():
    instruction = EXECUTION_DECISION_TEMPLATE.instruction

    assert "permission" in instruction
    assert "environment" in instruction
    assert "internal" in instruction
    assert "do not retry" in instruction
