from hashlib import sha256

import pytest

from agent.context import AgentExecutionContext, CapabilityScope
from tools.text_files import ReadTextTool, TextFileError


def _context() -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-read",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ("read",)),
    )


def test_read_returns_utf8_content_and_sha256_version(tmp_path) -> None:
    payload = "你好, Ella\n".encode()
    (tmp_path / "notes.txt").write_bytes(payload)

    result = ReadTextTool(tmp_path).run(_context(), {"path": "notes.txt"})

    assert result.payload == {
        "path": "notes.txt",
        "content": "你好, Ella\n",
        "byte_count": len(payload),
        "truncated": False,
        "content_hash_algorithm": "sha256",
        "content_hash": sha256(payload).hexdigest(),
    }


@pytest.mark.parametrize("path", ("", "/etc/hosts", "../outside.txt"))
def test_read_rejects_unsafe_paths(tmp_path, path) -> None:
    with pytest.raises((TextFileError, FileNotFoundError)):
        ReadTextTool(tmp_path).run(_context(), {"path": path})


def test_read_rejects_symlink_escape(tmp_path) -> None:
    outside = tmp_path.parent / "outside-read.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp_path / "escape.txt").symlink_to(outside)

    with pytest.raises(TextFileError, match="inside"):
        ReadTextTool(tmp_path).run(_context(), {"path": "escape.txt"})


def test_read_rejects_invalid_utf8_and_oversized_files(tmp_path) -> None:
    (tmp_path / "binary.txt").write_bytes(b"\xff")
    with pytest.raises(TextFileError, match="UTF-8"):
        ReadTextTool(tmp_path).run(_context(), {"path": "binary.txt"})

    (tmp_path / "large.txt").write_text("12345", encoding="utf-8")
    with pytest.raises(TextFileError, match="limit"):
        ReadTextTool(tmp_path, max_bytes=4).run(
            _context(), {"path": "large.txt"}
        )
