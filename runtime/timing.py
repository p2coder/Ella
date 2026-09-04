from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _duration_ms(start: float, end: float | None = None) -> float:
    return round(((perf_counter() if end is None else end) - start) * 1000, 3)


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
    task_id: str
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
class _RuntimeTimingTask:
    task_id: str
    input_received_at: str | None = None
    task_submitted_at: str | None = None
    task_processing_started_at: str | None = None
    task_execution_started_at: str | None = None
    input_started_perf: float | None = None
    task_submitted_perf: float | None = None
    task_processing_started_perf: float | None = None
    execution_started_perf: float | None = None
    trigger_pipeline_duration_ms: float | None = None
    input_to_task_submitted_duration_ms: float | None = None
    queue_wait_duration_ms: float | None = None
    total_execution_duration_ms: float | None = None
    end_to_end_duration_ms: float | None = None
    final_response_generation_duration_ms: float | None = None
    llm_calls: list[LLMTimingEntry] = field(default_factory=list)
    tool_calls: list[ToolTimingEntry] = field(default_factory=list)

    def snapshot(self) -> RuntimeTimingSnapshot:
        values = {
            name: getattr(self, name)
            for name in RuntimeTimingSnapshot.__dataclass_fields__
            if name not in {"llm_calls", "tool_calls"}
        }
        return RuntimeTimingSnapshot(
            **values,
            llm_calls=tuple(self.llm_calls),
            tool_calls=tuple(self.tool_calls),
        )


@dataclass(slots=True)
class RuntimeTimingRecorder:
    _tasks: dict[str, _RuntimeTimingTask] = field(default_factory=dict)

    def _task(self, task_id: str) -> _RuntimeTimingTask:
        return self._tasks.setdefault(task_id, _RuntimeTimingTask(task_id))

    def start_input(self, task_id: str) -> float:
        timing = self._task(task_id)
        started = perf_counter()
        if timing.input_started_perf is None:
            timing.input_started_perf = started
            timing.input_received_at = _utc_now_iso()
        return started

    def record_stage_duration(self, task_id: str, field_name: str, started: float) -> None:
        if not field_name.endswith("_duration_ms"):
            raise ValueError("timing duration field must end with _duration_ms")
        setattr(self._task(task_id), field_name, _duration_ms(started))

    def record_task_submitted(self, task_id: str) -> None:
        timing = self._task(task_id)
        timing.task_submitted_at = _utc_now_iso()
        timing.task_submitted_perf = perf_counter()

    def record_input_to_task_submitted(self, task_id: str) -> None:
        timing = self._task(task_id)
        if timing.input_started_perf is not None:
            timing.input_to_task_submitted_duration_ms = _duration_ms(timing.input_started_perf)

    def record_task_processing_started(self, task_id: str) -> None:
        timing = self._task(task_id)
        if timing.task_processing_started_perf is not None:
            return
        started = perf_counter()
        timing.task_processing_started_perf = started
        timing.task_processing_started_at = _utc_now_iso()
        if timing.task_submitted_perf is not None:
            timing.queue_wait_duration_ms = _duration_ms(timing.task_submitted_perf, started)

    def record_execution_started(self, task_id: str) -> None:
        timing = self._task(task_id)
        if timing.execution_started_perf is None:
            timing.execution_started_perf = perf_counter()
            timing.task_execution_started_at = _utc_now_iso()

    def record_execution_completed(self, task_id: str) -> None:
        timing = self._task(task_id)
        if timing.execution_started_perf is not None:
            timing.total_execution_duration_ms = _duration_ms(timing.execution_started_perf)

    def record_task_completed(self, task_id: str) -> None:
        timing = self._task(task_id)
        if timing.input_started_perf is not None:
            timing.end_to_end_duration_ms = _duration_ms(timing.input_started_perf)

    def record_llm_call(self, task_id: str, **kwargs: Any) -> None:
        self._task(task_id).llm_calls.append(LLMTimingEntry(**kwargs))

    def record_tool_call(self, task_id: str, **kwargs: Any) -> None:
        self._task(task_id).tool_calls.append(ToolTimingEntry(**kwargs))

    def record_final_response_generation(self, task_id: str, duration_ms: float) -> None:
        self._task(task_id).final_response_generation_duration_ms = duration_ms

    def snapshot(self, task_id: str) -> RuntimeTimingSnapshot | None:
        timing = self._tasks.get(task_id)
        return None if timing is None else timing.snapshot()

    def snapshot_for_task(self, task_id: str) -> RuntimeTimingSnapshot | None:
        return self.snapshot(task_id)


class NoOpRuntimeTimingRecorder:
    def start_input(self, task_id: str) -> float:
        return perf_counter()

    def record_stage_duration(self, task_id: str, field_name: str, started: float) -> None:
        return None

    def record_task_submitted(self, task_id: str) -> None:
        return None

    def record_input_to_task_submitted(self, task_id: str) -> None:
        return None

    def record_task_processing_started(self, task_id: str) -> None:
        return None

    def record_execution_started(self, task_id: str) -> None:
        return None

    def record_execution_completed(self, task_id: str) -> None:
        return None

    def record_task_completed(self, task_id: str) -> None:
        return None

    def record_llm_call(self, task_id: str, **kwargs: Any) -> None:
        return None

    def record_tool_call(self, task_id: str, **kwargs: Any) -> None:
        return None

    def record_final_response_generation(self, task_id: str, duration_ms: float) -> None:
        return None

    def snapshot(self, task_id: str) -> None:
        return None

    def snapshot_for_task(self, task_id: str) -> None:
        return None
