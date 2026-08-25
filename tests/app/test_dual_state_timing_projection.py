from types import SimpleNamespace

from app_runtime import _timing_summary
from runtime.timing import LLMTimingEntry, RuntimeTimingSnapshot


def test_timing_projection_uses_current_decision_boundaries() -> None:
    timing = RuntimeTimingSnapshot(
        trace_id="trace-1",
        task_formulation_duration_ms=9.0,
        planning_duration_ms=12.0,
        llm_calls=(
            LLMTimingEntry("first_decision", 10.0, True),
            LLMTimingEntry("verification_decision", 4.0, True),
        ),
    )

    summary = _timing_summary(SimpleNamespace(timing=timing))

    assert "first_decision_stage: 12.0ms" in summary
    assert "llm:first_decision: 10.0ms" in summary
    assert "llm:verification_decision: 4.0ms" in summary
    assert "task_formulation" not in summary
    assert "planning:" not in summary
