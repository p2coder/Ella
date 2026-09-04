from dataclasses import dataclass, field, replace
from copy import deepcopy
from datetime import datetime, timezone
from time import monotonic, sleep
from typing import Any, Callable
from uuid import uuid4

from agent.context import AgentExecutionContext
from agent.decision import SUBMIT_RESULT
from runtime.provider_usage import aggregate_provider_usage
from tasks.task import Task, TaskState


@dataclass(frozen=True, slots=True)
class ChildAgentRun:
    child_agent_id: str
    status: str
    final_response: str | None
    observations: tuple[dict[str, Any], ...]
    error: str | None
    provider_usage: dict[str, object] | None
    completed_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "child_agent_id": self.child_agent_id,
            "status": self.status,
            "final_response": self.final_response,
            "observations": self.observations,
            "error": self.error,
            "provider_usage": self.provider_usage,
            "completed_at": self.completed_at,
        }


@dataclass(frozen=True, slots=True)
class ChildAgentRunner:
    decision_agent: Any
    executor: Any
    task_reader: Callable[[str], Task]
    child_agent_id_factory: Callable[[], str] = field(
        default=lambda: f"agent-{uuid4().hex}", repr=False, compare=False
    )
    max_depth: int = 4
    max_advances: int = 50
    max_timeout_seconds: float = 300.0

    def run(
        self,
        parent_context: AgentExecutionContext,
        *,
        prompt: str,
        timeout_seconds: float,
        fork: bool = False,
    ) -> ChildAgentRun:
        if parent_context.agent_depth >= self.max_depth:
            raise ValueError("subagent depth limit exceeded")
        if not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        if timeout_seconds <= 0 or timeout_seconds > self.max_timeout_seconds:
            raise ValueError(
                f"timeout_seconds must be in (0, {self.max_timeout_seconds:g}]"
            )

        child_id = self.child_agent_id_factory()
        context = replace(
            parent_context,
            agent_id=child_id,
            parent_agent_id=parent_context.agent_id,
            agent_depth=parent_context.agent_depth + 1,
            handoff_goal=prompt,
        )
        local = self._initial_task(parent_context, prompt, fork=fork)
        inherited_observation_count = len(local.tool_trace)
        local.execution_context = context
        started = monotonic()
        try:
            first = self.decision_agent.decide_first_action(context, local)
            local.intent = first.intent
            local.first_decision_completed = True
            decision = first.action
            for advance in range(self.max_advances):
                control_error = self._control_error(
                    parent_context.task_id, started, timeout_seconds
                )
                if control_error is not None:
                    status, error = control_error
                    return self._result(
                        local,
                        child_id,
                        status,
                        None,
                        error,
                        inherited_observation_count,
                    )
                if advance:
                    decision = self.decision_agent.decide_next_action(
                        None, context, local
                    )
                if decision.action == SUBMIT_RESULT:
                    return self._result(
                        local,
                        child_id,
                        "completed",
                        decision.final_response_draft,
                        None,
                        inherited_observation_count,
                    )
                local.state = TaskState.TOOL_EXECUTION
                execution = self.executor.execute(decision, context, local)
                local.state = TaskState.REASONING
                if execution.uncertain:
                    error = (
                        "uncertain child tool outcome"
                        if execution.failure is None
                        else execution.failure.message
                    )
                    return self._result(
                        local,
                        child_id,
                        "uncertain",
                        None,
                        error,
                        inherited_observation_count,
                    )
                if execution.failure is not None:
                    local.current_step = replace(
                        local.current_step,
                        failures=(*local.current_step.failures, execution.failure),
                    )
                    continue
                observation = execution.tool_result.to_dict()
                observation["observation_id"] = (
                    f"{local.task_id}:{child_id}:observation:"
                    f"{len(local.tool_trace) + 1}"
                )
                local.tool_trace += (observation,)
            return self._result(
                local,
                child_id,
                "failed",
                None,
                "child advance budget exhausted",
                inherited_observation_count,
            )
        except Exception as error:
            return self._result(
                local,
                child_id,
                "failed",
                None,
                str(error),
                inherited_observation_count,
            )

    def _initial_task(
        self,
        parent_context: AgentExecutionContext,
        prompt: str,
        *,
        fork: bool,
    ) -> Task:
        if not fork:
            return Task(
                task_id=parent_context.task_id,
                state=TaskState.REASONING,
                task_local_state={"latest_user_input": prompt},
            )
        parent = self.task_reader(parent_context.task_id)
        inherited_context = {
            "intent": None if parent.intent is None else parent.intent.to_dict(),
            "original_input": parent.task_local_state.get("latest_user_input"),
            "message_history": deepcopy(parent.message_history),
            "observations": deepcopy(parent.tool_trace),
            "current_step": {
                "step_number": parent.current_step.step_number,
                "retry_index": parent.current_step.retry_index,
                "active_tool_name": parent.current_step.active_tool_name,
                "blacklisted_tools": parent.current_step.blacklisted_tools,
                "failures": tuple(
                    failure.to_dict() for failure in parent.current_step.failures
                ),
            },
            "task_local_state": deepcopy(parent.task_local_state),
        }
        return Task(
            task_id=parent_context.task_id,
            state=TaskState.REASONING,
            intent=deepcopy(parent.intent),
            first_decision_completed=False,
            task_local_state={
                "latest_user_input": prompt,
                "inherited_context": inherited_context,
            },
            message_history=deepcopy(parent.message_history),
            tool_trace=deepcopy(parent.tool_trace),
            current_step=deepcopy(parent.current_step),
        )

    def _control_error(
        self, task_id: str, started: float, timeout_seconds: float
    ) -> tuple[str, str] | None:
        if monotonic() - started >= timeout_seconds:
            return "timed_out", "child execution timed out"
        task = self.task_reader(task_id)
        while task.state in {TaskState.PAUSE_REQUESTED, TaskState.PAUSED}:
            if monotonic() - started >= timeout_seconds:
                return "timed_out", "child execution timed out while paused"
            sleep(0.01)
            task = self.task_reader(task_id)
        if task.state in {TaskState.KILL_REQUESTED, TaskState.KILLED}:
            return "failed", "parent task was killed"
        return None

    @staticmethod
    def _result(
        task: Task,
        child_agent_id: str,
        status: str,
        final_response: str | None,
        error: str | None,
        inherited_observation_count: int,
    ) -> ChildAgentRun:
        calls = task.task_local_state.get("provider_usage_calls", ())
        return ChildAgentRun(
            child_agent_id=child_agent_id,
            status=status,
            final_response=final_response,
            observations=tuple(task.tool_trace[inherited_observation_count:]),
            error=error,
            provider_usage=aggregate_provider_usage(calls),
            completed_at=datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
        )
