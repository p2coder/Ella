from datetime import datetime, timezone

from agent.context import AgentExecutionContext, CapabilityScope
from events import StandardizedEvent
from runtime.task_runtime import TaskRuntime
from tasks.state import TaskControlCommand, TaskControlType
from tasks.task import Task, TaskState
from tasks.factory import TaskCreationResult


def runtime(state=TaskState.REASONING):
    event = StandardizedEvent("trace-control", "test", {}, "USER_UTTERANCE", metadata={})
    context = AgentExecutionContext("agent", "main_agent", None, "task-control", "trace-control", "", "task_local", capability_scope=CapabilityScope("main_agent", (), ()))
    task = Task(task_id="task-control", trace_id="trace-control", source_event=event, execution_context=context, state=state)
    rt = TaskRuntime(); rt._tasks[task.task_id] = TaskCreationResult(task)
    return rt, task


def command(kind, command_id="command-1"):
    return TaskControlCommand(command_id, "task-control", kind, datetime.now(timezone.utc), "user")


def test_pause_records_real_origin_and_resume_returns_to_interrupted_stage():
    rt, task = runtime(TaskState.REASONING)
    requested = rt.apply_control(command(TaskControlType.PAUSE))
    assert requested.current_state == "pause_requested"
    assert task.paused_from_state is TaskState.REASONING
    assert rt._reach_control_safe_point(task) is True
    assert task.state is TaskState.PAUSED
    resumed = rt.apply_control(command(TaskControlType.RESUME, "command-2"))
    assert resumed.current_state == "reasoning"
    assert task.paused_from_state is None


def test_control_commands_are_idempotent_and_kill_has_priority():
    rt, task = runtime(TaskState.READY)
    first = rt.apply_control(command(TaskControlType.PAUSE))
    repeated = rt.apply_control(command(TaskControlType.PAUSE))
    assert repeated == first
    killed = rt.apply_control(command(TaskControlType.KILL, "kill"))
    assert killed.current_state == "killed"
    assert rt.apply_control(command(TaskControlType.RESUME, "resume")).accepted is False


def test_pause_cannot_be_requested_twice():
    rt, task = runtime(TaskState.PAUSED)

    result = rt.apply_control(command(TaskControlType.PAUSE))

    assert result.accepted is False
    assert result.current_state == "paused"


def test_kill_is_rejected_for_succeeded_uncertain_and_pause_requested():
    for state in (
        TaskState.SUCCEEDED,
        TaskState.UNCERTAIN,
        TaskState.PAUSE_REQUESTED,
    ):
        rt, task = runtime(state)

        result = rt.apply_control(command(TaskControlType.KILL))

        assert result.accepted is False
        assert task.state is state
