from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path, PurePath
from tempfile import NamedTemporaryFile

from agent.context import AgentExecutionContext

from .base import (
    ToolDefinition,
    ToolIdempotency,
    ToolResult,
    ToolUncertainPolicy,
)


MAX_TEXT_FILE_BYTES = 1_000_000


class TextFileError(ValueError):
    pass


def resolve_project_path(
    project_root: Path,
    raw_path: object,
    *,
    must_exist: bool,
) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise TextFileError("path must be a non-empty relative path")
    relative = Path(raw_path)
    if relative.is_absolute() or PurePath(raw_path).anchor:
        raise TextFileError("absolute paths are not allowed")
    root = project_root.resolve()
    candidate = (root / relative).resolve(strict=must_exist)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise TextFileError("path must stay inside the project root") from error
    return candidate


@dataclass(frozen=True, slots=True)
class ReadTextTool:
    project_root: Path
    max_bytes: int = MAX_TEXT_FILE_BYTES
    name: str = "read"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    def __post_init__(self) -> None:
        if self.max_bytes < 1:
            raise ValueError("max_bytes must be positive")

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Read one UTF-8 text file inside the project root. The result "
                "includes a SHA-256 content version. A prior hash describes only "
                "that observed version; read again to establish current content."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            input_examples=({"path": "README.md"},),
            output_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "byte_count": {"type": "number"},
                    "truncated": {"type": "boolean"},
                    "content_hash_algorithm": {"type": "string"},
                    "content_hash": {"type": "string"},
                },
                "required": [
                    "path",
                    "content",
                    "byte_count",
                    "truncated",
                    "content_hash_algorithm",
                    "content_hash",
                ],
                "additionalProperties": False,
            },
            result_ttl_seconds=None,
            idempotency=ToolIdempotency.IDEMPOTENT,
        )

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict[str, object] | None = None,
    ) -> ToolResult:
        args = arguments or {}
        path = resolve_project_path(
            self.project_root,
            args.get("path"),
            must_exist=True,
        )
        if not path.is_file():
            raise TextFileError("path must reference a regular file")
        size = path.stat().st_size
        if size > self.max_bytes:
            raise TextFileError(
                f"text file exceeds the {self.max_bytes}-byte read limit"
            )
        content_bytes = path.read_bytes()
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise TextFileError("file is not valid UTF-8 text") from error
        relative = path.relative_to(self.project_root.resolve()).as_posix()
        return ToolResult(
            self.name,
            context.task_id,
            {
                "path": relative,
                "content": content,
                "byte_count": len(content_bytes),
                "truncated": False,
                "content_hash_algorithm": "sha256",
                "content_hash": sha256(content_bytes).hexdigest(),
            },
        )


