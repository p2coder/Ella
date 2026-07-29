import pytest

from sessions.session import ALLOWED_TASK_STATE_TRANSITIONS, TaskState


def test_primary_lifecycle_transitions_exist():
    assert TaskState.FORMULATING in ALLOWED_TASK_STATE_TRANSITIONS[TaskState.CREATED]
    assert TaskState.READY in ALLOWED_TASK_STATE_TRANSITIONS[TaskState.FORMULATING]
    assert TaskState.RUNNING in ALLOWED_TASK_STATE_TRANSITIONS[TaskState.READY]
    assert TaskState.SUCCEEDED in ALLOWED_TASK_STATE_TRANSITIONS[TaskState.RUNNING]
    assert TaskState.DELIVERED in ALLOWED_TASK_STATE_TRANSITIONS[TaskState.SUCCEEDED]
    assert TaskState.DELIVERED in ALLOWED_TASK_STATE_TRANSITIONS[TaskState.FAILED]


@pytest.mark.parametrize(
    "origin",
    (
        TaskState.CREATED,
        TaskState.FORMULATING,
        TaskState.READY,
        TaskState.RUNNING,
        TaskState.WAITING,
    ),
)
def test_pause_is_requested_from_real_execution_stages(origin):
    assert TaskState.PAUSE_REQUESTED in ALLOWED_TASK_STATE_TRANSITIONS[origin]
    assert origin in ALLOWED_TASK_STATE_TRANSITIONS[TaskState.PAUSED]


def test_pause_requested_is_not_a_resume_target():
    assert TaskState.PAUSE_REQUESTED not in ALLOWED_TASK_STATE_TRANSITIONS[
        TaskState.PAUSED
    ]


def test_killed_and_delivered_are_terminal():
    assert ALLOWED_TASK_STATE_TRANSITIONS[TaskState.KILLED] == frozenset()
    assert ALLOWED_TASK_STATE_TRANSITIONS[TaskState.DELIVERED] == frozenset()


def test_uncertain_only_resolves_to_failed():
    assert ALLOWED_TASK_STATE_TRANSITIONS[TaskState.UNCERTAIN] == frozenset(
        {TaskState.FAILED}
    )


def test_legacy_states_remain_distinct_during_runtime_migration():
    assert TaskState.PLANNING is not TaskState.FORMULATING
    assert TaskState.REPLANNING is not TaskState.RUNNING
    assert TaskState.COMPLETED is not TaskState.SUCCEEDED
    assert TaskState.CANCELLED is not TaskState.KILLED
