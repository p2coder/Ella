from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent.handoff import HandoffRequest
from agent.final_response import FinalResponseResult
from events import StandardizedEvent
from memory import MemoryManagementRequest, MemoryWriteResult
from runtime.task_runtime import TaskRuntime
from sessions.completion import TaskCompletionPackage
from sessions.decision import COMPLETE, ExecutionDecision
from sessions.executor import CapabilityExecutionResult
from sessions.session_manager import TaskSessionManager
from sessions.strategy import StrategyDecision
from tools import ToolResult


def make_handoff() -> HandoffRequest:
    return HandoffRequest(
        task_goal="Give the user a short reminder before leaving.",
        trigger_event=StandardizedEvent(
            trace_id="trace-runtime-final-response",
            source="cli_input",
            timestamp=datetime(2026, 6, 13, 14, 0, tzinfo=timezone.utc),
            payload={"text": "Ella，我要出门了"},
            event_type="USER_UTTERANCE",
            metadata={"trigger_kind": "user_initiated"},
        ),
        user_preference_summary="Prefers concise reminders.",
        environment_summary="Mock environment only.",
        context_summary="User is preparing to leave.",
        constraints=("Keep the reminder short.",),
        completion_criteria=("A reminder is ready.",),
    )


def make_strategy() -> StrategyDecision:
    return StrategyDecision(
        mode="skill",
        skill_name="going_out",
        reason="Use the going-out capability.",
        initial_plan=None,
        completion_criteria=("A reminder is ready.",),
        session_id="session-runtime-final-response",
        task_id="task-runtime-final-response",
        trace_id="trace-runtime-final-response",
    )


def complete_decision() -> ExecutionDecision:
    return ExecutionDecision(
        action=COMPLETE,
        tool_name=None,
        tool_input=None,
        reason="The required going-out context has been collected.",
        is_complete=True,
    )


@dataclass
class RuntimeSkillManager:
    def refresh(self):
        return ()


@dataclass
class RuntimeToolManager:
    def list_names(self):
        return ()


@dataclass
class CompletingSubAgent:
    skill_manager: RuntimeSkillManager

    def select_strategy(self, handoff, context, task_session):
        return make_strategy()

    def decide_next_action(self, handoff, context, task_session, strategy):
        return complete_decision()


@dataclass
class CompletingExecutor:
    tool_manager: RuntimeToolManager
    calls: int = 0

    def execute(self, decision, strategy, context, task_session):
        self.calls += 1
        return CapabilityExecutionResult(
            decision=decision,
            strategy=strategy,
            tool_result=None,
            replan_required=False,
        )


@dataclass
class RecordingFinalResponseGenerator:
    final_response: str = "Final response from generator."
    calls: tuple[dict, ...] = ()

    def generate(self, **kwargs):
        self.calls += (kwargs,)
        return FinalResponseResult(
            final_response=self.final_response,
            tool_results_summary="camera_scene: phone is visible",
            prompt_trace={
                "trace_id": kwargs["trace_id"],
                "prompt_type": "FINAL_RESPONSE",
                "prompt_name": "final_response",
                "prompt_text": "prompt from generator",
                "provider_name": "recording_llm",
                "model_name": "recording-model",
                "llm_output": {"text": self.final_response},
            },
        )


@dataclass
class RecordingMemoryManager:
    memory_path: Path
    memory_content: str = ""
    requests: tuple[MemoryManagementRequest, ...] = ()

    def handle(self, request: MemoryManagementRequest) -> MemoryWriteResult:
        self.requests += (request,)
        return MemoryWriteResult(action="recorded", memory_path=self.memory_path)

    def query(self):
        return type(
            "MemoryQueryResult",
            (),
            {
                "action": "loaded_all",
                "memory_path": self.memory_path,
                "content": self.memory_content,
            },
        )()


def make_runtime(
    *,
    final_response_generator=None,
    memory_manager=None,
    executor=None,
):
    runtime = TaskRuntime(
        session_manager=TaskSessionManager(
            allowed_tools=("camera_scene",),
            session_id_factory=lambda: "session-runtime-final-response",
            task_id_factory=lambda: "task-runtime-final-response",
        ),
        subagent=CompletingSubAgent(RuntimeSkillManager()),
        executor=executor or CompletingExecutor(RuntimeToolManager()),
        memory_manager=memory_manager,
        final_response_generator=final_response_generator,
    )
    handle = runtime.submit(make_handoff())
    session = runtime.get_session(handle.task_id)
    session.tool_trace = (
        ToolResult(
            tool_name="camera_scene",
            task_id=handle.task_id,
            session_id=handle.session_id,
            trace_id=handle.trace_id,
            payload={
                "scene_summary": "Phone is visible on the desk.",
                "visible_items": ["phone", "keys"],
            },
        ).to_dict(),
    )
    return runtime, handle


