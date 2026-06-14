import pytest

from agent.context import AgentExecutionContext
from devices.camera import MockCameraProvider
from devices.microphone import DeviceError, DeviceResult
from providers.base import ProviderError, ProviderResult
from providers.mock import MockMultimodalProvider
from tools.camera_scene import CameraSceneTool
from tools.base import ToolResult


def make_context() -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        session_id="session-camera",
        task_id="task-camera",
        trace_id="trace-camera",
        handoff_goal="Give the user a short, necessary reminder before leaving.",
        memory_scope="task_local",
        allowed_tools=("camera_scene",),
        permissions=("read_context",),
    )


def test_camera_scene_tool_captures_bounded_frames_with_max_frames():
    camera = CountingCameraProvider()
    tool = CameraSceneTool(
        camera_provider=camera,
        multimodal_provider=RecordingMultimodalProvider(),
        max_frames=2,
    )

    result = tool.run(make_context())

    assert isinstance(result, ToolResult)
    assert result.tool_name == "camera_scene"
    assert result.task_id == "task-camera"
    assert result.session_id == "session-camera"
    assert result.trace_id == "trace-camera"
    assert camera.capture_count == 2


def test_unbounded_capture_configuration_is_rejected():
    with pytest.raises(ValueError, match="bounded"):
        CameraSceneTool(max_frames=None, max_duration_seconds=None)


def test_multimodal_provider_called_with_captured_frames():
    provider = RecordingMultimodalProvider()
    tool = CameraSceneTool(
        camera_provider=CountingCameraProvider(),
        multimodal_provider=provider,
        max_frames=3,
    )

    tool.run(make_context())

    assert provider.calls == [
        {
            "frames": (
                {"type": "image", "frame": "frame-1"},
                {"type": "image", "frame": "frame-2"},
                {"type": "image", "frame": "frame-3"},
            ),
            "task_id": "task-camera",
            "session_id": "session-camera",
            "handoff_goal": (
                "Give the user a short, necessary reminder before leaving."
            ),
        }
    ]


def test_tool_result_contains_scene_summary():
    tool = CameraSceneTool(
        camera_provider=MockCameraProvider(),
        multimodal_provider=MockMultimodalProvider(
            visible_items=("phone", "keys", "umbrella")
        ),
    )

    result = tool.run(make_context())

    assert result.payload["status"] == "available"
    assert result.payload["summary"] == "Mock scene contains phone, keys, umbrella."
    assert result.payload["visible_items"] == ("phone", "keys", "umbrella")
    assert "umbrella_visible" not in result.payload


def test_camera_unavailable_returns_safe_tool_result():
    tool = CameraSceneTool(
        camera_provider=UnavailableCameraProvider(),
        multimodal_provider=MockMultimodalProvider(),
    )

    result = tool.run(make_context())

    assert result.payload == {
        "status": "unavailable",
        "summary": "Visual context is unavailable.",
        "error": {
            "source": "camera",
            "code": "device_unavailable",
            "message": "camera unavailable",
        },
        "frames_captured": 0,
    }


def test_multimodal_failure_returns_structured_tool_result():
    tool = CameraSceneTool(
        camera_provider=MockCameraProvider(),
        multimodal_provider=FailingMultimodalProvider(),
    )

    result = tool.run(make_context())

    assert result.payload == {
        "status": "unavailable",
        "summary": "Visual context could not be summarized.",
        "error": {
            "source": "multimodal_provider",
            "code": "provider_unavailable",
            "message": "multimodal unavailable",
        },
        "frames_captured": 3,
    }


def test_default_tool_uses_mock_providers_and_does_not_store_raw_media():
    tool = CameraSceneTool()

    result = tool.run(make_context())

    assert result.payload["status"] == "available"
    assert result.payload["providers"] == {
        "camera": "mock_camera",
        "multimodal": "mock_multimodal",
    }
    assert "frames" not in result.payload
    assert result.payload["raw_media_stored"] is False


def test_tool_has_no_global_registration_side_effects():
    from registries.tool_registry import ToolRegistry

    registry = ToolRegistry()

    assert registry.get("camera_scene") is None

    tool = CameraSceneTool()
    registry.register(tool)

    assert registry.get("camera_scene") is tool


class CountingCameraProvider:
    device_name = "counting_camera"

    def __init__(self) -> None:
        self.capture_count = 0

    def capture_frame(self, *, trace_id=None, metadata=None):
        self.capture_count += 1
        return DeviceResult(
            device_name=self.device_name,
            trace_id=trace_id,
            output={"type": "image", "frame": f"frame-{self.capture_count}"},
        )


class UnavailableCameraProvider:
    device_name = "unavailable_camera"

    def capture_frame(self, *, trace_id=None, metadata=None):
        return DeviceResult(
            device_name=self.device_name,
            trace_id=trace_id,
            output=None,
            error=DeviceError(
                device_name=self.device_name,
                message="camera unavailable",
                code="device_unavailable",
            ),
        )


class RecordingMultimodalProvider:
    provider_name = "recording_multimodal"
    model_name = "recording-mm"

    def __init__(self) -> None:
        self.calls = []

    def describe(self, inputs, *, trace_id=None, metadata=None):
        self.calls.append(inputs)
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output={
                "scene_summary": "Recorded frames summarized.",
                "visible_items": ("phone",),
            },
        )


class FailingMultimodalProvider:
    provider_name = "failing_multimodal"
    model_name = "failing-mm"

    def describe(self, inputs, *, trace_id=None, metadata=None):
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            trace_id=trace_id,
            output=None,
            error=ProviderError(
                provider_name=self.provider_name,
                message="multimodal unavailable",
                code="provider_unavailable",
            ),
        )
