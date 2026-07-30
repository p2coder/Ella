from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Mapping

from agent.context import AgentExecutionContext
from runtime.executor import CapabilityExecutionResult, CapabilityExecutor
from tasks.graph import ToolGraphRun, ToolNodeDefinition
from tasks.task import Task
from agent.strategy import StrategyDecision
from tools.base import EffectiveToolExecutionMetadata
from tools.manager import CapabilityUnavailableError


class ToolNodeRunState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ToolNodeRun:
    node_id: str
    state: ToolNodeRunState = ToolNodeRunState.PENDING
    attempts: tuple[Mapping[str, Any], ...] = ()
    effective_metadata: EffectiveToolExecutionMetadata | None = None
    result: Any | None = None
    failure: Any | None = None


@dataclass(frozen=True, slots=True)
class StepTickResult:
    graph_run: ToolGraphRun
    selected_node_id: str | None
    execution_result: CapabilityExecutionResult | None
    step_state: str


@dataclass(frozen=True, slots=True)
class StepRuntime:
    executor: CapabilityExecutor
    max_tool_attempts_per_tool_node: int = 1

    def tick(
        self,
        graph_run: ToolGraphRun,
        *,
        task: Task,
        context: AgentExecutionContext,
        strategy: StrategyDecision,
        availability: Mapping[str, str] | None = None,
    ) -> StepTickResult:
        runs = {
            node.node_id: _coerce_run(node.node_id, graph_run.node_runs.get(node.node_id))
            for node in graph_run.definition.nodes
        }
        ready = self._ready_nodes(graph_run, runs, availability or {})
        if not ready:
            return StepTickResult(graph_run, None, None, self._step_state(graph_run, runs))
        node = ready[0]
        current = runs[node.node_id]
        if len(current.attempts) >= self.max_tool_attempts_per_tool_node:
            runs[node.node_id] = replace(current, state=ToolNodeRunState.FAILED)
            updated = ToolGraphRun(graph_run.definition, runs)
            return StepTickResult(updated, node.node_id, None, self._step_state(updated, runs))
        try:
            metadata = self.executor.tool_manager.resolve_execution_metadata(
                node.tool_name,
                node.tool_version,
                dict(node.execution_override or {}),
            )
        except (CapabilityUnavailableError, ValueError) as exc:
            runs[node.node_id] = replace(
                current,
                state=ToolNodeRunState.FAILED,
                failure={"code": "tool_metadata_invalid", "message": str(exc)},
            )
            updated = ToolGraphRun(graph_run.definition, runs)
            return StepTickResult(updated, node.node_id, None, self._step_state(updated, runs))

        arguments = dict(node.input_binding)
        execution = self.executor.execute_tool_node(
            tool_name=node.tool_name,
            arguments=arguments,
            strategy=strategy,
            context=context,
            task=task,
        )
        attempt = {
            "attempt_index": len(current.attempts) + 1,
            "arguments": arguments,
            "success": execution.tool_result is not None,
        }
        state = (
            ToolNodeRunState.SUCCEEDED
            if execution.tool_result is not None
            else ToolNodeRunState.FAILED
        )
        runs[node.node_id] = ToolNodeRun(
            node.node_id,
            state,
            current.attempts + (attempt,),
            metadata,
            execution.tool_result,
            execution.failure,
        )
        if node.node_id in graph_run.definition.terminal_node_ids and state is ToolNodeRunState.SUCCEEDED:
            for candidate_id, candidate in tuple(runs.items()):
                if candidate.state is ToolNodeRunState.PENDING:
                    runs[candidate_id] = replace(candidate, state=ToolNodeRunState.SKIPPED)
        updated = ToolGraphRun(graph_run.definition, runs)
        return StepTickResult(updated, node.node_id, execution, self._step_state(updated, runs))

    def _ready_nodes(self, graph_run, runs, availability):
        candidates = []
        for node in graph_run.definition.nodes:
            run = runs[node.node_id]
            if run.state is not ToolNodeRunState.PENDING:
                continue
            if availability.get(node.tool_name, "available") != "available":
                continue
            predecessors = graph_run.definition.predecessors(node.node_id)
            if all(runs[item].state is ToolNodeRunState.SUCCEEDED for item in predecessors):
                candidates.append(node.node_id)
        ordered = graph_run.definition.stable_ready_order(candidates)
        by_id = {node.node_id: node for node in graph_run.definition.nodes}
        return tuple(by_id[node_id] for node_id in ordered)

    @staticmethod
    def _step_state(graph_run, runs) -> str:
        terminal_states = [runs[node_id].state for node_id in graph_run.definition.terminal_node_ids]
        if ToolNodeRunState.SUCCEEDED in terminal_states:
            return "succeeded"
        if ToolNodeRunState.UNCERTAIN in terminal_states:
            return "uncertain"
        if terminal_states and all(state in {ToolNodeRunState.FAILED, ToolNodeRunState.SKIPPED} for state in terminal_states):
            return "failed"
        return "running"


def _coerce_run(node_id: str, value: Any) -> ToolNodeRun:
    if isinstance(value, ToolNodeRun):
        return value
    if isinstance(value, Mapping):
        return ToolNodeRun(
            node_id,
            ToolNodeRunState(value.get("state", "pending")),
            tuple(value.get("attempts", ())),
        )
    return ToolNodeRun(node_id)
