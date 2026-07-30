from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from runtime.timing import NoOpRuntimeTimingRecorder, RuntimeTimingRecorder
from skill import SkillManager
from tools import ToolManager, ToolResult
from tools.base import ToolUncertainPolicy, invoke_tool

from agent.decision import CALL_TOOL, REPLAN, ExecutionDecision
from agent.strategy import StrategyDecision
from agent.subagent import SubAgent
from tasks.state import ToolFailureKind, ToolFailureObservation
from tasks.task import Task


@dataclass(frozen=True, slots=True)
class CapabilityExecutionResult:
    decision: ExecutionDecision
    strategy: StrategyDecision
    tool_result: ToolResult | None
    replan_required: bool
    failure_reason: str | None = None
    unavailable_tool: str | None = None
    failure: ToolFailureObservation | None = None
    raw_result: Any | None = field(default=None, repr=False, compare=False)
    uncertain: bool = False

    def __post_init__(self) -> None:
        if self.tool_result is not None and self.failure is not None:
            raise ValueError("tool_result and failure are mutually exclusive")

    @property
    def tool_results(self) -> tuple[ToolResult, ...]:
        if self.tool_result is None:
            return ()
        return (self.tool_result,)

    @property
    def unavailable_tools(self) -> tuple[str, ...]:
        if self.unavailable_tool is None:
            return ()
        return (self.unavailable_tool,)

    @property
    def replanned(self) -> bool:
        return self.replan_required


