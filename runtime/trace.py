from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from threading import Lock
from typing import Any, Mapping


_SECRET_KEY = re.compile(r"(?:api[_-]?key|authorization|token|secret|password)", re.I)
_ABSOLUTE_PATH = re.compile(r"(?:(?:[A-Za-z]:\\)|/Users/|/home/)[^\s;,]+")
_SAFE_TRACE_ID = re.compile(r"[^A-Za-z0-9._-]+")


def _redact(value: Any, key: str = "") -> Any:
    if _SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_redact(item) for item in value)
    if isinstance(value, bytes):
        return "[RAW_MEDIA_REDACTED]"
    if isinstance(value, str):
        return _ABSOLUTE_PATH.sub("[REDACTED_PATH]", value)
    return value


@dataclass(frozen=True, slots=True)
class TraceEvent:
    sequence: int
    task_id: str
    trace_id: str
    boundary: str
    event_type: str
    payload: Mapping[str, Any]
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "boundary": self.boundary,
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "recorded_at": self.recorded_at,
        }


@dataclass(frozen=True, slots=True)
class TaskGraphTrace:
    events: tuple[TraceEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskNodeTrace:
    events: tuple[TraceEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class ReasoningTrace:
    events: tuple[TraceEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class StepTrace:
    events: tuple[TraceEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolNodeTrace:
    events: tuple[TraceEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolAttemptTrace:
    events: tuple[TraceEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskTraceSnapshot:
    task_id: str
    trace_id: str
    events: tuple[TraceEvent, ...]
    task_graph: TaskGraphTrace
    task_nodes: TaskNodeTrace
    reasoning: ReasoningTrace
    steps: StepTrace
    tool_nodes: ToolNodeTrace
    tool_attempts: ToolAttemptTrace

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "events": tuple(event.to_dict() for event in self.events),
        }


@dataclass(slots=True)
class TraceRecorder:
    output_path: Path | None = None
    output_directory: Path | None = None
    _events: dict[str, list[TraceEvent]] = field(default_factory=dict)
    _sequence_offsets: dict[str, int] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def __post_init__(self) -> None:
        if self.output_path is not None and self.output_directory is not None:
            raise ValueError("configure output_path or output_directory, not both")

    @classmethod
    def for_directory(cls, directory: Path | str) -> "TraceRecorder":
        return cls(output_directory=Path(directory))

    def record(
        self,
        *,
        task_id: str,
        trace_id: str,
        boundary: str,
        event_type: str,
        payload: Mapping[str, Any] | None = None,
    ) -> TraceEvent:
        with self._lock:
            task_events = self._events.setdefault(task_id, [])
            output_path = self._path_for_task(task_id)
            if task_id not in self._sequence_offsets:
                self._sequence_offsets[task_id] = self._existing_event_count(
                    output_path,
                    task_id,
                )
            event = TraceEvent(
                sequence=self._sequence_offsets[task_id] + len(task_events) + 1,
                task_id=task_id,
                trace_id=trace_id,
                boundary=boundary,
                event_type=event_type,
                payload=_redact(dict(payload or {})),
                recorded_at=datetime.now(timezone.utc).isoformat(),
            )
            task_events.append(event)
            if output_path is not None:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with output_path.open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
                    )
                    stream.flush()
            return event

    def _path_for_task(self, task_id: str) -> Path | None:
        if self.output_path is not None:
            return self.output_path
        if self.output_directory is None:
            return None
        safe_task_id = _SAFE_TRACE_ID.sub("_", task_id).strip("._")
        if not safe_task_id:
            raise ValueError("task_id does not contain a safe trace file name")
        return self.output_directory / f"{safe_task_id}.jsonl"

    @staticmethod
    def _existing_event_count(path: Path | None, task_id: str) -> int:
        if path is None or not path.exists():
            return 0
        with path.open("r", encoding="utf-8") as stream:
            count = 0
            for line in stream:
                if not line.strip():
                    continue
                try:
                    document = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if document.get("task_id") == task_id:
                    count += 1
            return count

    def snapshot(self, task_id: str) -> TaskTraceSnapshot | None:
        events = tuple(self._events.get(task_id, ()))
        if not events:
            return None
        matching = lambda prefix: tuple(
            event for event in events if event.boundary.startswith(prefix)
        )
        return TaskTraceSnapshot(
            task_id,
            events[0].trace_id,
            events,
            TaskGraphTrace(matching("task_graph")),
            TaskNodeTrace(matching("task_node")),
            ReasoningTrace(matching("reasoning")),
            StepTrace(matching("step")),
            ToolNodeTrace(matching("tool_node")),
            ToolAttemptTrace(matching("tool_attempt")),
        )


class NoOpTraceRecorder:
    def record(self, **_: Any) -> None:
        return None

    def snapshot(self, task_id: str) -> None:
        return None
