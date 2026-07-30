from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Iterable, Mapping


class TaskGraphNodeType(StrEnum):
    REASONING = "reasoning"
    STEP = "step"


def _require_name(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class GraphEdge:
    from_node_id: str
    to_node_id: str
    condition: Mapping[str, Any] | None = None
    priority: int = 0

    def __post_init__(self) -> None:
        _require_name("from_node_id", self.from_node_id)
        _require_name("to_node_id", self.to_node_id)
        if self.from_node_id == self.to_node_id:
            raise ValueError("graph edge cannot reference the same node")
        if not isinstance(self.priority, int):
            raise TypeError("priority must be an integer")
        if self.condition is not None:
            if not isinstance(self.condition, Mapping):
                raise TypeError("condition must be declarative mapping data")
            object.__setattr__(self, "condition", _freeze(self.condition))


@dataclass(frozen=True, slots=True)
class TaskGraphNodeDefinition:
    node_id: str
    node_type: TaskGraphNodeType
    payload: Any

    def __post_init__(self) -> None:
        _require_name("node_id", self.node_id)
        if not isinstance(self.node_type, TaskGraphNodeType):
            raise TypeError("node_type must be a TaskGraphNodeType")
        object.__setattr__(self, "payload", _freeze(self.payload))


@dataclass(frozen=True, slots=True)
class ToolNodeDefinition:
    node_id: str
    tool_name: str
    tool_version: str
    input_binding: Mapping[str, Any]
    success_condition: Mapping[str, Any] | None = None
    execution_override: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for field_name in ("node_id", "tool_name", "tool_version"):
            _require_name(field_name, getattr(self, field_name))
        if not isinstance(self.input_binding, Mapping):
            raise TypeError("input_binding must be a mapping")
        object.__setattr__(self, "input_binding", _freeze(self.input_binding))
        for field_name in ("success_condition", "execution_override"):
            value = getattr(self, field_name)
            if value is not None:
                if not isinstance(value, Mapping):
                    raise TypeError(f"{field_name} must be a mapping")
                object.__setattr__(self, field_name, _freeze(value))


class _GraphDefinition:
    nodes: tuple[Any, ...]
    edges: tuple[GraphEdge, ...]
    entry_node_ids: tuple[str, ...]
    terminal_node_ids: tuple[str, ...]

    def _validate_graph(self) -> None:
        node_ids = tuple(node.node_id for node in self.nodes)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("graph node IDs must be unique")
        if not node_ids:
            raise ValueError("graph must contain at least one node")
        known = frozenset(node_ids)
        for edge in self.edges:
            if edge.from_node_id not in known or edge.to_node_id not in known:
                raise ValueError("graph edge references an unknown node")
        for field_name, values in (
            ("entry_node_ids", self.entry_node_ids),
            ("terminal_node_ids", self.terminal_node_ids),
        ):
            if not values:
                raise ValueError(f"{field_name} must not be empty")
            if len(values) != len(set(values)) or not set(values) <= known:
                raise ValueError(f"{field_name} must contain unique known nodes")
        self.topological_order()

    def predecessors(self, node_id: str) -> tuple[str, ...]:
        self._require_node(node_id)
        return tuple(
            edge.from_node_id
            for edge in self._sorted_edges()
            if edge.to_node_id == node_id
        )

    def successors(self, node_id: str) -> tuple[str, ...]:
        self._require_node(node_id)
        return tuple(
            edge.to_node_id
            for edge in self._sorted_edges()
            if edge.from_node_id == node_id
        )

    def topological_order(self) -> tuple[str, ...]:
        node_ids = tuple(node.node_id for node in self.nodes)
        indegree = {node_id: 0 for node_id in node_ids}
        successors: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
        for edge in self.edges:
            if edge.from_node_id not in indegree or edge.to_node_id not in indegree:
                raise ValueError("graph edge references an unknown node")
            indegree[edge.to_node_id] += 1
            successors[edge.from_node_id].append(edge.to_node_id)
        ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
        ordered: list[str] = []
        while ready:
            node_id = ready.pop(0)
            ordered.append(node_id)
            for successor in sorted(successors[node_id]):
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    ready.append(successor)
                    ready.sort()
        if len(ordered) != len(node_ids):
            raise ValueError("graph must be acyclic")
        return tuple(ordered)

    def reachable_terminals(
        self, start_node_ids: Iterable[str]
    ) -> tuple[str, ...]:
        pending = list(dict.fromkeys(start_node_ids))
        for node_id in pending:
            self._require_node(node_id)
        visited: set[str] = set()
        while pending:
            node_id = pending.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)
            pending.extend(self.successors(node_id))
        return tuple(
            node_id for node_id in self.terminal_node_ids if node_id in visited
        )

    def stable_ready_order(self, node_ids: Iterable[str]) -> tuple[str, ...]:
        candidates = tuple(dict.fromkeys(node_ids))
        for node_id in candidates:
            self._require_node(node_id)
        topology = {node_id: index for index, node_id in enumerate(self.topological_order())}
        incoming_priority = {
            node_id: min(
                (
                    edge.priority
                    for edge in self.edges
                    if edge.to_node_id == node_id
                ),
                default=0,
            )
            for node_id in candidates
        }
        return tuple(
            sorted(
                candidates,
                key=lambda node_id: (
                    incoming_priority[node_id],
                    topology[node_id],
                    node_id,
                ),
            )
        )

    def _require_node(self, node_id: str) -> None:
        if node_id not in {node.node_id for node in self.nodes}:
            raise KeyError(node_id)

    def _sorted_edges(self) -> tuple[GraphEdge, ...]:
        return tuple(
            sorted(
                self.edges,
                key=lambda edge: (
                    edge.priority,
                    edge.from_node_id,
                    edge.to_node_id,
                ),
            )
        )