@dataclass(frozen=True, slots=True)
class CapabilityExecutor:
    skill_manager: SkillManager
    tool_manager: ToolManager
    subagent: SubAgent | None = None
    timing_recorder: RuntimeTimingRecorder | NoOpRuntimeTimingRecorder = field(
        default_factory=NoOpRuntimeTimingRecorder
    )

    def execute_tool_node(
        self,
        *,
        tool_name: str,
        arguments: dict[str, object],
        strategy: StrategyDecision,
        context: AgentExecutionContext,
        task: Task,
    ) -> CapabilityExecutionResult:
        """Execute one graph-selected ToolNode through the normal boundary."""
        return self.execute(
            decision=ExecutionDecision(
                CALL_TOOL,
                tool_name,
                arguments,
                "Execute the selected ToolGraph node.",
                False,
            ),
            strategy=strategy,
            context=context,
            task_session=task,
        )

    def execute(
        self,
        decision: ExecutionDecision | StrategyDecision | None = None,
        strategy: StrategyDecision | HandoffRequest | None = None,
        context: AgentExecutionContext | None = None,
        task_session: Task | None = None,
        handoff: HandoffRequest | None = None,
    ) -> CapabilityExecutionResult:
        decision, strategy = self._normalize_request(
            decision=decision,
            strategy=strategy,
            context=context,
            task_session=task_session,
            handoff=handoff,
        )
        if context is None or task_session is None:
            raise TypeError("context and task_session are required")

        if (
            strategy.skill_name is not None
            and self.skill_manager.get_summary(strategy.skill_name) is None
        ):
            return self._failure(
                decision=decision,
                strategy=strategy,
                task_session=task_session,
                reason=f"skill {strategy.skill_name} is not registered",
                kind=ToolFailureKind.ENVIRONMENT_UNAVAILABLE,
                code="skill_not_registered",
                tool_name=strategy.skill_name,
            )

        if decision.action == REPLAN:
            return CapabilityExecutionResult(
                decision=decision,
                strategy=strategy,
                tool_result=None,
                replan_required=True,
            )

        if decision.action != CALL_TOOL:
            return CapabilityExecutionResult(
                decision=decision,
                strategy=strategy,
                tool_result=None,
                replan_required=False,
            )

        tool_name = decision.tool_name
        if tool_name is None:
            raise ValueError("CALL_TOOL execution decision requires tool_name")
        if tool_name not in context.allowed_tools:
            return self._failure(
                decision=decision,
                strategy=strategy,
                task_session=task_session,
                reason=f"tool {tool_name} is not allowed",
                kind=ToolFailureKind.PERMISSION_DENIED,
                code="tool_not_allowed",
                unavailable_tool=tool_name,
            )

        tool = self.tool_manager.get_tool(tool_name)
        if tool is None:
            return self._failure(
                decision=decision,
                strategy=strategy,
                task_session=task_session,
                reason=f"tool {tool_name} is not registered",
                kind=ToolFailureKind.ENVIRONMENT_UNAVAILABLE,
                code="tool_not_registered",
                unavailable_tool=tool_name,
            )
        if context.agent_role not in self.tool_manager._allowed_roles(tool):
            return self._failure(
                decision=decision,
                strategy=strategy,
                task_session=task_session,
                reason=f"tool {tool_name} is not visible to agent role {context.agent_role}",
                kind=ToolFailureKind.PERMISSION_DENIED,
                code="tool_role_not_allowed",
                unavailable_tool=tool_name,
            )

        arguments = decision.tool_input or {}
        input_schema = _tool_schema(tool, "input_schema")
        input_error = _validate_schema(
            arguments,
            input_schema,
            path="arguments",
        )
        if input_error is not None:
            return self._failure(
                decision=decision,
                strategy=strategy,
                task_session=task_session,
                reason=f"invalid_tool_input: {input_error}",
                kind=ToolFailureKind.INVALID_ARGUMENTS,
                code="invalid_tool_input",
                retryable=True,
                unavailable_tool=tool_name,
            )

        tool_started = perf_counter()
        try:
            tool_result = invoke_tool(tool, context, arguments)
        except ValueError as error:
            duration_ms = round((perf_counter() - tool_started) * 1000, 3)
            self.timing_recorder.record_tool_call(
                context.trace_id,
                tool_name=tool_name,
                duration_ms=duration_ms,
                success=False,
                failure_kind=ToolFailureKind.INVALID_ARGUMENTS.value,
                failure_code="invalid_tool_input",
            )
            return self._failure(
                decision=decision,
                strategy=strategy,
                task_session=task_session,
                reason=f"invalid_tool_input: {error}",
                kind=ToolFailureKind.INVALID_ARGUMENTS,
                code="invalid_tool_input",
                retryable=True,
                unavailable_tool=tool_name,
            )
        except Exception:
            duration_ms = round((perf_counter() - tool_started) * 1000, 3)
            uncertain = _may_have_unconfirmed_side_effect(tool)
            failure_code = (
                "uncertain_tool_outcome"
                if uncertain
                else "tool_execution_failed"
            )
            self.timing_recorder.record_tool_call(
                context.trace_id,
                tool_name=tool_name,
                duration_ms=duration_ms,
                success=False,
                failure_kind=ToolFailureKind.TOOL_EXECUTION_FAILED.value,
                failure_code=failure_code,
            )
            result = self._failure(
                decision=decision,
                strategy=strategy,
                task_session=task_session,
                reason=(
                    f"tool {tool_name} was dispatched but its external outcome "
                    "could not be confirmed"
                    if uncertain
                    else f"tool {tool_name} execution failed"
                ),
                kind=ToolFailureKind.TOOL_EXECUTION_FAILED,
                code=failure_code,
                unavailable_tool=tool_name,
            )
            if not uncertain:
                return result
            return CapabilityExecutionResult(
                decision=result.decision,
                strategy=result.strategy,
                tool_result=None,
                replan_required=False,
                failure_reason=result.failure_reason,
                unavailable_tool=result.unavailable_tool,
                failure=result.failure,
                raw_result=result.raw_result,
                uncertain=True,
            )
        tool_duration_ms = round((perf_counter() - tool_started) * 1000, 3)
        output_schema = _tool_schema(tool, "output_schema")
        output_error = _validate_schema(
            tool_result.payload,
            output_schema,
            path="payload",
        )
        if output_error is not None:
            self.timing_recorder.record_tool_call(
                context.trace_id,
                tool_name=tool_name,
                duration_ms=tool_duration_ms,
                success=False,
                failure_kind=ToolFailureKind.TOOL_EXECUTION_FAILED.value,
                failure_code="invalid_tool_output",
            )
            return self._failure(
                decision=decision,
                strategy=strategy,
                task_session=task_session,
                reason=f"invalid_tool_output: {output_error}",
                kind=ToolFailureKind.TOOL_EXECUTION_FAILED,
                code="invalid_tool_output",
                unavailable_tool=tool_name,
                raw_result=tool_result,
            )

        normalized_failure = _failure_from_tool_result(
            tool_result,
            attempt_id=task_session.current_step.attempt_id,
            arguments=arguments,
        )
        if normalized_failure is not None:
            self.timing_recorder.record_tool_call(
                context.trace_id,
                tool_name=tool_name,
                duration_ms=tool_duration_ms,
                success=False,
                failure_kind=normalized_failure.kind.value,
                failure_code=normalized_failure.code,
            )
            return CapabilityExecutionResult(
                decision=decision,
                strategy=strategy,
                tool_result=None,
                replan_required=False,
                failure_reason=normalized_failure.message,
                unavailable_tool=tool_name,
                failure=normalized_failure,
                raw_result=tool_result,
            )

        self.timing_recorder.record_tool_call(
            context.trace_id,
            tool_name=tool_name,
            duration_ms=tool_duration_ms,
            success=True,
        )
        return CapabilityExecutionResult(
            decision=decision,
            strategy=strategy,
            tool_result=tool_result,
            replan_required=False,
        )

    def _normalize_request(
        self,
        decision: ExecutionDecision | StrategyDecision | None,
        strategy: StrategyDecision | HandoffRequest | None,
        context: AgentExecutionContext | None,
        task_session: Task | None,
        handoff: HandoffRequest | None,
    ) -> tuple[ExecutionDecision, StrategyDecision]:
        if isinstance(decision, ExecutionDecision):
            if not isinstance(strategy, StrategyDecision):
                raise TypeError("strategy must be a StrategyDecision")
            return decision, strategy

        legacy_strategy: StrategyDecision | None = None
        legacy_handoff = handoff
        if isinstance(decision, StrategyDecision):
            legacy_strategy = decision
            if isinstance(strategy, HandoffRequest):
                legacy_handoff = strategy
        elif decision is None and isinstance(strategy, StrategyDecision):
            legacy_strategy = strategy

        if legacy_strategy is None:
            raise TypeError("decision must be an ExecutionDecision")
        if context is None or task_session is None or legacy_handoff is None:
            raise TypeError("legacy execution requires handoff, context, and task_session")

        if (
            legacy_strategy.skill_name is not None
            and self.skill_manager.get_summary(legacy_strategy.skill_name) is None
            and self.subagent is not None
        ):
            replanned_strategy = self.subagent.replan_if_unavailable(
                legacy_strategy,
                legacy_handoff,
                context,
                task_session,
            )
            return (
                ExecutionDecision(
                    action=REPLAN,
                    tool_name=None,
                    tool_input=None,
                    reason="The selected skill is no longer available.",
                    is_complete=False,
                ),
                replanned_strategy,
            )

        if not context.allowed_tools:
            return (
                ExecutionDecision(
                    action=REPLAN,
                    tool_name=None,
                    tool_input=None,
                    reason="No allowed tool is available for legacy execution.",
                    is_complete=False,
                ),
                legacy_strategy,
            )

        tool_name = context.allowed_tools[0]
        return (
            ExecutionDecision(
                action=CALL_TOOL,
                tool_name=tool_name,
                tool_input=None,
                reason="Execute one allowed legacy capability action.",
                is_complete=False,
            ),
            legacy_strategy,
        )

    @staticmethod
    def _failure(
        decision: ExecutionDecision,
        strategy: StrategyDecision,
        task_session: Task,
        reason: str,
        kind: ToolFailureKind,
        code: str,
        retryable: bool = False,
        tool_name: str | None = None,
        unavailable_tool: str | None = None,
        raw_result: Any | None = None,
    ) -> CapabilityExecutionResult:
        failure_tool_name = tool_name or unavailable_tool or decision.tool_name or "unknown"
        return CapabilityExecutionResult(
            decision=decision,
            strategy=strategy,
            tool_result=None,
            replan_required=True,
            failure_reason=reason,
            unavailable_tool=unavailable_tool,
            failure=ToolFailureObservation(
                attempt_id=task_session.current_step.attempt_id,
                tool_name=failure_tool_name,
                kind=kind,
                code=code,
                message=reason,
                arguments=decision.tool_input or {},
                retryable=retryable,
            ),
            raw_result=raw_result,
        )


