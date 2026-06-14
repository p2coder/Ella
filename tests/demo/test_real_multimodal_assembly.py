import inspect
from pathlib import Path

import config.config as user_config
import demo.cli_demo as cli_demo
from devices.camera import MockCameraProvider, RealCameraProvider
from providers.mock import MockMultimodalProvider
from providers.qwen import QwenMultimodalProvider
from tools.camera_scene import CameraSceneTool


def camera_scene_tool(runtime):
    executor = runtime.task_runtime.executor
    assert executor is not None
    tool = executor.tool_manager.registry.get("camera_scene")
    assert isinstance(tool, CameraSceneTool)
    return tool


def test_default_demo_injects_mock_camera_and_multimodal_providers(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(user_config, "USE_REAL_PROVIDERS", False)

    tool = camera_scene_tool(
        cli_demo.DemoRuntime.create_default(tmp_path / "memory.md")
    )

    assert isinstance(tool.camera_provider, MockCameraProvider)
    assert isinstance(tool.multimodal_provider, MockMultimodalProvider)


def test_real_config_selects_real_visual_providers_without_platform_logic(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(user_config, "USE_REAL_PROVIDERS", True)
    monkeypatch.setattr(user_config, "CAMERA_ENABLED", True)
    monkeypatch.setattr(user_config, "CAMERA_DEVICE", "2")
    monkeypatch.setattr(user_config, "QWEN_API_KEY", "sk-configured")
    monkeypatch.setattr(user_config, "QWEN_LLM_MODEL", "qwen-plus")
    monkeypatch.setattr(
        user_config,
        "QWEN_MULTIMODAL_MODEL",
        "qwen-vl-plus",
    )

    tool = camera_scene_tool(
        cli_demo.DemoRuntime.create_default(tmp_path / "memory.md")
    )

    assert isinstance(tool.camera_provider, RealCameraProvider)
    assert tool.camera_provider.camera_device == "2"
    assert isinstance(tool.multimodal_provider, QwenMultimodalProvider)
    source = inspect.getsource(cli_demo.DemoRuntime.create_default)
    assert "sys.platform" not in source
    assert "platform.system" not in source


def test_demo_assembly_obtains_visual_dependencies_from_factories(
    monkeypatch,
    tmp_path: Path,
):
    camera = MockCameraProvider(device_name="factory_camera")
    multimodal = MockMultimodalProvider(
        provider_name="factory_multimodal"
    )
    calls = []

    class RecordingProviderFactory:
        def llm(self):
            from providers.mock import MockLLMProvider

            calls.append("llm")
            return MockLLMProvider()

        def multimodal(self):
            calls.append("multimodal")
            return multimodal

    class RecordingDeviceFactory:
        def camera(self):
            calls.append("camera")
            return camera

    monkeypatch.setattr(cli_demo, "ProviderFactory", RecordingProviderFactory)
    monkeypatch.setattr(cli_demo, "DeviceFactory", RecordingDeviceFactory)

    tool = camera_scene_tool(
        cli_demo.DemoRuntime.create_default(tmp_path / "memory.md")
    )

    assert calls == ["llm", "multimodal", "camera"]
    assert tool.camera_provider is camera
    assert tool.multimodal_provider is multimodal


def test_demo_run_keeps_runtime_entrypoint_boundary():
    source = inspect.getsource(cli_demo.DemoRuntime.run)

    assert "event_runtime.publish" in source
    assert "task_runtime.run_until_complete" in source
    assert "CameraSceneTool(" not in source
    assert ".capture_frame(" not in source
    assert ".describe(" not in source
    assert "TaskCompletionPackage(" not in source
    assert "MemoryManager(" not in source

