from dataclasses import dataclass
from typing import Any

from agent.context import AgentExecutionContext
from agent.handoff import HandoffRequest
from skill import SkillManager
from tools import ToolManager, ToolResult

from .decision import CALL_TOOL, REPLAN, ExecutionDecision
from .session import TaskSession
from .strategy import StrategyDecision
from .subagent import SubAgent


@dataclass(frozen=True, slots=True)
class CapabilityExecutionResult:
    decision: ExecutionDecision
    strategy: StrategyDecision
    tool_result: ToolResult | None
    replan_required: bool
    failure_reason: str | None = None
    unavailable_tool: str | None = None

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

    def execute(
        self,
        decision: ExecutionDecision | StrategyDecision | None = None,
        strategy: StrategyDecision | HandoffRequest | None = None,
        context: AgentExecutionContext | None = None,
        task_session: TaskSession | None = None,
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
                reason=f"skill {strategy.skill_name} is not registered",
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
                reason=f"tool {tool_name} is not allowed",
                unavailable_tool=tool_name,
            )

        tool = self.tool_manager.get_tool(tool_name)
        if tool is None:
            return self._failure(
                decision=decision,
                strategy=strategy,
                reason=f"tool {tool_name} is not registered",
                unavailable_tool=tool_name,
            )
        if context.agent_role not in self.tool_manager._allowed_roles(tool):
            return self._failure(
                decision=decision,
                strategy=strategy,
                reason=f"tool {tool_name} is not visible to agent role {context.agent_role}",
                unavailable_tool=tool_name,
            )

        arguments = decision.tool_input or {}
        input_schema = _tool_schema(tool, "input_schema")
        input_error = _validate_schema(
            arguments,
            input_schema,
            path="arguments",
        )
        if input_error is not None and arguments:
            empty_arguments_error = _validate_schema(
                {},
                input_schema,
                path="arguments",
            )
            if empty_arguments_error is None:
                input_error = None
        if input_error is not None:
            return self._failure(
                decision=decision,
                strategy=strategy,
                reason=f"invalid_tool_input: {input_error}",
                unavailable_tool=tool_name,
            )

        tool_result = tool.run(context)
        output_schema = _tool_schema(tool, "output_schema")
        output_error = _validate_schema(
            tool_result.payload,
            output_schema,
            path="payload",
        )
        if output_error is not None:
            return self._failure(
                decision=decision,
                strategy=strategy,
                reason=f"invalid_tool_output: {output_error}",
                unavailable_tool=tool_name,
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
        task_session: TaskSession | None,
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
        reason: str,
        unavailable_tool: str | None = None,
    ) -> CapabilityExecutionResult:
        return CapabilityExecutionResult(
            decision=decision,
            strategy=strategy,
            tool_result=None,
            replan_required=True,
            failure_reason=reason,
            unavailable_tool=unavailable_tool,
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
    if schema_type == "boolean" and not isinstance(value, bool):
        return f"{path} must be a boolean"
    return None