_PERMISSION_ERROR_CODES = frozenset(
    {
        "permission_denied",
        "authentication_failed",
        "authorization_failed",
    }
)
_ENVIRONMENT_ERROR_CODES = frozenset(
    {
        "backend_unavailable",
        "device_busy",
        "device_not_found",
        "device_unavailable",
        "file_not_found",
        "network_unavailable",
        "timeout",
        "tool_not_registered",
    }
)


def _failure_from_tool_result(
    tool_result: ToolResult,
    *,
    attempt_id: str,
    arguments: dict[str, object],
) -> ToolFailureObservation | None:
    payload = tool_result.payload
    error = payload.get("error")
    if payload.get("status") != "unavailable" and error is None:
        return None

    if isinstance(error, dict):
        raw_code = error.get("code")
        raw_message = error.get("message")
    else:
        raw_code = None
        raw_message = error
    code = str(raw_code or "tool_unavailable")
    message = str(raw_message or payload.get("summary") or "tool is unavailable")

    if code in _PERMISSION_ERROR_CODES:
        kind = ToolFailureKind.PERMISSION_DENIED
    elif code in _ENVIRONMENT_ERROR_CODES or code == "tool_unavailable":
        kind = ToolFailureKind.ENVIRONMENT_UNAVAILABLE
    else:
        kind = ToolFailureKind.TOOL_EXECUTION_FAILED

    return ToolFailureObservation(
        attempt_id=attempt_id,
        tool_name=tool_result.tool_name,
        kind=kind,
        code=code,
        message=message,
        arguments=arguments,
        retryable=False,
    )


