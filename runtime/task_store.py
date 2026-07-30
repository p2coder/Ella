from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import Enum
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping

from agent.context import AgentExecutionContext, CapabilityScope
from agent.handoff import HandoffRequest
from events import StandardizedEvent
from sessions.graph import (
    GraphEdge,
    TaskGraphDefinition,
    TaskGraphNodeDefinition,
    TaskGraphNodeType,
    TaskGraphRun,
)
from sessions.session import Task, TaskState


CHECKPOINT_SCHEMA_VERSION = 1
_FORBIDDEN_KEYS = frozenset(
    {"api_key", "authorization", "credentials", "prompt_text", "raw_media"}
)


class TaskStoreError(RuntimeError):
    pass


class TaskVersionConflict(TaskStoreError):
    pass


class CorruptTaskCheckpoint(TaskStoreError):
    pass


@dataclass(frozen=True, slots=True)
class StoredTask:
    task: Task
    version: int


class TaskStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def save(self, task: Task, *, expected_version: int | None = None) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        current = self.version(task.task_id)
        if expected_version is not None and current != expected_version:
            raise TaskVersionConflict(
                f"task {task.task_id} version is {current}, expected {expected_version}"
            )
        next_version = current + 1
        document = {
            "schema_version": CHECKPOINT_SCHEMA_VERSION,
            "version": next_version,
            "task": _encode_task(task),
        }
        payload = json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        path = self._path(task.task_id)
        try:
            with NamedTemporaryFile(
                mode="wb", dir=self.root, prefix=f".{task.task_id}.", delete=False
            ) as temporary:
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, path)
            _fsync_directory(self.root)
        except OSError as exc:
            try:
                temporary_path.unlink(missing_ok=True)
            except UnboundLocalError:
                pass
            raise TaskStoreError(f"checkpoint write failed: {exc}") from exc
        return next_version

    def load(self, task_id: str) -> StoredTask | None:
        path = self._path(task_id)
        if not path.exists():
            return None
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if document["schema_version"] != CHECKPOINT_SCHEMA_VERSION:
                raise ValueError("unsupported checkpoint schema")
            return StoredTask(
                task=_decode_task(document["task"]),
                version=int(document["version"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CorruptTaskCheckpoint(
                f"corrupt checkpoint for task {task_id}: {exc}"
            ) from exc

    def list(self) -> tuple[StoredTask, ...]:
        records = []
        for path in sorted(self.root.glob("*.json")) if self.root.exists() else ():
            record = self.load(path.stem)
            if record is not None:
                records.append(record)
        return tuple(records)

    def version(self, task_id: str) -> int:
        record = self.load(task_id)
        return 0 if record is None else record.version

    @staticmethod
    def recovery_classification(task: Task) -> str:
        if task.state in {TaskState.READY, TaskState.PAUSED, TaskState.WAITING}:
            return "restorable"
        if task.state in {
            TaskState.RUNNING,
            TaskState.PAUSE_REQUESTED,
            TaskState.KILL_REQUESTED,
        }:
            return "requires_recovery"
        if task.state is TaskState.UNCERTAIN:
            return "requires_resolution"
        if task.state in {TaskState.SUCCEEDED, TaskState.FAILED}:
            return "delivery_pending"
        if task.state in {TaskState.KILLED, TaskState.DELIVERED}:
            return "terminal"
        return "formulation_pending"

    def _path(self, task_id: str) -> Path:
        if not task_id or Path(task_id).name != task_id:
            raise ValueError("task_id must be a safe file name")
        return self.root / f"{task_id}.json"


def _encode_task(task: Task) -> dict[str, Any]:
    return _reject_secrets(
        {
            "task_id": task.task_id,
            "trace_id": task.trace_id,
            "source_event": _encode_event(task.source_event),
            "handoff": _encode_handoff(task.handoff),
            "execution_context": task.execution_context.to_dict()
            if task.execution_context
            else None,
            "state": task.state.value,
            "graph": _encode_graph(task.graph),
            "waiting_condition": _json_safe(task.waiting_condition),
            "paused_from_state": task.paused_from_state.value
            if task.paused_from_state
            else None,
            "terminal_outcome": _json_safe(task.terminal_outcome),
            "failure": _json_safe(task.failure),
            "uncertain_resolution": _json_safe(task.uncertain_resolution),
            "delivery": _json_safe(task.delivery),
            "control_request": _json_safe(task.control_request),
            "completion": _json_safe(task.completion),
            "task_local_state": _json_safe(task.task_local_state),
            "message_history": _json_safe(task.message_history),
            "tool_trace": _json_safe(task.tool_trace),
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }
    )


def _decode_task(data: Mapping[str, Any]) -> Task:
    event = _decode_event(data["source_event"])
    handoff = _decode_handoff(data.get("handoff"), event)
    context_data = data.get("execution_context")
    context = _decode_context(context_data) if context_data else None
    task = Task(
        session_id=data["task_id"],
        task_id=data["task_id"],
        handoff=handoff,
        trace_id=data["trace_id"],
        source_event=event,
        execution_context=context,
        graph=_decode_graph(data.get("graph")),
        state=TaskState(data["state"]),
        waiting_condition=data.get("waiting_condition"),
        paused_from_state=TaskState(data["paused_from_state"])
        if data.get("paused_from_state")
        else None,
        terminal_outcome=data.get("terminal_outcome"),
        failure=data.get("failure"),
        uncertain_resolution=data.get("uncertain_resolution"),
        delivery=data.get("delivery"),
        control_request=data.get("control_request"),
        completion=data.get("completion"),
        task_local_state=dict(data.get("task_local_state", {})),
        message_history=tuple(data.get("message_history", ())),
        tool_trace=tuple(data.get("tool_trace", ())),
        created_at=datetime.fromisoformat(data["created_at"]),
        updated_at=datetime.fromisoformat(data["updated_at"]),
    )
    return task


def _encode_event(event: StandardizedEvent | None) -> dict[str, Any] | None:
    if event is None:
        return None
    return {
        "trace_id": event.trace_id,
        "source": event.source,
        "payload": _json_safe(event.payload),
        "event_type": event.event_type,
        "timestamp": event.timestamp.isoformat(),
        "confidence": event.confidence,
        "priority": event.priority,
        "caused_by_task_id": event.caused_by_task_id,
        "metadata": _json_safe(event.metadata),
    }


def _decode_event(data: Mapping[str, Any] | None) -> StandardizedEvent:
    if data is None:
        raise ValueError("task checkpoint requires source_event")
    return StandardizedEvent(
        trace_id=data["trace_id"],
        source=data["source"],
        payload=dict(data["payload"]),
        event_type=data["event_type"],
        timestamp=datetime.fromisoformat(data["timestamp"]),
        confidence=data.get("confidence"),
        priority=data.get("priority"),
        caused_by_task_id=data.get("caused_by_task_id"),
        metadata=dict(data.get("metadata", {})),
    )


def _encode_handoff(handoff: HandoffRequest | None) -> dict[str, Any] | None:
    if handoff is None:
        return None
    data = handoff.to_dict()
    data.pop("trigger_event", None)
    data.pop("task_formulation_prompt_text", None)
    return _json_safe(data)


def _decode_handoff(
    data: Mapping[str, Any] | None, event: StandardizedEvent
) -> HandoffRequest | None:
    if data is None:
        return None
    return HandoffRequest(trigger_event=event, **data)


def _decode_context(data: Mapping[str, Any]) -> AgentExecutionContext:
    scope = data["capability_scope"]
    return AgentExecutionContext(
        agent_id=data["agent_id"],
        agent_role=data["agent_role"],
        parent_agent_id=data.get("parent_agent_id"),
        task_id=data["task_id"],
        trace_id=data["trace_id"],
        handoff_goal=data["handoff_goal"],
        memory_scope=data["memory_scope"],
        permissions=tuple(data.get("permissions", ())),
        capability_scope=CapabilityScope(
            agent_role=scope["agent_role"],
            allowed_skills=tuple(scope["allowed_skills"]),
            allowed_tools=tuple(scope["allowed_tools"]),
            skill_registry_version=scope.get("skill_registry_version"),
            tool_registry_version=scope.get("tool_registry_version"),
        ),
    )


def _encode_graph(run: TaskGraphRun | None) -> dict[str, Any] | None:
    if run is None:
        return None
    definition = run.definition
    return {
        "definition": {
            "graph_id": definition.graph_id,
            "version": definition.version,
            "nodes": [
                {"node_id": node.node_id, "node_type": node.node_type.value, "payload": _json_safe(node.payload)}
                for node in definition.nodes
            ],
            "edges": [
                {"from_node_id": edge.from_node_id, "to_node_id": edge.to_node_id, "condition": _json_safe(edge.condition), "priority": edge.priority}
                for edge in definition.edges
            ],
            "entry_node_ids": definition.entry_node_ids,
            "terminal_node_ids": definition.terminal_node_ids,
        },
        "node_runs": _json_safe(run.node_runs),
    }


def _decode_graph(data: Mapping[str, Any] | None) -> TaskGraphRun | None:
    if data is None:
        return None
    raw = data["definition"]
    definition = TaskGraphDefinition(
        graph_id=raw["graph_id"],
        version=raw["version"],
        nodes=tuple(TaskGraphNodeDefinition(node["node_id"], TaskGraphNodeType(node["node_type"]), node["payload"]) for node in raw["nodes"]),
        edges=tuple(GraphEdge(**edge) for edge in raw["edges"]),
        entry_node_ids=tuple(raw["entry_node_ids"]),
        terminal_node_ids=tuple(raw["terminal_node_ids"]),
    )
    return TaskGraphRun(definition, data["node_runs"])


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if is_dataclass(value):
        return _json_safe(asdict(value))
    raise TypeError(f"checkpoint cannot serialize runtime resource {type(value).__name__}")


def _reject_secrets(value: Any, path: str = "task") -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.lower()
            if any(forbidden in normalized for forbidden in _FORBIDDEN_KEYS):
                raise TaskStoreError(f"checkpoint contains forbidden field {path}.{key}")
            _reject_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_secrets(item, f"{path}[{index}]")
    return value


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
