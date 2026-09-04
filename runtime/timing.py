from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration_ms(start: float, end: float | None = None) -> float:
    current = perf_counter() if end is None else end
    return round((current - start) * 1000, 3)


@dataclass(frozen=True, slots=True)
class LLMTimingEntry:
    boundary: str
    duration_ms: float
    success: bool
    provider_name: str | None = None
    model_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary": self.boundary,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
        }


@dataclass(frozen=True, slots=True)
class ToolTimingEntry:
    tool_name: str
    duration_ms: float
    success: bool
    failure_kind: str | None = None
    failure_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "failure_kind": self.failure_kind,
            "failure_code": self.failure_code,
        }


@dataclass(frozen=True, slots=True)
class RuntimeTimingSnapshot:
    trace_id: str
    task_id: str | None = None
    input_received_at: str | None = None
    task_submitted_at: str | None = None
    task_processing_started_at: str | None = None
    task_execution_started_at: str | None = None
    trigger_pipeline_duration_ms: float | None = None
    input_to_task_submitted_duration_ms: float | None = None
    queue_wait_duration_ms: float | None = None
    total_execution_duration_ms: float | None = None
    end_to_end_duration_ms: float | None = None
    final_response_generation_duration_ms: float | None = None
    llm_calls: tuple[LLMTimingEntry, ...] = ()
    tool_calls: tuple[ToolTimingEntry, ...] = ()

    @property
    def total_llm_duration_ms(self) -> float:
        return round(sum(entry.duration_ms for entry in self.llm_calls), 3)

    @property
    def total_tool_duration_ms(self) -> float:
        return round(sum(entry.duration_ms for entry in self.tool_calls), 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "input_received_at": self.input_received_at,
            "task_submitted_at": self.task_submitted_at,
            "task_processing_started_at": self.task_processing_started_at,
            "task_execution_started_at": self.task_execution_started_at,
            "trigger_pipeline_duration_ms": self.trigger_pipeline_duration_ms,
            "input_to_task_submitted_duration_ms": self.input_to_task_submitted_duration_ms,
            "queue_wait_duration_ms": self.queue_wait_duration_ms,
            "total_execution_duration_ms": self.total_execution_duration_ms,
            "end_to_end_duration_ms": self.end_to_end_duration_ms,
            "final_response_generation_duration_ms": self.final_response_generation_duration_ms,
            "total_llm_duration_ms": self.total_llm_duration_ms,
            "total_tool_duration_ms": self.total_tool_duration_ms,
            "llm_calls": tuple(entry.to_dict() for entry in self.llm_calls),
            "tool_calls": tuple(entry.to_dict() for entry in self.tool_calls),
        }


@dataclass(slots=True)
class _RuntimeTimingTrace:
    trace_id: str
    task_id: str | None = None
    input_received_at: str | None = None
    task_submitted_at: str | None = None
    task_processing_started_at: str | None = None
    task_execution_started_at: str | None = None
    input_started_perf: float | None = None
    task_submitted_perf: float | None = None
    task_processing_started_perf: float | None = None
    execution_started_perf: float | None = None
    execution_completed_perf: float | None = None
    trigger_pipeline_duration_ms: float | None = None
    input_to_task_submitted_duration_ms: float | None = None
    queue_wait_duration_ms: float | None = None
    total_execution_duration_ms: float | None = None
    end_to_end_duration_ms: float | None = None
    final_response_generation_duration_ms: float | None = None
    llm_calls: list[LLMTimingEntry] = field(default_factory=list)
    tool_calls: list[ToolTimingEntry] = field(default_factory=list)

    def snapshot(self) -> RuntimeTimingSnapshot:
        return RuntimeTimingSnapshot(
            trace_id=self.trace_id,
            task_id=self.task_id,
            input_received_at=self.input_received_at,
            task_submitted_at=self.task_submitted_at,
            task_processing_started_at=self.task_processing_started_at,
            task_execution_started_at=self.task_execution_started_at,
            trigger_pipeline_duration_ms=self.trigger_pipeline_duration_ms,
            input_to_task_submitted_duration_ms=self.input_to_task_submitted_duration_ms,
            queue_wait_duration_ms=self.queue_wait_duration_ms,
            total_execution_duration_ms=self.total_execution_duration_ms,
            end_to_end_duration_ms=self.end_to_end_duration_ms,
            final_response_generation_duration_ms=self.final_response_generation_duration_ms,
            llm_calls=tuple(self.llm_calls),
            tool_calls=tuple(self.tool_calls),
        )


