import inspect
from dataclasses import dataclass
from pathlib import Path

import demo.app_runtime as app_runtime_module
import demo.cli_demo as cli_demo
from demo.app_runtime import AppRuntime
from demo.display_snapshot import TEXT_ONLY, RunDisplaySnapshot


def make_snapshot() -> RunDisplaySnapshot:
    return RunDisplaySnapshot(
        user_input="Hello Ella",
        transcript=None,
        captured_frame_reference=None,
        image_status=TEXT_ONLY,
        scene_summary="",
        visible_items=(),
        task_goal="Answer the user.",
        task_formulation_prompt_text="TASK PROMPT",
        final_response_prompt_text="FINAL PROMPT",
        tool_results_summary="",
        final_response="Hello.",
        memory_status="recorded",
    )


@dataclass(frozen=True, slots=True)
class FakeDisplayResult:
    output: str
    snapshot: RunDisplaySnapshot
    page_path: Path | None = None


class RecordingDemoRuntime:
    def __init__(self) -> None:
        self.inputs: list[str] = []

    def run_with_display(self, input_text: str):
        self.inputs.append(input_text)
        return FakeDisplayResult("rendered output", make_snapshot())


def test_app_runtime_exposes_text_display_entrypoint():
    demo_runtime = RecordingDemoRuntime()
    runtime = AppRuntime(demo_runtime)

    result = runtime.run_text_with_display("Hello Ella")

    assert result.snapshot == make_snapshot()
    assert result.output == "rendered output"
    assert demo_runtime.inputs == ["Hello Ella"]


def test_app_runtime_create_default_uses_existing_demo_assembly(tmp_path: Path):
    runtime = AppRuntime.create_default(tmp_path / "memory.md")

    assert isinstance(runtime, AppRuntime)
    assert not hasattr(runtime, "event_runtime")
    assert not hasattr(runtime, "task_runtime")
    assert not hasattr(runtime, "tool_manager")
    assert not hasattr(runtime, "provider_factory")
    assert not hasattr(runtime, "memory_manager")


def test_cli_demo_default_path_runs_through_app_runtime(monkeypatch, tmp_path: Path):
    calls: list[tuple[Path, str]] = []

    class RecordingAppRuntime:
        @classmethod
        def create_default(cls, memory_path: Path):
            instance = cls()
            instance.memory_path = memory_path
            return instance

        def run_text_with_display(self, input_text: str):
            calls.append((self.memory_path, input_text))
            return FakeDisplayResult("facade output", make_snapshot())

    monkeypatch.setattr(app_runtime_module, "AppRuntime", RecordingAppRuntime)

    output = cli_demo.run_demo(
        input_text="Hello from CLI",
        memory_path=tmp_path / "memory.md",
    )

    assert output == "facade output"
    assert calls == [(tmp_path / "memory.md", "Hello from CLI")]


def test_explicit_demo_runtime_injection_remains_compatible():
    class RecordingRuntime:
        def run(self, input_text: str) -> str:
            return f"legacy injection: {input_text}"

    output = cli_demo.run_demo(
        input_text="Injected",
        runtime=RecordingRuntime(),
    )

    assert output == "legacy injection: Injected"


def test_app_runtime_delegates_instead_of_bypassing_runtime_boundaries():
    source = inspect.getsource(AppRuntime)

    assert "run_with_display" in source
    assert "EventRuntime" not in source
    assert "TaskRuntime" not in source
    assert "TaskSession" not in source
    assert "CameraSceneTool" not in source
    assert "LLMProvider" not in source
    assert "MemoryManager" not in source


def test_web_ui_is_not_part_of_app_runtime_facade():
    source = inspect.getsource(app_runtime_module)

    assert "demo.web_ui" not in source
    assert "LocalWebUIShell" not in source
