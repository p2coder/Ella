from pathlib import Path

from app_runtime import AppRuntime


def test_default_app_runtime_wires_verification_agent_and_tools(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("app_runtime.TaskRuntime.start", lambda _runtime: None)

    runtime = AppRuntime.create_default(memory_path=tmp_path / "memory.md")

    verifier = runtime._task_runtime.verification_agent
    assert verifier is not None
    assert verifier.llm_provider is runtime._event_runtime.llm_provider

    tool_manager = runtime._task_runtime.executor.tool_manager
    assert tool_manager.get_tool("artifact_exists") is not None
    assert tool_manager.get_tool("document_read") is not None
    assert tool_manager.get_tool("tool_observation_check") is not None
