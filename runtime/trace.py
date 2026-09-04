from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from threading import Lock
from typing import Any, Mapping


_SECRET_KEY = re.compile(r"(?:api[_-]?key|authorization|token|secret|password)", re.I)
_ABSOLUTE_PATH = re.compile(r"(?:(?:[A-Za-z]:\\)|/Users/|/home/)[^\s;,]+")
_SAFE_TASK_ID = re.compile(r"[^A-Za-z0-9._-]+")


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
    boundary: str
    event_type: str
    payload: Mapping[str, Any]
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "task_id": self.task_id,
            "boundary": self.boundary,
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "recorded_at": self.recorded_at,
        }


@dataclass(frozen=True, slots=True)
class TaskTraceSnapshot:
    task_id: str
    events: tuple[TraceEvent, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
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
        boundary: str,
        event_type: str,
        payload: Mapping[str, Any] | None = None,
    ) -> TraceEvent:
        with self._lock:
            task_events = self._events.setdefault(task_id, [])
            output_path = self._path_for_task(task_id)
            if task_id not in self._sequence_offsets:
                self._sequence_offsets[task_id] = self._existing_event_count(
                    output_path, task_id
                )
            event = TraceEvent(
                sequence=self._sequence_offsets[task_id] + len(task_events) + 1,
                task_id=task_id,
                boundary=boundary,
                event_type=event_type,
                payload=_redact(dict(payload or {})),
                recorded_at=datetime.now(timezone.utc).isoformat(),
            )
            task_events.append(event)
            if output_path is not None:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with output_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            return event

    def _path_for_task(self, task_id: str) -> Path | None:
        if self.output_path is not None:
            return self.output_path
        if self.output_directory is None:
            return None
        safe_task_id = _SAFE_TASK_ID.sub("_", task_id).strip("._")
        if not safe_task_id:
            raise ValueError("task_id does not contain a safe trace file name")
        return self.output_directory / f"{safe_task_id}.jsonl"

    @staticmethod
    def _existing_event_count(path: Path | None, task_id: str) -> int:
        return len(TraceRecorder._read_events(path, task_id))

    def snapshot(self, task_id: str) -> TaskTraceSnapshot | None:
        with self._lock:
            persisted = self._read_events(self._path_for_task(task_id), task_id)
            in_memory = tuple(self._events.get(task_id, ()))
        by_sequence = {event.sequence: event for event in persisted}
        by_sequence.update({event.sequence: event for event in in_memory})
        events = tuple(by_sequence[key] for key in sorted(by_sequence))
        return None if not events else TaskTraceSnapshot(task_id, events)

    @staticmethod
    def _read_events(path: Path | None, task_id: str) -> tuple[TraceEvent, ...]:
        if path is None or not path.exists():
            return ()
        events = []
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    document = json.loads(line)
                    if document.get("task_id") != task_id:
                        continue
                    events.append(
                        TraceEvent(
                            sequence=int(document["sequence"]),
                            task_id=str(document["task_id"]),
                            boundary=str(document["boundary"]),
                            event_type=str(document["event_type"]),
                            payload=dict(document.get("payload", {})),
                            recorded_at=str(document["recorded_at"]),
                        )
                    )
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    continue
        return tuple(events)


class NoOpTraceRecorder:
    def record(self, **_: Any) -> None:
        return None

    def snapshot(self, task_id: str) -> None:
        return None
