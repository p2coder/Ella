import pytest

from runtime.task_runtime import TaskRuntime


def test_argument_retry_budget_must_be_non_negative():
    with pytest.raises(ValueError, match="max_argument_retries"):
        TaskRuntime(max_argument_retries=-1)


def test_default_argument_retry_budget_is_two():
    runtime = TaskRuntime()

    assert runtime.max_argument_retries == 2
