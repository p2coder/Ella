import pytest

from agent.context import AgentExecutionContext, CapabilityScope
from tools.verification import (
    ArtifactExistsTool,
    DocumentReadTool,
    ToolObservationCheckTool,
    VerificationTool,
)
from agent.verification import (
    VerificationAction,
    VerificationAgent,
    VerificationVerdict,
)
from tasks.task import Task, TaskGoalState, TaskIntent
from tools import ToolManager


def _context() -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-verifier",
        agent_role="verification_agent",
        parent_agent_id="ella-main",
        task_id="task-verify-tools",
        memory_scope="task_local",
        capability_scope=CapabilityScope(
            "verification_agent",
            (),
            ("artifact_exists", "document_read", "tool_observation_check"),
        ),
    )


def test_artifact_exists_is_confined_to_controlled_root(tmp_path) -> None:
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "result.md").write_text("result", encoding="utf-8")
    tool = ArtifactExistsTool(tmp_path)

    result = tool.run(_context(), {"relative_path": "reports/result.md"})

    assert result.payload == {
        "relative_path": "reports/result.md",
        "exists": True,
        "is_file": True,
    }
    with pytest.raises(ValueError, match="controlled root"):
        tool.run(_context(), {"relative_path": "../secret.txt"})


def test_document_read_is_bounded(tmp_path) -> None:
    (tmp_path / "result.md").write_text("abcdef", encoding="utf-8")
    result = DocumentReadTool(tmp_path, max_bytes=3).run(
        _context(), {"relative_path": "result.md"}
    )

    assert result.payload["content"] == "abc"
    assert result.payload["truncated"] is True


def test_observation_check_reads_persisted_data_without_execution() -> None:
    calls = []

    def read(task_id):
        calls.append(task_id)
        return (
            {"observation_id": "obs-1", "tool_name": "document_write"},
            {"observation_id": "obs-2", "tool_name": "camera_scene"},
        )

    result = ToolObservationCheckTool(read).run(
        _context(), {"tool_name": "document_write"}
    )

    assert calls == ["task-verify-tools"]
    assert result.payload["matched"] is True
    assert result.payload["observations"] == (
        {"observation_id": "obs-1", "tool_name": "document_write"},
    )


def test_verification_definitions_are_read_only_and_have_no_produces_field(tmp_path) -> None:
    tools = (
        ArtifactExistsTool(tmp_path),
        DocumentReadTool(tmp_path),
        ToolObservationCheckTool(lambda _: ()),
    )

    for tool in tools:
        assert tool.definition.side_effecting is False
        assert "produces" not in tool.definition.to_dict()


def test_verification_tool_loads_task_data_from_context() -> None:
    task = Task("task-verify-tools")
    task.intent = TaskIntent(goal="Return a useful answer")
    requested = []

    def read_task(task_id: str) -> Task:
        requested.append(task_id)
        return task

    tool = VerificationTool(read_task, VerificationAgent())
    result = tool.run(_context(), {"candidate_result": "A useful answer"})

    assert requested == ["task-verify-tools"]
    assert result.payload["goal_state"] == "achieved"
    assert result.payload["recoverable"] is False
    assert tool.definition.result_ttl_seconds == 300
    assert set(tool.definition.input_schema["properties"]) == {"candidate_result"}


def test_verification_tool_runs_selected_read_only_check(tmp_path) -> None:
    artifact = tmp_path / "result.md"
    artifact.write_text("verified", encoding="utf-8")
    task = Task("task-verify-tools")
    task.intent = TaskIntent(goal="Create result.md")
    manager = ToolManager({"artifact_exists": 42})
    manager.register(ArtifactExistsTool(tmp_path))

    class SequencedVerifier:
        def __init__(self) -> None:
            self.calls = []

        def decide_candidate(self, task, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return VerificationAction(
                    "CALL_TOOL",
                    "artifact_exists",
                    {"relative_path": "result.md"},
                )
            return VerificationAction(
                "VERIFICATION_VERDICT",
                verdict=VerificationVerdict(
                    TaskGoalState.ACHIEVED,
                    ("artifact exists",),
                    ("result.md",),
                    (),
                    False,
                    "",
                    "Verified.",
                ),
            )

    verifier = SequencedVerifier()
    result = VerificationTool(lambda _: task, verifier, manager).run(
        _context(),
        {"candidate_result": "Created result.md"},
    )

    assert result.payload["goal_state"] == "achieved"
    assert len(result.payload["checks"]) == 1
    check = result.payload["checks"][0]
    assert check["payload"]["exists"] is True
    assert check["tool_use_id"].startswith("tool-use-")
    assert check["called_at"].endswith("Z")
    assert check["completed_at"].endswith("Z")
    assert check["result_ttl_seconds"] == 42
    assert verifier.calls[1]["verification_results"] == result.payload["checks"]
