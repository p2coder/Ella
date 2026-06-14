import inspect
from pathlib import Path

import config.config as user_config
from agent.final_response import FinalResponseGenerator
from demo.cli_demo import DemoRuntime, _build_display_snapshot, _tool_results_summary
from demo.web_ui import render_web_ui_shell
from memory import MemoryManagementRequest, MemoryManager
from prompts.engine import PromptEngine
from providers.base import ProviderResult
from sessions.completion import TaskCompletionPackage
from sessions.output import UserVisibleAgentOutput
from tools.camera_scene import CameraSceneTool

from tests.tools.test_camera_scene_display_frame import (
    SequenceCameraProvider,
    SuccessfulMultimodalProvider,
    make_context,
)


class RecordingLLMProvider:
    provider_name = "recording_llm"
    model_name = "recording-model"

    def __init__(self):
        self.prompts = []

    def generate(self, prompt, *, trace_id=None, metadata=None):
        self.prompts.append(prompt)
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output={"text": "Your phone and keys are visible."},
        )


class TaskResult:
    def __init__(self, completion, memory_result=None):
        self.completion = completion
        self.memory_result = memory_result


def camera_tool(runtime):
    executor = runtime.task_runtime.executor
    assert executor is not None
    tool = executor.tool_manager.registry.get("camera_scene")
    assert isinstance(tool, CameraSceneTool)
    return tool


def make_camera_result():
    return CameraSceneTool(
        camera_provider=SequenceCameraProvider(
            ({"type": "image", "bytes": b"display-frame", "mime_type": "image/jpeg"},)
        ),
        multimodal_provider=SuccessfulMultimodalProvider(),
        max_frames=1,
        store_raw_media=True,
    ).run(make_context())


def test_demo_assembly_passes_configured_raw_media_flag(monkeypatch, tmp_path):
    monkeypatch.setattr(user_config, "DEBUG_STORE_RAW_MEDIA", True)

    tool = camera_tool(DemoRuntime.create_default(tmp_path / "memory.md"))

    assert tool.store_raw_media is True


def test_frame_reference_reaches_snapshot_and_existing_web_ui():
    camera_result = make_camera_result()
    completion = TaskCompletionPackage(
        context=make_context(),
        summary="Completed camera task.",
        user_visible_output=UserVisibleAgentOutput(
            process={"task_goal": "Inspect the scene."},
            final_response="Your phone and keys are visible.",
        ),
        tool_results=(camera_result,),
    )

    snapshot = _build_display_snapshot(
        user_input="What can you see?",
        transcript=None,
        task_result=TaskResult(completion),
    )
    html = render_web_ui_shell(snapshot)

    assert snapshot.captured_frame_reference.startswith("data:image/jpeg;base64,")
    assert '<img class="captured-frame"' in html
    assert snapshot.captured_frame_reference in html


def test_display_frame_does_not_enter_prompt_tool_summary_or_memory(tmp_path: Path):
    camera_result = make_camera_result()
    reference = camera_result.payload["captured_frame_reference"]
    encoded = reference.split(",", 1)[1]
    llm = RecordingLLMProvider()
    generator = FinalResponseGenerator(PromptEngine(), llm)

    generated = generator.generate(
        trace_id="trace-frame",
        user_input="What can you see?",
        task_goal="Inspect the scene.",
        task_constraints=(),
        completion_criteria=("Answer the user.",),
        tool_results=(camera_result,),
        user_preference_summary="Short answers.",
        environment_summary="Indoor scene.",
    )
    completion = TaskCompletionPackage(
        context=make_context(),
        summary="Completed camera task.",
        user_visible_output=UserVisibleAgentOutput(
            process={},
            final_response=generated.final_response,
        ),
        tool_results=(camera_result,),
    )
    memory_path = tmp_path / "memory.md"
    MemoryManager(memory_path).handle(MemoryManagementRequest.from_completion(completion))

    assert encoded not in llm.prompts[0]
    assert encoded not in generated.tool_results_summary
    assert encoded not in _tool_results_summary((camera_result,))
    assert encoded not in memory_path.read_text(encoding="utf-8")


def test_demo_runtime_paths_do_not_bypass_runtime_boundaries():
    source = inspect.getsource(DemoRuntime.run_with_display)
    source += inspect.getsource(DemoRuntime._run_signal_to_completion)

    assert "event_runtime.publish" in source
    assert "task_runtime.run_until_complete" in source
    assert ".capture_frame(" not in source
    assert ".describe(" not in source
