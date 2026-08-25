import pytest

from agent.decision import (
    CALL_TOOL,
    SUBMIT_RESULT,
    ExecutionDecision,
    SUPPORTED_EXECUTION_ACTIONS,
)


def test_action_protocol_contains_only_call_tool_and_submit_result() -> None:
    assert SUPPORTED_EXECUTION_ACTIONS == frozenset({CALL_TOOL, SUBMIT_RESULT})


def test_submit_result_is_a_candidate_not_a_tool_call() -> None:
    decision = ExecutionDecision(
        SUBMIT_RESULT,
        None,
        None,
        "Current evidence is sufficient for verification.",
        "Candidate result for the user.",
        (),
    )

    assert decision.is_submit_result is True
    assert decision.tool_name is None


def test_removed_complete_action_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        ExecutionDecision(
            "COMPLETE",
            None,
            None,
            "Legacy completion is no longer valid.",
            "Legacy result.",
            (),
        )
