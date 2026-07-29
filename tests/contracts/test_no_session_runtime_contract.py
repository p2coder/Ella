from dataclasses import fields
from pathlib import Path

from agent.subagent import SubAgent
from runtime.executor import CapabilityExecutor
from runtime.task_runtime import TaskRuntimeResult
from sessions.executor import CapabilityExecutor as LegacyExecutor
from sessions.session import Task as LegacyTask, TaskSession
from sessions.subagent import SubAgent as LegacySubAgent
from tasks.task import Task


def test_task_is_the_only_aggregate_and_has_no_session_state():
    task = Task("task-1")
    assert TaskSession is Task
    assert LegacyTask is Task
    assert not hasattr(task, "session_id")
    assert "session_id" not in {item.name for item in fields(Task)}


def test_compatibility_modules_are_identity_aliases_only():
    assert LegacyExecutor is CapabilityExecutor
    assert LegacySubAgent is SubAgent


def test_runtime_result_and_runtime_source_do_not_own_sessions():
    assert "task" in {item.name for item in fields(TaskRuntimeResult)}
    assert "session" not in {item.name for item in fields(TaskRuntimeResult)}
    source = Path("runtime/task_runtime.py").read_text(encoding="utf-8")
    assert "_sessions" not in source
    assert "TaskSession" not in source


def test_new_ownership_modules_do_not_import_session_implementations():
    for path in (
        Path("runtime/task_runtime.py"),
        Path("runtime/executor.py"),
        Path("runtime/step_runtime.py"),
        Path("agent/subagent.py"),
    ):
        source = path.read_text(encoding="utf-8")
        assert "from sessions.session" not in source
        assert "from sessions.executor" not in source
        assert "from sessions.subagent" not in source
