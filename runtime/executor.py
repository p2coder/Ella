from dataclasses import dataclass, field, replace
from concurrent.futures import Future
from datetime import datetime, timezone
from threading import RLock
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from agent.context import AgentExecutionContext
from agent.decision import CALL_TOOL, ExecutionDecision
from runtime.timing import NoOpRuntimeTimingRecorder, RuntimeTimingRecorder
from skill import SkillManager
from tasks.state import ToolFailureKind, ToolFailureObservation
from tasks.task import Task
from tools import ToolManager, ToolResult
from tools.base import ToolUncertainPolicy


@dataclass(frozen=True, slots=True)
class CapabilityExecutionResult:
    decision: ExecutionDecision
    tool_result: ToolResult | None = None
    failure: ToolFailureObservation | None = None
    raw_result: Any | None = field(default=None, repr=False, compare=False)
    uncertain: bool = False

    def __post_init__(self) -> None:
        if self.tool_result is not None and self.failure is not None:
            raise ValueError("tool_result and failure are mutually exclusive")


@dataclass(frozen=True, slots=True)
class ToolUseRecord:
    tool_use_id: str
    task_id: str
    agent_id: str
    tool_name: str
    arguments: dict[str, Any]

    @property
    def tool_results(self) -> tuple[ToolResult, ...]:
        return () if self.tool_result is None else (self.tool_result,)

    @property
    def failure_reason(self) -> str | None:
        return None if self.failure is None else self.failure.message