def _may_have_unconfirmed_side_effect(tool: Any) -> bool:
    definition = getattr(tool, "definition", None)
    return bool(
        definition is not None
        and getattr(definition, "side_effecting", False)
        and getattr(definition, "uncertain_policy", None)
        is ToolUncertainPolicy.POSSIBLE_AFTER_DISPATCH
    )


def _tool_schema(tool: Any, schema_name: str) -> dict[str, Any]:
    definition = getattr(tool, "definition", None)
    if definition is None:
        return {"type": "object"}
    schema = getattr(definition, schema_name, None)
    if not isinstance(schema, dict):
        return {"type": "object"}
    return schema


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
        if isinstance(required, (list, tuple)):
            for key in required:
                if key not in value:
                    return f"{path}.{key} is required"
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return None
        if schema.get("additionalProperties") is False:
            extra_keys = tuple(key for key in value if key not in properties)
            if extra_keys:
                return f"{path} has unsupported property {extra_keys[0]}"
        required_keys = set(required) if isinstance(required, (list, tuple)) else set()
        for key, nested_schema in properties.items():
            if key not in value:
                continue
            if value[key] is None and key not in required_keys:
                continue
            if not isinstance(nested_schema, dict):
                continue
            error = _validate_schema(
                value[key],
                nested_schema,
                path=f"{path}.{key}",
            )
            if error is not None:
                return error
        return None
    if schema_type == "array":
        if not isinstance(value, (list, tuple)):
            return f"{path} must be an array"
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                error = _validate_schema(item, item_schema, path=f"{path}[{index}]")
                if error is not None:
                    return error
        return None
    if schema_type == "string" and not isinstance(value, str):
        return f"{path} must be a string"
    if schema_type == "number" and (
        not isinstance(value, (int, float)) or isinstance(value, bool)
    ):
        return f"{path} must be a number"
    if schema_type == "number":
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            return f"{path} must be at least {minimum}"
        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and value > maximum:
            return f"{path} must be at most {maximum}"
    if schema_type == "boolean" and not isinstance(value, bool):
        return f"{path} must be a boolean"
    return None
