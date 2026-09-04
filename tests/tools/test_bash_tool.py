from pathlib import Path

import pytest

from agent.context import AgentExecutionContext, CapabilityScope
from tools.bash import BashTool


pytestmark = pytest.mark.skipif(
    not Path("/usr/bin/sandbox-exec").exists(),
    reason="requires macOS sandbox-exec",
)


def _context() -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-bash",
        trace_id="trace-bash",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ("bash",)),
    )


def test_bash_returns_stdout_stderr_and_exit_code(tmp_path) -> None:
    result = BashTool(tmp_path).run(
        _context(),
        {"command": "print -r -- output; print -r -- error >&2; exit 7"},
    )

    assert result.payload["exit_code"] == 7
    assert result.payload["stdout"] == "output\n"
    assert result.payload["stderr"] == "error\n"
    assert result.payload["timed_out"] is False


def test_bash_allows_project_write_and_denies_outside_write(tmp_path) -> None:
    result = BashTool(tmp_path).run(
        _context(), {"command": "print -n inside > result.txt"}
    )
    assert result.payload["exit_code"] == 0
    assert (tmp_path / "result.txt").read_text() == "inside"

    outside = tmp_path.parent / "ella-bash-outside.txt"
    outside.unlink(missing_ok=True)
    result = BashTool(tmp_path).run(
        _context(), {"command": f"print -n outside > {outside}"}
    )
    assert result.payload["exit_code"] != 0
    assert not outside.exists()


def test_bash_times_out_process_group(tmp_path) -> None:
    result = BashTool(
        tmp_path,
        default_timeout_seconds=1,
        max_timeout_seconds=2,
    ).run(_context(), {"command": "sleep 10", "timeout_seconds": 1})

    assert result.payload["timed_out"] is True
    assert result.payload["exit_code"] != 0


def test_bash_truncates_outputs_independently(tmp_path) -> None:
    result = BashTool(tmp_path, max_output_bytes=4).run(
        _context(), {"command": "print -n 12345; print -n abcde >&2"}
    )

    assert result.payload["stdout"] == "1234"
    assert result.payload["stderr"] == "abcd"
    assert result.payload["stdout_truncated"] is True
    assert result.payload["stderr_truncated"] is True


def test_bash_fails_closed_without_sandbox(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="unavailable"):
        BashTool(tmp_path, sandbox_executable=tmp_path / "missing").run(
            _context(), {"command": "true"}
        )