@dataclass(frozen=True, slots=True)
class WriteTextTool:
    project_root: Path
    max_bytes: int = MAX_TEXT_FILE_BYTES
    name: str = "write"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    def __post_init__(self) -> None:
        if self.max_bytes < 1:
            raise ValueError("max_bytes must be positive")

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Create one new UTF-8 text file inside the project root. Existing "
                "files are never overwritten. The result includes the SHA-256 "
                "version of the bytes written."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            input_examples=({"path": "notes/result.md", "content": "# Result\n"},),
            output_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "byte_count": {"type": "number"},
                    "created": {"type": "boolean"},
                    "content_hash_algorithm": {"type": "string"},
                    "content_hash": {"type": "string"},
                },
                "required": [
                    "path",
                    "byte_count",
                    "created",
                    "content_hash_algorithm",
                    "content_hash",
                ],
                "additionalProperties": False,
            },
            result_ttl_seconds=None,
            idempotency=ToolIdempotency.NON_IDEMPOTENT,
            side_effecting=True,
            uncertain_policy=ToolUncertainPolicy.POSSIBLE_AFTER_DISPATCH,
        )

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict[str, object] | None = None,
    ) -> ToolResult:
        args = arguments or {}
        content = args.get("content")
        if not isinstance(content, str):
            raise TextFileError("content must be UTF-8 text")
        content_bytes = content.encode("utf-8")
        if len(content_bytes) > self.max_bytes:
            raise TextFileError(
                f"content exceeds the {self.max_bytes}-byte write limit"
            )
        path = resolve_project_path(
            self.project_root,
            args.get("path"),
            must_exist=False,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        parent = path.parent.resolve(strict=True)
        try:
            parent.relative_to(self.project_root.resolve())
        except ValueError as error:
            raise TextFileError("path must stay inside the project root") from error
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="wb",
                dir=parent,
                prefix=f".{path.name}.",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(content_bytes)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.link(temporary_path, path)
            _fsync_directory(parent)
        except FileExistsError as error:
            raise TextFileError("file already exists; use edit to modify it") from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        relative = path.relative_to(self.project_root.resolve()).as_posix()
        return ToolResult(
            self.name,
            context.task_id,
            {
                "path": relative,
                "byte_count": len(content_bytes),
                "created": True,
                "content_hash_algorithm": "sha256",
                "content_hash": sha256(content_bytes).hexdigest(),
            },
        )


@dataclass(frozen=True, slots=True)
class EditTextTool:
    project_root: Path
    max_bytes: int = MAX_TEXT_FILE_BYTES
    name: str = "edit"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    def __post_init__(self) -> None:
        if self.max_bytes < 1:
            raise ValueError("max_bytes must be positive")

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Replace exactly one occurrence of old_text in an existing UTF-8 "
                "file inside the project root. Zero or multiple matches fail "
                "without changing the file."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                "required": ["path", "old_text", "new_text"],
                "additionalProperties": False,
            },
            input_examples=(
                {
                    "path": "README.md",
                    "old_text": "old sentence",
                    "new_text": "new sentence",
                },
            ),
            output_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "replacement_count": {"type": "number"},
                    "byte_count_before": {"type": "number"},
                    "byte_count_after": {"type": "number"},
                    "content_hash_algorithm": {"type": "string"},
                    "content_hash": {"type": "string"},
                },
                "required": [
                    "path",
                    "replacement_count",
                    "byte_count_before",
                    "byte_count_after",
                    "content_hash_algorithm",
                    "content_hash",
                ],
                "additionalProperties": False,
            },
            result_ttl_seconds=None,
            idempotency=ToolIdempotency.NON_IDEMPOTENT,
            side_effecting=True,
            uncertain_policy=ToolUncertainPolicy.POSSIBLE_AFTER_DISPATCH,
        )

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict[str, object] | None = None,
    ) -> ToolResult:
        args = arguments or {}
        old_text = args.get("old_text")
        new_text = args.get("new_text")
        if not isinstance(old_text, str) or not old_text:
            raise TextFileError("old_text must be a non-empty string")
        if not isinstance(new_text, str):
            raise TextFileError("new_text must be a string")
        path = resolve_project_path(
            self.project_root,
            args.get("path"),
            must_exist=True,
        )
        if not path.is_file():
            raise TextFileError("path must reference a regular file")
        original_bytes = path.read_bytes()
        if len(original_bytes) > self.max_bytes:
            raise TextFileError(
                f"text file exceeds the {self.max_bytes}-byte edit limit"
            )
        try:
            original = original_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise TextFileError("file is not valid UTF-8 text") from error
        matches = original.count(old_text)
        if matches != 1:
            raise TextFileError(
                f"old_text must match exactly once; found {matches} matches"
            )
        updated_bytes = original.replace(old_text, new_text, 1).encode("utf-8")
        if len(updated_bytes) > self.max_bytes:
            raise TextFileError(
                f"edited content exceeds the {self.max_bytes}-byte limit"
            )
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(updated_bytes)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
            _fsync_directory(path.parent)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        relative = path.relative_to(self.project_root.resolve()).as_posix()
        return ToolResult(
            self.name,
            context.task_id,
            {
                "path": relative,
                "replacement_count": 1,
                "byte_count_before": len(original_bytes),
                "byte_count_after": len(updated_bytes),
                "content_hash_algorithm": "sha256",
                "content_hash": sha256(updated_bytes).hexdigest(),
            },
        )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