def advance_to_running(runtime: TaskRuntime, task_id: str) -> None:
    runtime.step(task_id)
    runtime.step(task_id)


def test_completed_task_uses_final_response_generator():
    generator = RecordingFinalResponseGenerator("Remember your phone and keys.")
    runtime, handle = make_runtime(final_response_generator=generator)
    advance_to_running(runtime, handle.task_id)

    result = runtime.step(handle.task_id)

    assert result.completion is not None
    assert result.completion.user_visible_output.final_response == (
        "Remember your phone and keys."
    )
    assert len(generator.calls) == 1
    assert generator.calls[0]["trace_id"] == handle.trace_id
    assert generator.calls[0]["user_input"] == "Ella，我要出门了"
    assert generator.calls[0]["task_goal"] == (
        "Give the user a short reminder before leaving."
    )
    assert generator.calls[0]["task_constraints"] == ("Keep the reminder short.",)
    assert generator.calls[0]["completion_criteria"] == ("A reminder is ready.",)
    assert generator.calls[0]["user_preference_summary"] == (
        "Prefers concise reminders."
    )
    assert generator.calls[0]["environment_summary"] == "Mock environment only."
    assert generator.calls[0]["tool_results"][0].payload == {
        "scene_summary": "Phone is visible on the desk.",
        "visible_items": ["phone", "keys"],
    }


def test_final_response_uses_tool_results_and_preserves_process_data():
    generator = RecordingFinalResponseGenerator(
        "I can see your phone on the desk, so take it before leaving."
    )
    runtime, handle = make_runtime(final_response_generator=generator)
    advance_to_running(runtime, handle.task_id)

    completion = runtime.step(handle.task_id).completion

    assert completion is not None
    output = completion.user_visible_output
    assert "phone on the desk" in output.final_response
    assert output.final_response != (
        "Task completed: Give the user a short reminder before leaving."
    )
    assert output.process["task_goal"] == (
        "Give the user a short reminder before leaving."
    )
    assert output.process["strategy"] == "going_out"
    assert output.process["tool_results"] == ("camera_scene",)


def test_task_runtime_does_not_call_llm_or_build_prompt_directly():
    source = Path("runtime/task_runtime.py").read_text(encoding="utf-8")

    assert "PromptEngine" not in source
    assert "PromptType" not in source
    assert "LLMProvider" not in source
    assert "llm_provider" not in source
    assert "prompt_text" not in source


def test_task_runtime_still_creates_completion_package_and_memory_flow(tmp_path):
    generator = RecordingFinalResponseGenerator("Generated final response.")
    memory_manager = RecordingMemoryManager(tmp_path / "memory.md")
    runtime, handle = make_runtime(
        final_response_generator=generator,
        memory_manager=memory_manager,
    )

    result = runtime.run_until_complete(handle.task_id, max_steps=10)

    assert isinstance(result.completion, TaskCompletionPackage)
    assert result.completion is result.session.completion
    assert result.completion.user_visible_output.final_response == (
        "Generated final response."
    )
    assert len(memory_manager.requests) == 1
    assert memory_manager.requests[0].completion is result.completion


def test_task_runtime_passes_existing_memory_to_final_response_generator(
    tmp_path,
):
    generator = RecordingFinalResponseGenerator("Generated with memory.")
    memory_manager = RecordingMemoryManager(
        tmp_path / "memory.md",
        memory_content="## Task previous\n- final_response: Bring a thermos.\n",
    )
    runtime, handle = make_runtime(
        final_response_generator=generator,
        memory_manager=memory_manager,
    )
    advance_to_running(runtime, handle.task_id)

    runtime.step(handle.task_id)

    assert generator.calls[0]["memory_context"] == (
        "## Task previous\n- final_response: Bring a thermos.\n"
    )


def test_default_completion_fallback_is_compatible_without_old_template():
    runtime, handle = make_runtime(final_response_generator=None)
    advance_to_running(runtime, handle.task_id)

    completion = runtime.step(handle.task_id).completion

    assert completion is not None
    assert completion.user_visible_output.final_response
    assert not completion.user_visible_output.final_response.startswith(
        "Task completed:"
    )
