from dataclasses import FrozenInstanceError

import pytest

from sessions.execution_state import (
    StepExecutionState,
    ToolFailureKind,
    ToolFailureObservation,
)


def test_tool_failure_kinds_are_stable():
    assert tuple(kind.value for kind in ToolFailureKind) == (
        "invalid_arguments",
        "invalid_arguments_repair_violation",
        "permission_denied",
        "environment_unavailable",
        "tool_execution_failed",
    )


def test_failure_observation_is_immutable_and_serializable():
    source_arguments = {"location": "Shanghai"}
    failure = ToolFailureObservation(
        attempt_id="step1_try",
        tool_name="weather",
        kind=ToolFailureKind.INVALID_ARGUMENTS,
        code="invalid_tool_input",
        message="location is required",
        arguments=source_arguments,
        retryable=True,
    )
    source_arguments["location"] = "Beijing"

    assert failure.to_dict() == {
        "attempt_id": "step1_try",
        "tool_name": "weather",
        "kind": "invalid_arguments",
        "code": "invalid_tool_input",
        "message": "location is required",
        "arguments": {"location": "Shanghai"},
        "retryable": True,
    }
    with pytest.raises(TypeError):
        failure.arguments["location"] = "Shenzhen"
    with pytest.raises(FrozenInstanceError):
        failure.code = "changed"


@pytest.mark.parametrize(
    ("retry_index", "attempt_id"),
    ((0, "step1_try"), (1, "step1_retry1"), (2, "step1_retry2")),
)
def test_step_attempt_id_is_derived(retry_index, attempt_id):
    state = StepExecutionState(step_number=1, retry_index=retry_index)

    assert state.attempt_id == attempt_id


def test_step_state_normalizes_collections_without_sharing():
    blacklist = ["camera_scene"]
    failures = [
        ToolFailureObservation(
            attempt_id="step1_try",
            tool_name="camera_scene",
            kind=ToolFailureKind.PERMISSION_DENIED,
            code="permission_denied",
            message="camera permission denied",
            arguments={},
            retryable=False,
        )
    ]

    state = StepExecutionState(
        step_number=1,
        retry_index=0,
        active_tool_name="camera_scene",
        blacklisted_tools=blacklist,
        failures=failures,
    )
    blacklist.append("screen_scene")
    failures.clear()

    assert state.blacklisted_tools == ("camera_scene",)
    assert len(state.failures) == 1
    assert state.to_dict()["attempt_id"] == "step1_try"


def test_step_state_carries_retry_budget():
    state = StepExecutionState(max_argument_retries=4, retry_index=1)

    assert state.max_argument_retries == 4
    assert state.retries_remaining == 3
    assert state.to_dict()["max_argument_retries"] == 4


@pytest.mark.parametrize(
    ("step_number", "retry_index", "max_argument_retries"),
    ((0, 0, 2), (-1, 0, 2), (1, -1, 2), (1, 0, -1), (1, 3, 2)),
)
def test_invalid_step_numbers_and_retry_indexes_are_rejected(
    step_number,
    retry_index,
    max_argument_retries,
):
    with pytest.raises(ValueError):
        StepExecutionState(
            step_number=step_number,
            retry_index=retry_index,
            max_argument_retries=max_argument_retries,
        )
