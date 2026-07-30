from dataclasses import dataclass, field

from events import RawSignal
from memory import MemoryManager
from providers.base import ProviderResult
from runtime.event_runtime import EventRuntime
from runtime.task_runtime import TaskRuntime
from runtime.timing import RuntimeTimingRecorder
from sessions.executor import CapabilityExecutor
from sessions.session_manager import TaskSessionManager
from sessions.subagent import SubAgent
from skill.manager import SkillManager
from tools.manager import ToolManager
from tools.mock_tools import MockWeatherTool
from agent.final_response import FinalResponseGenerator


@dataclass(slots=True)
class BoundaryLLMProvider:
    provider_name: str = "timing_llm"
    model_name: str = "timing-model"
    execution_calls: int = 0
    seen_boundaries: list[str] = field(default_factory=list)

    def generate(self, prompt, *, trace_id=None, metadata=None):
        boundary = (metadata or {}).get("boundary", "")
        self.seen_boundaries.append(boundary)
        if boundary == "task_formulation":
            output = {
                "goal": "Check local weather and answer the user.",
                "context_summary": "User asked for weather help.",
            }
        elif boundary == "strategy_selection":
            output = {"mode": "react", "reason": "Use one ReAct step."}
        elif boundary == "execution_decision":
            self.execution_calls += 1
            if self.execution_calls == 1:
                output = {
                    "action": "CALL_TOOL",
                    "tool_name": "mock_weather",
                    "arguments": {},
                    "reason": "Weather context is needed.",
                }
            else:
                output = {
                    "action": "COMPLETE",
                    "reason": "Weather observation is available.",
                }
        elif boundary == "final_response":
            output = {"text": "天气信息已整理。"}
        else:
            output = {"text": "ok"}
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=output,
        )


def test_runtime_timing_records_publish_queue_llm_tool_and_final_response(tmp_path):
    recorder = RuntimeTimingRecorder()
    llm_provider = BoundaryLLMProvider()
    skill_manager = SkillManager()
    tool_manager = ToolManager()
    tool_manager.register(MockWeatherTool())
    subagent = SubAgent(
        skill_manager=skill_manager,
        tool_directory=tool_manager,
        llm_provider=llm_provider,
        timing_recorder=recorder,
    )
    task_runtime = TaskRuntime(
        session_manager=TaskSessionManager(
            skill_manager=skill_manager,
            tool_manager=tool_manager,
            session_id_factory=lambda: "session-timing",
            task_id_factory=lambda: "task-timing",
        ),
        subagent=subagent,
        executor=CapabilityExecutor(
            skill_manager=skill_manager,
            tool_manager=tool_manager,
            timing_recorder=recorder,
        ),
        final_response_generator=FinalResponseGenerator(
            llm_provider=llm_provider,
            prompt_engine=subagent.prompt_engine,
            timing_recorder=recorder,
        ),
        memory_manager=MemoryManager(tmp_path / "memory.md"),
        timing_recorder=recorder,
    )
    event_runtime = EventRuntime(
        task_runtime=task_runtime,
        llm_provider=llm_provider,
        timing_recorder=recorder,
    )
    signal = RawSignal(
        trace_id="trace-timing",
        source="cli_input",
        payload={"text": "我有点迷茫，帮我看看天气"},
        signal_type="cli_text",
        metadata={"trigger_kind": "user_initiated"},
    )

    event_result = event_runtime.publish(signal)
    runtime_result = task_runtime.run_until_complete(
        event_result.task_handle.task_id,
        max_steps=10,
    )

    snapshot = runtime_result.timing
    assert snapshot is not None
    assert snapshot.trace_id == "trace-timing"
    assert snapshot.task_id == "task-timing"
    assert snapshot.session_id == "session-timing"
    assert snapshot.input_received_at is not None
    assert snapshot.task_submitted_at is not None
    assert snapshot.task_processing_started_at is not None
    assert snapshot.task_execution_started_at is not None
    assert snapshot.input_to_task_submitted_duration_ms is not None
    assert snapshot.task_formulation_duration_ms is not None
    assert snapshot.queue_wait_duration_ms is not None
    assert snapshot.planning_duration_ms is not None
    assert snapshot.final_response_generation_duration_ms is not None
    assert snapshot.total_execution_duration_ms is not None
    assert snapshot.end_to_end_duration_ms is not None
    assert snapshot.planning_duration_ms >= next(
        entry.duration_ms
        for entry in snapshot.llm_calls
        if entry.boundary == "strategy_selection"
    )
    assert snapshot.queue_wait_duration_ms >= 0
    assert {entry.boundary for entry in snapshot.llm_calls} >= {
        "task_formulation",
        "strategy_selection",
        "execution_decision",
        "final_response",
    }
    assert any(
        entry.tool_name == "mock_weather" and entry.success
        for entry in snapshot.tool_calls
    )
    timing_process = runtime_result.completion.user_visible_output.process["timing"]
    assert timing_process["total_llm_duration_ms"] >= 0
    assert timing_process["total_tool_duration_ms"] >= 0


def test_task_runtime_noop_timing_keeps_existing_flow_compatible():
    runtime = TaskRuntime()
    assert runtime.timing_recorder.snapshot("missing") is None
