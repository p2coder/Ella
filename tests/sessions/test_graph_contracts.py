import pytest

from sessions.graph import (
    DynamicGraphCapacity,
    GraphEdge,
    TaskGraphDefinition,
    TaskGraphNodeDefinition,
    TaskGraphNodeType,
    ToolGraphDefinition,
    ToolNodeDefinition,
)


def task_node(node_id: str) -> TaskGraphNodeDefinition:
    return TaskGraphNodeDefinition(node_id, TaskGraphNodeType.STEP, {"goal": node_id})


def task_graph(*, edges=()) -> TaskGraphDefinition:
    return TaskGraphDefinition(
        graph_id="task-graph",
        version="v1",
        nodes=(task_node("start"), task_node("left"), task_node("right")),
        edges=tuple(edges),
        entry_node_ids=("start",),
        terminal_node_ids=("left", "right"),
    )


def test_edges_are_the_only_topology_source_and_helpers_are_deterministic():
    graph = task_graph(
        edges=(
            GraphEdge("start", "right", priority=2),
            GraphEdge("start", "left", priority=1),
        )
    )

    assert not hasattr(graph.nodes[0], "dependencies")
    assert graph.predecessors("left") == ("start",)
    assert graph.successors("start") == ("left", "right")
    assert graph.topological_order() == ("start", "left", "right")
    assert graph.stable_ready_order(("right", "left")) == ("left", "right")
    assert graph.reachable_terminals(("start",)) == ("left", "right")


@pytest.mark.parametrize(
    "nodes,edges,entries,terminals,message",
    [
        (
            (task_node("same"), task_node("same")),
            (),
            ("same",),
            ("same",),
            "unique",
        ),
        (
            (task_node("start"),),
            (GraphEdge("start", "missing"),),
            ("start",),
            ("start",),
            "unknown",
        ),
        (
            (task_node("a"), task_node("b")),
            (GraphEdge("a", "b"), GraphEdge("b", "a")),
            ("a",),
            ("b",),
            "acyclic",
        ),
    ],
)
def test_invalid_graphs_are_rejected(nodes, edges, entries, terminals, message):
    with pytest.raises(ValueError, match=message):
        TaskGraphDefinition("graph", "v1", nodes, edges, entries, terminals)


def test_condition_is_declarative_and_defensively_frozen():
    condition = {"field": "status", "equals": ["ready"]}
    edge = GraphEdge("a", "b", condition)
    condition["field"] = "changed"

    assert edge.condition["field"] == "status"
    assert edge.condition["equals"] == ("ready",)
    with pytest.raises(TypeError):
        edge.condition["field"] = "nope"
    with pytest.raises(TypeError, match="declarative"):
        GraphEdge("a", "b", lambda: True)


def test_tool_graph_uses_edges_and_immutable_node_data():
    first = ToolNodeDefinition("capture", "camera_scene", "v1", {"count": 1})
    second = ToolNodeDefinition("summarize", "vision", "v2", {})
    graph = ToolGraphDefinition(
        "tool-graph",
        (first, second),
        (GraphEdge("capture", "summarize"),),
        ("capture",),
        ("summarize",),
    )

    assert graph.predecessors("summarize") == ("capture",)
    assert not hasattr(first, "dependencies")
    with pytest.raises(TypeError):
        first.input_binding["count"] = 2


def test_dynamic_capacity_starts_at_five_and_doubles_within_budget():
    capacity = DynamicGraphCapacity.initial(12)
    assert capacity == DynamicGraphCapacity(5, 0, 12)

    for _ in range(6):
        capacity = capacity.consume()
    assert capacity == DynamicGraphCapacity(10, 6, 12)

    for _ in range(6):
        capacity = capacity.consume()
    assert capacity == DynamicGraphCapacity(12, 12, 12)
    with pytest.raises(ValueError, match="exhausted"):
        capacity.consume()


def test_dynamic_capacity_uses_budget_when_less_than_five():
    assert DynamicGraphCapacity.initial(3) == DynamicGraphCapacity(3, 0, 3)
