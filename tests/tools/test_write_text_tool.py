from hashlib import sha256

import pytest

from agent.context import AgentExecutionContext, CapabilityScope
from tools.text_files import TextFileError, WriteTextTool


def _context() -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-write",
        trace_id="trace-write",
        handoff_goal="Write a text file",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ("write",)),
    )


def test_write_creates_parent_directories_and_returns_hash(tmp_path) -> None:
    content = "你好, Ella\n"
    payload = content.encode()

    result = WriteTextTool(tmp_path).run(
        _context(), {"path": "notes/result.md", "content": content}
    )

    assert (tmp_path / "notes/result.md").read_bytes() == payload
    assert result.payload == {
        "path": "notes/result.md",
        "byte_count": len(payload),
        "created": True,
        "content_hash_algorithm": "sha256",
        "content_hash": sha256(payload).hexdigest(),
    }


def test_write_refuses_to_overwrite_existing_file(tmp_path) -> None:
    target = tmp_path / "result.txt"
    target.write_text("original", encoding="utf-8")

    with pytest.raises(TextFileError, match="already exists"):
        WriteTextTool(tmp_path).run(
            _context(), {"path": "result.txt", "content": "replacement"}
        )

    assert target.read_text(encoding="utf-8") == "original"


@pytest.mark.parametrize("path", ("", "/tmp/out.txt", "../out.txt"))
def test_write_rejects_unsafe_paths(tmp_path, path) -> None:
    with pytest.raises(TextFileError):
        WriteTextTool(tmp_path).run(
            _context(), {"path": path, "content": "content"}
        )


def test_write_rejects_symlinked_parent_escape(tmp_path) -> None:
    outside = tmp_path.parent / "outside-write"
    outside.mkdir(exist_ok=True)
    (tmp_path / "escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(TextFileError, match="inside"):
        WriteTextTool(tmp_path).run(
            _context(), {"path": "escape/result.txt", "content": "secret"}
        )


def test_write_rejects_content_over_limit(tmp_path) -> None:
    with pytest.raises(TextFileError, match="limit"):
        WriteTextTool(tmp_path, max_bytes=4).run(
            _context(), {"path": "large.txt", "content": "12345"}
        )
