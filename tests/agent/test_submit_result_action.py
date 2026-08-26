import pytest

from agent.decision import (
    CALL_TOOL,
    SUBMIT_RESULT,
    ExecutionDecision,
    SUPPORTED_EXECUTION_ACTIONS,
)
from agent.subagent import SubAgent


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
        "Here is the completed result for you.",
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


def test_submit_result_requires_complete_user_facing_draft() -> None:
    with pytest.raises(ValueError, match="final_response_draft"):
        ExecutionDecision(
            SUBMIT_RESULT,
            None,
            None,
            "The task is ready to submit.",
            "Internal completion summary.",
            (),
        )


def test_submit_result_does_not_fail_when_explanatory_reason_is_missing() -> None:
    decision = SubAgent._decision_from_payload(
        {
            "action": "SUBMIT_RESULT",
            "completion_summary": "The requested report is ready.",
            "final_response_draft": "The requested report is ready.",
            "evidence_refs": [],
        },
        (),
        (),
    )

    assert decision.action == SUBMIT_RESULT
    assert decision.completion_summary == "The requested report is ready."
    assert decision.final_response_draft == "The requested report is ready."
    assert decision.decision_reason == "Model selected SUBMIT_RESULT."


def test_reason_alias_is_normalized_for_submit_result() -> None:
    decision = SubAgent._decision_from_payload(
        {
            "action": "SUBMIT_RESULT",
            "reason": "The evidence is sufficient.",
            "completion_summary": "The requested report is ready.",
            "final_response_draft": "The requested report is ready.",
            "evidence_refs": [],
        },
        (),
        (),
    )

    assert decision.decision_reason == "The evidence is sufficient."
