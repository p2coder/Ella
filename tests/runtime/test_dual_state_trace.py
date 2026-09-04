from agent.subagent import SubAgent
from runtime.executor import CapabilityExecutor
from runtime.task_runtime import TaskRuntime
from runtime.trace import TraceRecorder
from skill.manager import SkillManager
from tasks.factory import TaskFactory
from tools.manager import ToolManager

from tests.runtime.test_first_decision_flow import FirstDecisionProvider, _event


def test_submit_result_completes_without_implicit_verification(tmp_path) -> None:
    recorder = TraceRecorder.for_directory(tmp_path)
    tool_manager = ToolManager()
    subagent = SubAgent(
        skill_manager=SkillManager(),
        tool_directory=tool_manager,
        llm_provider=FirstDecisionProvider(),
    )
    runtime = TaskRuntime(
        task_factory=TaskFactory(
            task_id_factory=lambda: "task-trace",
            tool_manager=tool_manager,
        ),
        subagent=subagent,
        executor=CapabilityExecutor(
            subagent=subagent,
            skill_manager=SkillManager(),
            tool_manager=tool_manager,
        ),
        trace_recorder=recorder,
    )
    handle = runtime.create_task(_event())

    runtime.step(handle.task_id)
    result = runtime.step(handle.task_id)

    assert result.stop_reason == "completed"
    assert result.completion is not None
    snapshot = recorder.snapshot(handle.task_id)
    assert snapshot is not None
    markers = {(event.boundary, event.event_type) for event in snapshot.events}
    assert ("reasoning.first_decision", "started") in markers
    assert ("reasoning.first_decision", "intent_committed") in markers
    assert ("reasoning.first_decision", "completed") in markers
    assert ("reasoning.submit_result", "completed") in markers
    assert not any(boundary == "reasoning.verification" for boundary, _ in markers)
    assert ("task", "completed") in markers
    assert ("checkpoint", "persisted") in markers
