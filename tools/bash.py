from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess

from agent.context import AgentExecutionContext

from .base import (
    ToolDefinition,
    ToolIdempotency,
    ToolResult,
    ToolUncertainPolicy,
)


DEFAULT_BASH_TIMEOUT_SECONDS = 30
MAX_BASH_TIMEOUT_SECONDS = 600
MAX_BASH_OUTPUT_BYTES = 1_000_000
MAX_BASH_COMMAND_CHARS = 100_000


@dataclass(frozen=True, slots=True)
class BashTool:
    project_root: Path
    sandbox_executable: Path = Path("/usr/bin/sandbox-exec")
    default_timeout_seconds: int = DEFAULT_BASH_TIMEOUT_SECONDS
    max_timeout_seconds: int = MAX_BASH_TIMEOUT_SECONDS
    max_output_bytes: int = MAX_BASH_OUTPUT_BYTES
    name: str = "bash"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    def __post_init__(self) -> None:
        if self.default_timeout_seconds < 1:
            raise ValueError("default_timeout_seconds must be positive")
        if self.max_timeout_seconds < self.default_timeout_seconds:
            raise ValueError("max_timeout_seconds must allow the default timeout")
        if self.max_output_bytes < 1:
            raise ValueError("max_output_bytes must be positive")

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Run one shell command from the project root in a macOS sandbox. "
                "File writes outside the project root are denied. Returns separate "
                "stdout, stderr, exit status, timeout, and truncation metadata."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout_seconds": {
                        "type": "number",
                        "minimum": 1,
                        "maximum": self.max_timeout_seconds,
                    },
                },
                "required": ["command"],
                "additionalProperties": False,
            },
            input_examples=({"command": "python -m pytest -q"},),
            output_schema={
                "type": "object",
                "properties": {
                    "exit_code": {"type": "number"},
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                    "timed_out": {"type": "boolean"},
                    "stdout_truncated": {"type": "boolean"},
                    "stderr_truncated": {"type": "boolean"},
                },
                "required": [
                    "exit_code",
                    "stdout",
                    "stderr",
                    "timed_out",
                    "stdout_truncated",
                    "stderr_truncated",
                ],
                "additionalProperties": False,
            },
            result_ttl_seconds=300,
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
        command = args.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("command must be a non-empty string")
        if len(command) > MAX_BASH_COMMAND_CHARS:
            raise ValueError("command exceeds the maximum length")
        raw_timeout = args.get("timeout_seconds", self.default_timeout_seconds)
        if (
            not isinstance(raw_timeout, (int, float))
            or isinstance(raw_timeout, bool)
            or raw_timeout < 1
            or raw_timeout > self.max_timeout_seconds
        ):
            raise ValueError("timeout_seconds is outside the allowed range")
        sandbox = self.sandbox_executable
        if not sandbox.is_file() or not os.access(sandbox, os.X_OK):
            raise RuntimeError("macOS sandbox-exec is unavailable")
        root = self.project_root.resolve(strict=True)
        profile = _sandbox_profile(root)
        process = subprocess.Popen(
            [str(sandbox), "-p", profile, "/bin/zsh", "-lc", command],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=float(raw_timeout))
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
        stdout, stdout_truncated = _bounded_output(stdout, self.max_output_bytes)
        stderr, stderr_truncated = _bounded_output(stderr, self.max_output_bytes)
        return ToolResult(
            self.name,
            context.task_id,
            {
                "exit_code": int(process.returncode),
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": timed_out,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            },
        )


def _sandbox_profile(project_root: Path) -> str:
    root = json.dumps(str(project_root))
    return (
        "(version 1) "
        "(allow default) "
        "(deny file-write*) "
        f"(allow file-write* (subpath {root}) (literal \"/dev/null\"))"
    )


def _bounded_output(value: bytes, limit: int) -> tuple[str, bool]:
    truncated = len(value) > limit
    return value[:limit].decode("utf-8", errors="replace"), truncated
