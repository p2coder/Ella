from hashlib import sha256

import pytest

from agent.context import AgentExecutionContext, CapabilityScope
from tools.text_files import EditTextTool, TextFileError


def _context() -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-edit",
        trace_id="trace-edit",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ("edit",)),
    )


def test_edit_replaces_one_match_and_returns_new_hash(tmp_path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("before old after", encoding="utf-8")

    result = EditTextTool(tmp_path).run(
        _context(),
        {"path": "notes.txt", "old_text": "old", "new_text": "new"},
    )

    expected = b"before new after"
    assert target.read_bytes() == expected
    assert result.payload["replacement_count"] == 1
    assert result.payload["content_hash"] == sha256(expected).hexdigest()


@pytest.mark.parametrize(
    ("content", "old_text", "matches"),
    (("one", "missing", 0), ("same same", "same", 2)),
)
def test_edit_requires_exactly_one_match(tmp_path, content, old_text, matches) -> None:
    target = tmp_path / "notes.txt"
    target.write_text(content, encoding="utf-8")

    with pytest.raises(TextFileError, match=rf"found {matches} matches"):
        EditTextTool(tmp_path).run(
            _context(),
            {"path": "notes.txt", "old_text": old_text, "new_text": "new"},
        )

    assert target.read_text(encoding="utf-8") == content


def test_edit_rejects_empty_old_text(tmp_path) -> None:
    (tmp_path / "notes.txt").write_text("content", encoding="utf-8")
    with pytest.raises(TextFileError, match="non-empty"):
        EditTextTool(tmp_path).run(
            _context(), {"path": "notes.txt", "old_text": "", "new_text": "x"}
        )


def test_edit_rejects_path_escape_and_invalid_utf8(tmp_path) -> None:
    with pytest.raises((TextFileError, FileNotFoundError)):
        EditTextTool(tmp_path).run(
            _context(), {"path": "../outside.txt", "old_text": "a", "new_text": "b"}
        )

    (tmp_path / "binary.txt").write_bytes(b"\xff")
    with pytest.raises(TextFileError, match="UTF-8"):
        EditTextTool(tmp_path).run(
            _context(), {"path": "binary.txt", "old_text": "a", "new_text": "b"}
        )


def test_edit_rejects_result_over_limit_without_changing_file(tmp_path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("a", encoding="utf-8")

    with pytest.raises(TextFileError, match="limit"):
        EditTextTool(tmp_path, max_bytes=4).run(
            _context(), {"path": "notes.txt", "old_text": "a", "new_text": "12345"}
        )

    assert target.read_text(encoding="utf-8") == "a"
