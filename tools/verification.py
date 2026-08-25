from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from agent.context import AgentExecutionContext

from .base import ToolDefinition, ToolIdempotency, ToolResult


MAX_VERIFICATION_DOCUMENT_BYTES = 200_000


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
                "Read-only verification capability. Check whether a user-visible "
                "artifact exists under the controlled output directory. Use only "
                "during result verification. Never use for arbitrary local paths."
            ),
            schema_version="1.0",
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
                "Read-only verification capability. Read a bounded UTF-8 document "
                "under the controlled document directory to verify a produced "
                "deliverable. Do not use for arbitrary filesystem access."
            ),
            schema_version="1.0",
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
                "Read-only verification capability. Query persisted observations "
                "for this Task by observation_id or tool_name. It never executes "
                "the original Tool again."
            ),
            schema_version="1.0",
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