@dataclass(frozen=True, slots=True)
class TaskGraphDefinition(_GraphDefinition):
    graph_id: str
    version: str
    nodes: tuple[TaskGraphNodeDefinition, ...]
    edges: tuple[GraphEdge, ...]
    entry_node_ids: tuple[str, ...]
    terminal_node_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_name("graph_id", self.graph_id)
        _require_name("version", self.version)
        for field_name in ("nodes", "edges", "entry_node_ids", "terminal_node_ids"):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        self._validate_graph()


@dataclass(frozen=True, slots=True)
class ToolGraphDefinition(_GraphDefinition):
    graph_id: str
    nodes: tuple[ToolNodeDefinition, ...]
    edges: tuple[GraphEdge, ...]
    entry_node_ids: tuple[str, ...]
    terminal_node_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_name("graph_id", self.graph_id)
        for field_name in ("nodes", "edges", "entry_node_ids", "terminal_node_ids"):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))
        self._validate_graph()


@dataclass(frozen=True, slots=True)
class TaskGraphRun:
    definition: TaskGraphDefinition
    node_runs: Mapping[str, Any]

    def __post_init__(self) -> None:
        if set(self.node_runs) - {node.node_id for node in self.definition.nodes}:
            raise ValueError("node_runs contains unknown task graph nodes")
        object.__setattr__(self, "node_runs", _freeze(self.node_runs))


@dataclass(frozen=True, slots=True)
class ToolGraphRun:
    definition: ToolGraphDefinition
    node_runs: Mapping[str, Any]

    def __post_init__(self) -> None:
        if set(self.node_runs) - {node.node_id for node in self.definition.nodes}:
            raise ValueError("node_runs contains unknown tool graph nodes")
        object.__setattr__(self, "node_runs", _freeze(self.node_runs))


@dataclass(frozen=True, slots=True)
class DynamicGraphCapacity:
    allocated_slots: int
    used_slots: int
    max_slots: int

    def __post_init__(self) -> None:
        if self.max_slots < 1:
            raise ValueError("max_slots must be positive")
        if not 0 <= self.used_slots <= self.allocated_slots <= self.max_slots:
            raise ValueError("dynamic graph capacity values are inconsistent")

    @classmethod
    def initial(cls, max_steps: int) -> DynamicGraphCapacity:
        if max_steps < 1:
            raise ValueError("max_steps must be positive")
        return cls(min(5, max_steps), 0, max_steps)

    def consume(self) -> DynamicGraphCapacity:
        capacity = self
        if capacity.used_slots == capacity.allocated_slots:
            if capacity.allocated_slots == capacity.max_slots:
                raise ValueError("dynamic graph capacity is exhausted")
            capacity = DynamicGraphCapacity(
                min(capacity.allocated_slots * 2, capacity.max_slots),
                capacity.used_slots,
                capacity.max_slots,
            )
        return DynamicGraphCapacity(
            capacity.allocated_slots,
            capacity.used_slots + 1,
            capacity.max_slots,
        )
