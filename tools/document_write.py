from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path, PurePosixPath
import tempfile

from agent.context import AgentExecutionContext

from .base import (
    ToolDefinition,
    ToolIdempotency,
    ToolResult,
    ToolUncertainPolicy,
)


MAX_DOCUMENT_BYTES = 1_000_000
ALLOWED_DOCUMENT_SUFFIXES = frozenset({".csv", ".json", ".md", ".txt"})


@dataclass(frozen=True, slots=True)
class DocumentWriteTool:
    root_directory: Path
    name: str = "document_write"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Purpose: Save a completed user-requested text document as "
                "Markdown, plain text, JSON, or CSV. Use when: The requested "
                "deliverable must persist beyond the chat response. Do not use "
                "when: The user only needs an in-chat answer, or for executable "
                "files, credentials, raw media, arbitrary filesystem access, or "
                "paths outside the controlled document directory. Execution "
                "behavior: Supply the complete document content and a safe relative "
                "path in one call. Failure and limitations: A successful write "
                "result is required before claiming that the artifact exists."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": (
                            "Safe relative output path ending in .md, .txt, .json, "
                            "or .csv."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": "Complete UTF-8 document content.",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": (
                            "Whether an existing document may be atomically replaced."
                        ),
                    },
                },
                "required": ["relative_path", "content"],
                "additionalProperties": False,
            },
            input_examples=(
                {
                    "relative_path": "reports/ella-competition-analysis.md",
                    "content": "# Ella Agent Runtime competition analysis\n",
                    "overwrite": False,
                },
            ),
            output_schema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["written"]},
                    "relative_path": {"type": "string"},
                    "bytes_written": {"type": "number"},
                    "sha256": {"type": "string"},
                    "overwritten": {"type": "boolean"},
                },
                "required": [
                    "status",
                    "relative_path",
                    "bytes_written",
                    "sha256",
                    "overwritten",
                ],
                "additionalProperties": False,
            },
            idempotency=ToolIdempotency.NON_IDEMPOTENT,
            side_effecting=True,
            uncertain_policy=ToolUncertainPolicy.POSSIBLE_AFTER_DISPATCH,
        )

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict[str, object] | None = None,
    ) -> ToolResult:
        arguments = arguments or {}
        relative_path = _validate_relative_path(arguments.get("relative_path"))
        content = arguments.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("content must be a non-empty string")
        encoded_content = content.encode("utf-8")
        if len(encoded_content) > MAX_DOCUMENT_BYTES:
            raise ValueError(
                f"content exceeds the {MAX_DOCUMENT_BYTES}-byte document limit"
            )
        overwrite = arguments.get("overwrite", False)
        if not isinstance(overwrite, bool):
            raise ValueError("overwrite must be a boolean")

        root = self.root_directory.expanduser()
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve()
        target = root.joinpath(*relative_path.parts)
        _reject_symlink_components(root, target)
        resolved_target = target.resolve(strict=False)
        if not resolved_target.is_relative_to(root):
            raise ValueError("relative_path must remain inside document directory")
        existed = resolved_target.exists()
        if existed and not overwrite:
            raise ValueError("document already exists; set overwrite=true to replace it")
        if existed and not resolved_target.is_file():
            raise ValueError("document path does not refer to a regular file")

        resolved_target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=resolved_target.parent,
                prefix=f".{resolved_target.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(encoded_content)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            if overwrite:
                os.replace(temporary_path, resolved_target)
            else:
                try:
                    os.link(temporary_path, resolved_target)
                except FileExistsError as error:
                    raise ValueError(
                        "document already exists; set overwrite=true to replace it"
                    ) from error
                temporary_path.unlink()
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        payload = {
            "status": "written",
            "relative_path": relative_path.as_posix(),
            "bytes_written": len(encoded_content),
            "sha256": sha256(encoded_content).hexdigest(),
            "overwritten": existed,
        }
        return ToolResult(self.name, context.task_id, context.trace_id, payload)


def _validate_relative_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("relative_path must be a non-empty string")
    if "\\" in value:
        raise ValueError("relative_path must use forward slashes")
    path = PurePosixPath(value.strip())
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("relative_path must be safe and relative")
    if path.suffix.casefold() not in ALLOWED_DOCUMENT_SUFFIXES:
        raise ValueError("document extension must be .md, .txt, .json, or .csv")
    return path


def _reject_symlink_components(root: Path, target: Path) -> None:
    current = root
    for part in target.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("relative_path must not traverse symbolic links")
