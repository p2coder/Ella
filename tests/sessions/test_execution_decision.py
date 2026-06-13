import pytest

from sessions.decision import ExecutionDecision


def test_valid_call_tool_decision():
    decision = ExecutionDecision(
        action="CALL_TOOL",
        tool_name="mock_weather",
        tool_input={"location": "current"},
        reason="Weather context is needed before preparing the reminder.",
        is_complete=False,
    )

    assert decision.action == "CALL_TOOL"
    assert decision.tool_name == "mock_weather"
    assert decision.tool_input == {"location": "current"}
    assert decision.is_complete is False


def test_call_tool_without_tool_name_raises_clear_error():
    with pytest.raises(
        ValueError,
        match="CALL_TOOL execution decision requires tool_name",
    ):
        ExecutionDecision(
            action="CALL_TOOL",
            tool_name=None,
            tool_input=None,
            reason="A tool is needed.",
            is_complete=False,
        )


def test_complete_with_tool_name_raises_clear_error():
    with pytest.raises(
        ValueError,
        match="COMPLETE execution decision must not include tool_name",
    ):
        ExecutionDecision(
            action="COMPLETE",
            tool_name="mock_checklist",
            tool_input=None,
            reason="The task is complete.",
            is_complete=True,
        )


def test_complete_requires_is_complete_true():
    with pytest.raises(
        ValueError,
        match="COMPLETE execution decision requires is_complete=True",
    ):
        ExecutionDecision(
            action="COMPLETE",
            tool_name=None,
            tool_input=None,
            reason="The task is complete.",
            is_complete=False,
        )


@pytest.mark.parametrize("action", ("WAIT", "REPLAN"))
def test_non_tool_actions_are_valid_without_tool_name(action):
    decision = ExecutionDecision(
        action=action,
        tool_name=None,
        tool_input=None,
        reason="The task cannot continue with the current information.",
        is_complete=False,
    )

    assert decision.action == action
    assert decision.tool_name is None


def test_invalid_action_raises_clear_error():
    with pytest.raises(
        ValueError,
        match="unsupported execution decision action: UNKNOWN",
    ):
        ExecutionDecision(
            action="UNKNOWN",
            tool_name=None,
            tool_input=None,
            reason="Invalid decision.",
            is_complete=False,
        )


def test_execution_decision_serializes_to_dict():
    decision = ExecutionDecision(
        action="CALL_TOOL",
        tool_name="mock_checklist",
        tool_input={"category": "going_out"},
        reason="A checklist is needed.",
        is_complete=False,
    )

    assert decision.to_dict() == {
        "action": "CALL_TOOL",
        "tool_name": "mock_checklist",
        "tool_input": {"category": "going_out"},
        "reason": "A checklist is needed.",
        "is_complete": False,
    }
