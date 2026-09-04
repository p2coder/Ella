from pathlib import Path

from app_runtime import AppRuntime


def test_default_app_runtime_wires_verification_tool(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("app_runtime.TaskRuntime.start", lambda _runtime: None)

    runtime = AppRuntime.create_default(memory_path=tmp_path / "memory.md")

    tool_manager = runtime._task_runtime.executor.tool_manager
    assert tool_manager.get_tool("artifact_exists") is not None
    assert tool_manager.get_tool("document_read") is not None
    assert tool_manager.get_tool("tool_observation_check") is not None
    verification = tool_manager.get_tool("verification")
    assert verification is not None
    assert verification.verification_agent.llm_provider is runtime._task_runtime.subagent.llm_provider
