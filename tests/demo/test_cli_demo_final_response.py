import inspect
from dataclasses import dataclass
from pathlib import Path

import demo.cli_demo as cli_demo
from devices.camera import MockCameraProvider
from providers.base import ProviderResult


def test_default_demo_injects_final_response_generator(monkeypatch, tmp_path: Path):
    provider = RecordingLLMProvider()
    install_demo_factories(monkeypatch, provider)

    runtime = cli_demo.DemoRuntime.create_default(tmp_path / "memory.md")

    assert runtime.task_runtime.final_response_generator is not None
    assert runtime.task_runtime.final_response_generator.llm_provider is provider
    assert runtime.event_runtime.llm_provider is provider


def test_run_demo_final_answer_uses_final_response_generator(
    monkeypatch,
    tmp_path: Path,
):
    provider = RecordingLLMProvider(
        final_response="出门前请带上手机和钥匙；我没有在画面里看到伞，今天可能有雨，建议带伞。"
    )
    install_demo_factories(monkeypatch, provider)

    output = cli_demo.run_demo(
        input_text="Ella，看看当前画面，我要出门了",
        memory_path=tmp_path / "memory.md",
    )
    final_answer = output.split("[Final Answer]\n", 1)[1].split("\n\n[Memory]", 1)[0]

    assert final_answer == (
        "出门前请带上手机和钥匙；我没有在画面里看到伞，今天可能有雨，建议带伞。"
    )
    assert not final_answer.startswith("我已经根据当前信息完成了检查")
    assert "```json" not in final_answer
    assert "camera_scene:" not in final_answer
    assert "mock_weather:" not in final_answer
    assert "任务目标是：" not in final_answer


def test_process_output_can_still_include_runtime_tool_information(
    monkeypatch,
    tmp_path: Path,
):
    provider = RecordingLLMProvider(final_response="自然语言最终回答。")
    install_demo_factories(monkeypatch, provider)

    output = cli_demo.run_demo(
        input_text="Ella，看看当前画面，我要出门了",
        memory_path=tmp_path / "memory.md",
    )
    process = output.split("[Ella Process]\n", 1)[1].split("\n\n[Final Answer]", 1)[0]

    assert "camera_scene" in process
    assert "mock_weather" in process
    assert "mock_checklist" in process
    assert "Visual context:" in process


def test_demo_does_not_directly_call_llm_or_memory_for_final_response():
    source = inspect.getsource(cli_demo.DemoRuntime.create_default)
    source += inspect.getsource(cli_demo.DemoRuntime.run)
    source += inspect.getsource(cli_demo.DemoRuntime.run_input)

    assert ".generate(" not in source
    assert ".handle(" not in source
    assert "TaskSession(" not in source
    assert "CameraSceneTool().run" not in source


def test_python_main_style_run_still_works(monkeypatch, tmp_path: Path):
    provider = RecordingLLMProvider(final_response="自然语言最终回答。")
    install_demo_factories(monkeypatch, provider)

    output = cli_demo.run_demo(memory_path=tmp_path / "memory.md")

    assert "[Ella Process]" in output
    assert "[Final Answer]" in output
    assert "自然语言最终回答。" in output
    assert "[Memory]" in output


def install_demo_factories(monkeypatch, provider):
    class RecordingProviderFactory:
        def llm(self):
            return provider

        def multimodal(self):
            return StaticMultimodalProvider()

    class RecordingDeviceFactory:
        def camera(self):
            return MockCameraProvider()

    monkeypatch.setattr(cli_demo, "ProviderFactory", RecordingProviderFactory)
    monkeypatch.setattr(cli_demo, "DeviceFactory", RecordingDeviceFactory)


@dataclass(frozen=True, slots=True)
class RecordingLLMProvider:
    final_response: str = "出门前请带上手机和钥匙。"
    provider_name: str = "recording_llm"
    model_name: str = "recording-model"

    def generate(self, prompt, *, trace_id=None, metadata=None):
        boundary = (metadata or {}).get("boundary")
        if boundary == "task_formulation":
            output = {
                "goal": "提醒用户出门前需检查的事项。",
                "context_summary": "User is leaving soon.",
            }
        else:
            output = {"text": self.final_response}
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=output,
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True, slots=True)
class StaticMultimodalProvider:
    provider_name: str = "static_multimodal"
    model_name: str = "static-vl"

    def describe(self, inputs, *, trace_id=None, metadata=None):
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output={
                "scene_summary": "```json {\"umbrella_visible\": false} ```",
                "visible_items": ("phone", "keys"),
                "umbrella_visible": False,
            },
            metadata=dict(metadata or {}),
        )
