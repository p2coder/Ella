from pathlib import Path

import pytest

from agent.context import AgentExecutionContext
from config.settings import load_settings
from tools.base import ToolIdempotency, ToolUncertainPolicy
from tools.document_write import DocumentWriteTool, MAX_DOCUMENT_BYTES


def _context() -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-document",
        trace_id="trace-document",
        handoff_goal="Write a report",
        memory_scope="task_local",
        allowed_tools=("document_write",),
        permissions=("write_document",),
    )


def test_definition_describes_controlled_document_writes(tmp_path: Path) -> None:
    definition = DocumentWriteTool(tmp_path).definition

    assert definition.name == "document_write"
    assert definition.side_effecting is True
    assert definition.idempotency is ToolIdempotency.NON_IDEMPOTENT
    assert (
        definition.uncertain_policy
        is ToolUncertainPolicy.POSSIBLE_AFTER_DISPATCH
    )
    assert definition.input_schema["required"] == ["relative_path", "content"]
    assert definition.input_schema["additionalProperties"] is False


def test_document_directory_can_be_configured_centrally(tmp_path: Path) -> None:
    settings = load_settings({"ELLA_DOCUMENT_DIRECTORY": tmp_path})

    assert settings.document_directory == tmp_path.resolve()


def test_writes_utf8_document_below_configured_root(tmp_path: Path) -> None:
    tool = DocumentWriteTool(tmp_path)
    content = "# Ella competition analysis\n\n结论。\n"

    result = tool.run(
        _context(),
        {
            "relative_path": "reports/competition.md",
            "content": content,
        },
    )

    assert (tmp_path / "reports" / "competition.md").read_text() == content
    assert result.payload["status"] == "written"
    assert result.payload["relative_path"] == "reports/competition.md"
    assert result.payload["bytes_written"] == len(content.encode("utf-8"))
    assert result.payload["overwritten"] is False
    assert len(result.payload["sha256"]) == 64
    assert list((tmp_path / "reports").glob("*.tmp")) == []


def test_existing_document_requires_explicit_overwrite(tmp_path: Path) -> None:
    tool = DocumentWriteTool(tmp_path)
    arguments = {"relative_path": "report.md", "content": "first"}
    tool.run(_context(), arguments)

    with pytest.raises(ValueError, match="already exists"):
        tool.run(_context(), {**arguments, "content": "second"})

    result = tool.run(
        _context(),
        {**arguments, "content": "second", "overwrite": True},
    )
    assert result.payload["overwritten"] is True
    assert (tmp_path / "report.md").read_text() == "second"


@pytest.mark.parametrize(
    "relative_path",
    (
        "/tmp/report.md",
        "../report.md",
        "reports/../../report.md",
        "reports\\report.md",
        "report.py",
    ),
)
def test_rejects_unsafe_or_unsupported_paths(
    tmp_path: Path,
    relative_path: str,
) -> None:
    with pytest.raises(ValueError):
        DocumentWriteTool(tmp_path).run(
            _context(),
            {"relative_path": relative_path, "content": "report"},
        )


def test_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic links"):
        DocumentWriteTool(tmp_path).run(
            _context(),
            {"relative_path": "linked/report.md", "content": "report"},
        )
    assert not (outside / "report.md").exists()


def test_rejects_documents_above_size_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="document limit"):
        DocumentWriteTool(tmp_path).run(
            _context(),
            {
                "relative_path": "large.txt",
                "content": "x" * (MAX_DOCUMENT_BYTES + 1),
            },
        )
