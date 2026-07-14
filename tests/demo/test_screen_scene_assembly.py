from pathlib import Path

import config.config as user_config
import demo.cli_demo as cli_demo
from devices.screen import MockScreenProvider, RealScreenProvider
from providers.mock import MockMultimodalProvider
from tools.screen_scene import ScreenSceneTool


def screen_scene_tool(runtime):
    executor = runtime.task_runtime.executor
    assert executor is not None
    tool = executor.tool_manager.registry.get("screen_scene")
    assert isinstance(tool, ScreenSceneTool)
    return tool


def test_demo_assembly_registers_screen_scene_tool_with_mock_defaults(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(user_config, "USE_REAL_PROVIDERS", False)

    tool = screen_scene_tool(
        cli_demo.DemoRuntime.create_default(tmp_path / "memory.md")
    )

    assert isinstance(tool.screen_provider, MockScreenProvider)
    assert isinstance(tool.multimodal_provider, MockMultimodalProvider)
    assert "screen_scene" in tool.definition.name


def test_demo_assembly_uses_real_screen_provider_when_real_mode_enabled(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr(user_config, "USE_REAL_PROVIDERS", True)

    tool = screen_scene_tool(
        cli_demo.DemoRuntime.create_default(tmp_path / "memory.md")
    )

    assert isinstance(tool.screen_provider, RealScreenProvider)

