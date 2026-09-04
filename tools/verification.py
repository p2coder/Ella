from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from agent.context import AgentExecutionContext
from agent.verification import VerificationAgent
from tasks.task import Task

from .base import ToolDefinition, ToolIdempotency, ToolResult


MAX_VERIFICATION_DOCUMENT_BYTES = 200_000


@dataclass(frozen=True, slots=True)
class VerificationTool:
    task_reader: Callable[[str], Task]
    verification_agent: VerificationAgent
    name: str = "verification"
    allowed_roles: tuple[str, ...] = ("main_agent", "subagent")

    @property
    def definition(self) -> ToolDefinition:
        string_array = {"type": "array", "items": {"type": "string"}}
        return ToolDefinition(
            name=self.name,
            description=(
                "Verify a candidate result against the current task intent and "
                "observations. Task data is loaded from the execution context."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {"candidate_result": {"type": "string"}},
                "required": ["candidate_result"],
                "additionalProperties": False,
            },
            input_examples=({"candidate_result": "The requested report is ready."},),
            output_schema={
                "type": "object",
                "properties": {
                    "goal_state": {"type": "string"},
                    "criterion_results": string_array,
                    "deliverable_results": string_array,
                    "draft_quality_issues": string_array,
                    "recoverable": {"type": "boolean"},
                    "feedback_for_execution": {"type": "string"},
                    "public_summary": {"type": "string"},
                },
                "required": [
                    "goal_state",
                    "criterion_results",
                    "deliverable_results",
                    "draft_quality_issues",
                    "recoverable",
                    "feedback_for_execution",
                    "public_summary",
                ],
                "additionalProperties": False,
            },
            result_ttl_seconds=300,
            idempotency=ToolIdempotency.IDEMPOTENT,
        )

    def run(self, context: AgentExecutionContext, arguments=None) -> ToolResult:
        candidate_result = str((arguments or {}).get("candidate_result", ""))
        action = self.verification_agent.decide_candidate(
            self.task_reader(context.task_id),
            candidate_result=candidate_result,
        )
        if action.verdict is None:
            raise RuntimeError("verification did not produce a verdict")
        return ToolResult(
            self.name,
            context.task_id,
            context.trace_id,
            action.verdict.to_dict(),
        )


def _safe_target(root: Path, value: object) -> tuple[PurePosixPath, Path]:
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        raise ValueError("relative_path must be a non-empty POSIX relative path")
    relative = PurePosixPath(value.strip())
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("relative_path must remain inside the controlled root")
    controlled_root = root.expanduser().resolve()
    target = controlled_root.joinpath(*relative.parts).resolve(strict=False)
    if not target.is_relative_to(controlled_root):
        raise ValueError("relative_path must remain inside the controlled root")
    return relative, target


@dataclass(frozen=True, slots=True)
class ArtifactExistsTool:
    root_directory: Path
    name: str = "artifact_exists"
    allowed_roles: tuple[str, ...] = ("main_agent", "verification_agent")

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Purpose: Check whether a user-visible artifact exists under the "
                "controlled output directory. Use when: Result verification must "
                "mechanically confirm an expected artifact. Do not use when: The "
                "task does not claim an artifact or the target is an arbitrary "
                "local path. Execution behavior: Perform a read-only existence and "
                "file-type check; never create or modify the artifact."
            ),
            schema_version="1.0",
            result_ttl_seconds=3600,
            input_schema={
                "type": "object",
                "properties": {"relative_path": {"type": "string"}},
                "required": ["relative_path"],
                "additionalProperties": False,
            },
            input_examples=({"relative_path": "reports/result.md"},),
            output_schema={
                "type": "object",
                "properties": {
                    "relative_path": {"type": "string"},
                    "exists": {"type": "boolean"},
                    "is_file": {"type": "boolean"},
                },
                "required": ["relative_path", "exists", "is_file"],
                "additionalProperties": False,
            },
            idempotency=ToolIdempotency.IDEMPOTENT,
        )

    def run(self, context: AgentExecutionContext, arguments=None) -> ToolResult:
        relative, target = _safe_target(
            self.root_directory, (arguments or {}).get("relative_path")
        )
        return ToolResult(
            self.name,
            context.task_id,
            context.trace_id,
            {
                "relative_path": relative.as_posix(),
                "exists": target.exists(),
                "is_file": target.is_file(),
            },
        )


