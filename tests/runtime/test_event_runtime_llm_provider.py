from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from agent.main_agent import MainAgent
from events import RawSignal, StandardizedEvent
from events.trigger_pipeline import EventTriggerPipeline, PipelineStage
from providers.base import ProviderResult
from runtime.event_runtime import EventRuntime
from runtime.task_runtime import TaskHandle


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = datetime(2026, 6, 13, 16, 0, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class SignalToEventStage(PipelineStage):
    def process(self, signal: RawSignal) -> StandardizedEvent:
        return StandardizedEvent(
            trace_id=signal.trace_id,
            source=signal.source,
            timestamp=signal.timestamp,
            payload=signal.payload,
            event_type="USER_UTTERANCE",
            metadata={"trigger_kind": "user_initiated"},
        )


@dataclass
class RecordingTaskRuntime:
    submitted_handoffs: list = field(default_factory=list)

    def submit(self, handoff):
        self.submitted_handoffs.append(handoff)
        return TaskHandle("task-llm", "session-llm", handoff.trigger_event.trace_id)


class StructuredLLMProvider:
    provider_name = "injected_llm"
    model_name = "injected-model"

    def generate(self, prompt, *, trace_id=None, metadata=None):
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output={
                "goal": "Give the user an injected reminder before leaving.",
                "context_summary": "The injected provider formulated this task.",
            },
        )


def test_main_agent_receives_llm_provider_by_injection():
    provider = StructuredLLMProvider()

    agent = MainAgent(llm_provider=provider)

    assert agent.llm_provider is provider
    assert agent.formulator.llm_provider is provider


def test_event_runtime_injects_provider_into_main_agent_and_formulation():
    provider = StructuredLLMProvider()
    task_runtime = RecordingTaskRuntime()
    runtime = EventRuntime(
        trigger_pipeline=EventTriggerPipeline(stages=(SignalToEventStage(),)),
        task_runtime=task_runtime,
        llm_provider=provider,
    )

    result = runtime.publish(
        RawSignal(
            trace_id="trace-llm-runtime",
            source="test",
            timestamp=FIXED_TIME,
            payload={"text": "Ella，我要出门了"},
        )
    )

    assert result.submitted is True
    assert runtime.llm_provider is provider
    assert runtime.main_agent.formulator.llm_provider is provider
    assert task_runtime.submitted_handoffs[0].task_goal == (
        "Give the user an injected reminder before leaving."
    )


def test_agent_and_runtime_do_not_import_qwen_directly():
    for relative_path in ("agent/main_agent.py", "runtime/event_runtime.py"):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "providers.qwen" not in source