@dataclass(frozen=True, slots=True)
class CapabilityExecutor:
    """Validate and execute exactly one model-selected capability action."""

    skill_manager: SkillManager
    tool_manager: ToolManager
    subagent: Any | None = None
    timing_recorder: RuntimeTimingRecorder | NoOpRuntimeTimingRecorder = field(
        default_factory=NoOpRuntimeTimingRecorder
    )
    clock: Callable[[], datetime] = field(
        default=lambda: datetime.now(timezone.utc), repr=False, compare=False
    )
    tool_use_id_factory: Callable[[], str] = field(
        default=lambda: f"tool-use-{uuid4().hex}", repr=False, compare=False
    )
    _tool_uses: dict[str, ToolUseRecord] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _refreshes: dict[str, Future[CapabilityExecutionResult]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _tool_use_lock: RLock = field(
        default_factory=RLock, init=False, repr=False, compare=False
    )

    def execute(
        self,
        decision: ExecutionDecision,
        context: AgentExecutionContext,
        task: Task,
    ) -> CapabilityExecutionResult:
        if decision.action != CALL_TOOL:
            return CapabilityExecutionResult(decision)
        tool_name = decision.tool_name
        if tool_name is None:
            raise ValueError("CALL_TOOL requires tool_name")
        if tool_name not in context.capability_scope.allowed_tools:
            return self._failure(
                decision, task, ToolFailureKind.PERMISSION_DENIED,
                "tool_not_allowed", f"tool {tool_name} is not allowed",
            )
        tool = self.tool_manager.get_tool(tool_name)
        if tool is None:
            return self._failure(
                decision, task, ToolFailureKind.ENVIRONMENT_UNAVAILABLE,
                "tool_not_registered", f"tool {tool_name} is not registered",
            )
        if context.agent_role not in tool.allowed_roles:
            return self._failure(
                decision, task, ToolFailureKind.PERMISSION_DENIED,
                "tool_role_not_allowed",
                f"tool {tool_name} is not visible to role {context.agent_role}",
            )

        arguments = decision.tool_input or {}
        input_error = _validate_schema(
            arguments,
            _tool_schema(tool, "input_schema"),
            path="arguments",
        )
        if input_error is not None:
            return self._failure(
                decision, task, ToolFailureKind.INVALID_ARGUMENTS,
                "invalid_tool_input", f"invalid_tool_input: {input_error}",
                retryable=True,
            )

        if tool_name == "refresh":
            return self._execute_refresh(decision, context, task, arguments)

        tool_use_id = self.tool_use_id_factory()
        tool_use_record = ToolUseRecord(
            tool_use_id=tool_use_id,
            task_id=context.task_id,
            agent_id=context.agent_id,
            tool_name=tool_name,
            arguments=dict(arguments),
        )
        called_at = _utc_timestamp(self.clock())
        started = perf_counter()
        try:
            result = tool.run(context=context, arguments=arguments)
        except ValueError as error:
            completed_at = _utc_timestamp(self.clock())
            self._record_timing(context, tool_name, started, False, "invalid_tool_input")
            outcome = self._failure(
                decision, task, ToolFailureKind.INVALID_ARGUMENTS,
                "invalid_tool_input", f"invalid_tool_input: {error}",
                retryable=True,
                tool_use_id=tool_use_id,
                context=context,
                called_at=called_at,
                completed_at=completed_at,
                result_ttl_seconds=tool.definition.result_ttl_seconds,
            )
            self._remember_tool_use(tool_use_record)
            return outcome
        except Exception as error:
            completed_at = _utc_timestamp(self.clock())
            uncertain = _may_have_unconfirmed_side_effect(tool)
            code = (
                "uncertain_tool_outcome"
                if uncertain
                else str(getattr(error, "code", "tool_execution_failed"))
            )
            self._record_timing(context, tool_name, started, False, code)
            failure = self._failure(
                decision,
                task,
                ToolFailureKind.TOOL_EXECUTION_FAILED,
                code,
                str(error) or f"tool {tool_name} execution failed",
                tool_use_id=tool_use_id,
                context=context,
                called_at=called_at,
                completed_at=completed_at,
                result_ttl_seconds=tool.definition.result_ttl_seconds,
            )
            outcome = CapabilityExecutionResult(
                decision=decision,
                failure=failure.failure,
                uncertain=uncertain,
            )
            self._remember_tool_use(tool_use_record)
            return outcome

        completed_at = _utc_timestamp(self.clock())
        result = replace(
            result,
            tool_use_id=tool_use_id,
            agent_id=context.agent_id,
            parent_agent_id=context.parent_agent_id,
            arguments=dict(arguments),
            called_at=called_at,
            completed_at=completed_at,
            result_ttl_seconds=tool.definition.result_ttl_seconds,
        )
        output_error = _validate_schema(
            result.payload,
            _tool_schema(tool, "output_schema"),
            path="payload",
        )
        if output_error is not None:
            self._record_timing(context, tool_name, started, False, "invalid_tool_output")
            outcome = self._failure(
                decision, task, ToolFailureKind.TOOL_EXECUTION_FAILED,
                "invalid_tool_output", f"invalid_tool_output: {output_error}",
                raw_result=result,
                tool_use_id=tool_use_id,
                context=context,
                called_at=called_at,
                completed_at=completed_at,
                result_ttl_seconds=tool.definition.result_ttl_seconds,
            )
            self._remember_tool_use(tool_use_record)
            return outcome
        self._record_timing(context, tool_name, started, True, None)
        self._remember_tool_use(tool_use_record)
        return CapabilityExecutionResult(decision, tool_result=result)

    def _execute_refresh(
        self,
        decision: ExecutionDecision,
        context: AgentExecutionContext,
        task: Task,
        arguments: dict[str, Any],
    ) -> CapabilityExecutionResult:
        source_id = str(arguments["tool_use_id"])
        with self._tool_use_lock:
            source = self._tool_uses.get(source_id)
        if source is None:
            return self._failure(
                decision,
                task,
                ToolFailureKind.INVALID_ARGUMENTS,
                "refresh_source_not_found",
                f"tool use {source_id} is not available for refresh",
            )
        if source.task_id != context.task_id or source.agent_id != context.agent_id:
            return self._failure(
                decision,
                task,
                ToolFailureKind.PERMISSION_DENIED,
                "refresh_source_not_visible",
                f"tool use {source_id} is not visible to this agent",
            )
        if source.tool_name == "refresh":
            return self._failure(
                decision,
                task,
                ToolFailureKind.INVALID_ARGUMENTS,
                "recursive_refresh_not_allowed",
                "refresh cannot replay refresh",
            )

        with self._tool_use_lock:
            pending = self._refreshes.get(source_id)
            if pending is None:
                pending = Future()
                self._refreshes[source_id] = pending
                owns_replay = True
            else:
                owns_replay = False

        if owns_replay:
            try:
                replay = self.execute(
                    ExecutionDecision(
                        CALL_TOOL,
                        source.tool_name,
                        dict(source.arguments),
                        f"Refresh tool use {source_id}.",
                    ),
                    context,
                    task,
                )
            except BaseException as error:
                pending.set_exception(error)
                with self._tool_use_lock:
                    self._refreshes.pop(source_id, None)
                raise
            else:
                pending.set_result(replay)
                with self._tool_use_lock:
                    self._refreshes.pop(source_id, None)
        else:
            replay = pending.result()
        if replay.tool_result is not None:
            return replace(
                replay,
                decision=decision,
                tool_result=replace(
                    replay.tool_result,
                    refresh_of_tool_use_id=source_id,
                ),
            )
        if replay.failure is not None:
            return replace(
                replay,
                decision=decision,
                failure=replace(
                    replay.failure,
                    refresh_of_tool_use_id=source_id,
                ),
            )
        return replace(replay, decision=decision)

    def _remember_tool_use(self, record: ToolUseRecord) -> None:
        with self._tool_use_lock:
            self._tool_uses[record.tool_use_id] = record

    def _record_timing(
        self,
        context: AgentExecutionContext,
        tool_name: str,
        started: float,
        success: bool,
        code: str | None,
    ) -> None:
        self.timing_recorder.record_tool_call(
            context.task_id,
            tool_name=tool_name,
            duration_ms=round((perf_counter() - started) * 1000, 3),
            success=success,
            failure_kind=None if success else ToolFailureKind.TOOL_EXECUTION_FAILED.value,
            failure_code=code,
        )

    @staticmethod
    def _failure(
        decision: ExecutionDecision,
        task: Task,
        kind: ToolFailureKind,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        raw_result: Any | None = None,
        tool_use_id: str | None = None,
        context: AgentExecutionContext | None = None,
        called_at: str | None = None,
        completed_at: str | None = None,
        result_ttl_seconds: float | None = None,
        refresh_of_tool_use_id: str | None = None,
    ) -> CapabilityExecutionResult:
        return CapabilityExecutionResult(
            decision=decision,
            failure=ToolFailureObservation(
                attempt_id=task.current_step.attempt_id,
                tool_name=decision.tool_name or "unknown",
                kind=kind,
                code=code,
                message=message,
                arguments=decision.tool_input or {},
                retryable=retryable,
                tool_use_id=tool_use_id,
                task_id=None if context is None else context.task_id,
                agent_id=None if context is None else context.agent_id,
                parent_agent_id=None if context is None else context.parent_agent_id,
                called_at=called_at,
                completed_at=completed_at,
                result_ttl_seconds=result_ttl_seconds,
                refresh_of_tool_use_id=refresh_of_tool_use_id,
            ),
            raw_result=raw_result,
        )


def _may_have_unconfirmed_side_effect(tool: Any) -> bool:
    return bool(
        tool.definition.side_effecting
        and tool.definition.uncertain_policy
        is ToolUncertainPolicy.POSSIBLE_AFTER_DISPATCH
    )


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _tool_schema(tool: Any, schema_name: str) -> dict[str, Any]:
    return getattr(tool.definition, schema_name)


def _validate_schema(value: Any, schema: dict[str, Any], *, path: str) -> str | None:
    if "enum" in schema and value not in schema["enum"]:
        return f"{path} must be one of {tuple(schema['enum'])}"
    schema_type = schema.get("type")
    if schema_type is None:
        return None
    if schema_type == "object":
        if not isinstance(value, dict):
            return f"{path} must be an object"
        required = schema.get("required", ())
        for key in required if isinstance(required, (list, tuple)) else ():
            if key not in value:
                return f"{path}.{key} is required"
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    return f"{path} has unsupported property {key}"
        for key, nested in properties.items() if isinstance(properties, dict) else ():
            if key in value and isinstance(nested, dict):
                error = _validate_schema(value[key], nested, path=f"{path}.{key}")
                if error:
                    return error
        return None
    if schema_type == "array":
        if not isinstance(value, (list, tuple)):
            return f"{path} must be an array"
        nested = schema.get("items")
        if isinstance(nested, dict):
            for index, item in enumerate(value):
                error = _validate_schema(item, nested, path=f"{path}[{index}]")
                if error:
                    return error
        return None
    if schema_type == "string" and not isinstance(value, str):
        return f"{path} must be a string"
    if schema_type == "number" and (
        not isinstance(value, (int, float)) or isinstance(value, bool)
    ):
        return f"{path} must be a number"
    if schema_type == "number":
        if "minimum" in schema and value < schema["minimum"]:
            return f"{path} must be at least {schema['minimum']}"
        if "maximum" in schema and value > schema["maximum"]:
            return f"{path} must be at most {schema['maximum']}"
    if schema_type == "boolean" and not isinstance(value, bool):
        return f"{path} must be a boolean"
    return None