@dataclass(frozen=True, slots=True)
class DocumentReadTool:
    root_directory: Path
    max_bytes: int = MAX_VERIFICATION_DOCUMENT_BYTES
    name: str = "document_read"
    allowed_roles: tuple[str, ...] = ("main_agent", "verification_agent")

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Purpose: Read a bounded UTF-8 document under the controlled "
                "document directory. Use when: Result verification must inspect a "
                "produced text deliverable. Do not use when: The target is outside "
                "the controlled directory or arbitrary filesystem access is "
                "requested. Execution behavior: Read without modifying the file. "
                "Failure and limitations: Content may be truncated at the configured "
                "byte limit and non-UTF-8 documents are unsupported."
            ),
            schema_version="1.0",
            result_ttl_seconds=3600,
            input_schema={
                "type": "object",
                "properties": {"relative_path": {"type": "string"}},
                "required": ["relative_path"],
                "additionalProperties": False,
            },
            input_examples=({"relative_path": "reports/result.md"},),
            output_schema={
                "type": "object",
                "properties": {
                    "relative_path": {"type": "string"},
                    "content": {"type": "string"},
                    "bytes_read": {"type": "number"},
                    "truncated": {"type": "boolean"},
                },
                "required": ["relative_path", "content", "bytes_read", "truncated"],
                "additionalProperties": False,
            },
            idempotency=ToolIdempotency.IDEMPOTENT,
        )

    def run(self, context: AgentExecutionContext, arguments=None) -> ToolResult:
        relative, target = _safe_target(
            self.root_directory, (arguments or {}).get("relative_path")
        )
        if not target.is_file():
            raise ValueError("document does not exist")
        payload = target.read_bytes()
        truncated = len(payload) > self.max_bytes
        bounded = payload[: self.max_bytes]
        try:
            content = bounded.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("document must be UTF-8 text") from error
        return ToolResult(
            self.name,
            context.task_id,
            context.trace_id,
            {
                "relative_path": relative.as_posix(),
                "content": content,
                "bytes_read": len(bounded),
                "truncated": truncated,
            },
        )


@dataclass(frozen=True, slots=True)
class ToolObservationCheckTool:
    observation_reader: Callable[[str], tuple[Mapping[str, Any], ...]]
    name: str = "tool_observation_check"
    allowed_roles: tuple[str, ...] = ("main_agent", "verification_agent")

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Purpose: Query persisted Tool observations for the current Task. "
                "Use when: Result verification needs to confirm an observation by "
                "observation_id or tool_name. Do not use when: New external evidence "
                "is required. Execution behavior: Read matching persisted "
                "observations without executing the original Tool again. Failure "
                "and limitations: An unmatched query only proves that no matching "
                "persisted observation was found."
            ),
            schema_version="1.0",
            result_ttl_seconds=0,
            input_schema={
                "type": "object",
                "properties": {
                    "observation_id": {"type": "string"},
                    "tool_name": {"type": "string"},
                },
                "additionalProperties": False,
            },
            input_examples=({"tool_name": "document_write"},),
            output_schema={
                "type": "object",
                "properties": {
                    "matched": {"type": "boolean"},
                    "observations": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["matched", "observations"],
                "additionalProperties": False,
            },
            idempotency=ToolIdempotency.IDEMPOTENT,
        )

    def run(self, context: AgentExecutionContext, arguments=None) -> ToolResult:
        arguments = arguments or {}
        observation_id = arguments.get("observation_id")
        tool_name = arguments.get("tool_name")
        if observation_id is None and tool_name is None:
            raise ValueError("observation_id or tool_name is required")
        observations = tuple(
            dict(item)
            for item in self.observation_reader(context.task_id)
            if (observation_id is None or item.get("observation_id") == observation_id)
            and (tool_name is None or item.get("tool_name") == tool_name)
        )
        return ToolResult(
            self.name,
            context.task_id,
            context.trace_id,
            {"matched": bool(observations), "observations": observations},
        )
