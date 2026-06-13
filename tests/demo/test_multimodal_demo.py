import inspect
from pathlib import Path

import config.config as user_config
from demo.cli_demo import DemoRuntime, run_demo
from devices.camera import MockCameraProvider
from providers.mock import MockLLMProvider, MockMultimodalProvider
from tools import ToolManager
from tools.camera_scene import CameraSceneTool


def test_demo_assembly_registers_mock_camera_scene_tool(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(user_config, "USE_REAL_PROVIDERS", False)

    runtime = DemoRuntime.create_default(tmp_path / "memory.md")
    executor = runtime.task_runtime.executor
    assert executor is not None

    tool = executor.tool_manager.registry.get("camera_scene")

    assert isinstance(runtime.event_runtime.llm_provider, MockLLMProvider)
    assert isinstance(tool, CameraSceneTool)
    assert isinstance(tool.camera_provider, MockCameraProvider)
    assert isinstance(tool.multimodal_provider, MockMultimodalProvider)
    assert "camera_scene" in runtime.task_runtime.session_manager.allowed_tools


def test_camera_scene_is_not_registered_globally():
    assert "camera_scene" not in ToolManager().list_names()


def test_multimodal_going_out_demo_includes_visual_context(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(user_config, "USE_REAL_PROVIDERS", False)

    output = run_demo(
        input_text="Ella，看看当前画面，我要出门了",
        memory_path=tmp_path / "memory.md",
    )

    assert "Mock scene contains phone, keys, wallet." in output
    assert "camera_scene" in output
    assert "[Ella Process]" in output
    assert "[Final Answer]" in output
    assert "[Memory]" in output


def test_demo_uses_runtime_entrypoints_for_multimodal_flow():
    source = inspect.getsource(DemoRuntime.run)

    assert "event_runtime.publish" in source
    assert "task_runtime.run_until_complete" in source
    for forbidden_call in (
        "TaskSession(",
        "select_strategy(",
        "CameraSceneTool(",
        ".execute(",
        "TaskCompletionPackage(",
        "MemoryManager(",
        ".handle(",
    ):
        assert forbidden_call not in source