@dataclass(slots=True)
class RuntimeTimingRecorder:
    _traces: dict[str, _RuntimeTimingTrace] = field(default_factory=dict)
    _task_to_trace: dict[str, str] = field(default_factory=dict)

    def start_input(self, trace_id: str) -> float:
        trace = self._trace(trace_id)
        started = perf_counter()
        if trace.input_started_perf is None:
            trace.input_started_perf = started
            trace.input_received_at = _utc_now_iso()
        return started

    def record_stage_duration(
        self,
        trace_id: str,
        field_name: str,
        started: float,
    ) -> None:
        if not field_name.endswith("_duration_ms"):
            raise ValueError("timing duration field must end with _duration_ms")
        setattr(self._trace(trace_id), field_name, _duration_ms(started))

    def record_task_submitted(
        self,
        trace_id: str,
        *,
        task_id: str,
    ) -> None:
        trace = self._trace(trace_id)
        submitted = perf_counter()
        trace.task_id = task_id
        trace.task_submitted_at = _utc_now_iso()
        trace.task_submitted_perf = submitted
        self._task_to_trace[task_id] = trace_id

    def record_input_to_task_submitted(self, trace_id: str) -> None:
        trace = self._trace(trace_id)
        if trace.input_started_perf is None:
            return
        trace.input_to_task_submitted_duration_ms = _duration_ms(
            trace.input_started_perf
        )

    def record_task_processing_started(self, trace_id: str) -> None:
        trace = self._trace(trace_id)
        if trace.task_processing_started_perf is not None:
            return
        started = perf_counter()
        trace.task_processing_started_perf = started
        trace.task_processing_started_at = _utc_now_iso()
        if trace.task_submitted_perf is not None:
            trace.queue_wait_duration_ms = _duration_ms(
                trace.task_submitted_perf,
                started,
            )

    def record_execution_started(self, trace_id: str) -> None:
        trace = self._trace(trace_id)
        if trace.execution_started_perf is not None:
            return
        started = perf_counter()
        trace.execution_started_perf = started
        trace.task_execution_started_at = _utc_now_iso()
        if trace.task_processing_started_perf is not None:
            trace.planning_duration_ms = _duration_ms(
                trace.task_processing_started_perf,
                started,
            )

    def record_execution_completed(self, trace_id: str) -> None:
        trace = self._trace(trace_id)
        if trace.execution_started_perf is None:
            return
        completed = perf_counter()
        trace.execution_completed_perf = completed
        trace.total_execution_duration_ms = _duration_ms(
            trace.execution_started_perf,
            completed,
        )

    def record_task_completed(self, trace_id: str) -> None:
        trace = self._trace(trace_id)
        if trace.input_started_perf is None:
            return
        trace.end_to_end_duration_ms = _duration_ms(trace.input_started_perf)

    def record_llm_call(
        self,
        trace_id: str,
        *,
        boundary: str,
        duration_ms: float,
        success: bool,
        provider_name: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self._trace(trace_id).llm_calls.append(
            LLMTimingEntry(
                boundary=boundary,
                duration_ms=duration_ms,
                success=success,
                provider_name=provider_name,
                model_name=model_name,
            )
        )

    def record_tool_call(
        self,
        trace_id: str,
        *,
        tool_name: str,
        duration_ms: float,
        success: bool,
        failure_kind: str | None = None,
        failure_code: str | None = None,
    ) -> None:
        self._trace(trace_id).tool_calls.append(
            ToolTimingEntry(
                tool_name=tool_name,
                duration_ms=duration_ms,
                success=success,
                failure_kind=failure_kind,
                failure_code=failure_code,
            )
        )

    def record_final_response_generation(
        self,
        trace_id: str,
        duration_ms: float,
    ) -> None:
        self._trace(trace_id).final_response_generation_duration_ms = duration_ms

    def snapshot(self, trace_id: str) -> RuntimeTimingSnapshot | None:
        trace = self._traces.get(trace_id)
        return None if trace is None else trace.snapshot()

    def snapshot_for_task(self, task_id: str) -> RuntimeTimingSnapshot | None:
        trace_id = self._task_to_trace.get(task_id)
        if trace_id is None:
            return None
        return self.snapshot(trace_id)

    def _trace(self, trace_id: str) -> _RuntimeTimingTrace:
        if trace_id not in self._traces:
            self._traces[trace_id] = _RuntimeTimingTrace(trace_id=trace_id)
        return self._traces[trace_id]


class NoOpRuntimeTimingRecorder:
    def start_input(self, trace_id: str) -> float:
        return perf_counter()

    def record_stage_duration(
        self,
        trace_id: str,
        field_name: str,
        started: float,
    ) -> None:
        return None

    def record_task_submitted(
        self,
        trace_id: str,
        *,
        task_id: str,
    ) -> None:
        return None

    def record_input_to_task_submitted(self, trace_id: str) -> None:
        return None

    def record_task_processing_started(self, trace_id: str) -> None:
        return None

    def record_execution_started(self, trace_id: str) -> None:
        return None

    def record_execution_completed(self, trace_id: str) -> None:
        return None

    def record_task_completed(self, trace_id: str) -> None:
        return None

    def record_llm_call(self, trace_id: str, **kwargs: Any) -> None:
        return None

    def record_tool_call(self, trace_id: str, **kwargs: Any) -> None:
        return None

    def record_final_response_generation(
        self,
        trace_id: str,
        duration_ms: float,
    ) -> None:
        return None

    def snapshot(self, trace_id: str) -> RuntimeTimingSnapshot | None:
        return None

    def snapshot_for_task(self, task_id: str) -> RuntimeTimingSnapshot | None:
        return None
