from agent.context import AgentExecutionContext, CapabilityScope
from devices.microphone import DeviceError, DeviceResult
from providers.base import ProviderError, ProviderResult
from tools.camera_scene import CameraSceneTool


def make_context() -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-frame",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ("camera_scene",)),
        permissions=("read_context",),
    )


class SequenceCameraProvider:
    device_name = "sequence_camera"

    def __init__(self, frames):
        self.frames = list(frames)
        self.capture_count = 0

    def capture_frame(self, *, task_id=None, metadata=None):
        output = self.frames[self.capture_count]
        self.capture_count += 1
        return DeviceResult(
            device_name=self.device_name,
            task_id=task_id,
            output=output,
        )


class SuccessfulMultimodalProvider:
    provider_name = "recording_multimodal"
    model_name = "recording-model"

    def __init__(self):
        self.frames = None

    def describe(self, inputs, *, task_id=None, metadata=None):
        self.frames = inputs["frames"]
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            task_id=task_id,
            output={
                "scene_summary": "Phone and keys are visible.",
                "visible_items": ("phone", "keys"),
            },
        )


class FailingCameraProvider:
    device_name = "failing_camera"

    def capture_frame(self, *, task_id=None, metadata=None):
        return DeviceResult(
            device_name=self.device_name,
            task_id=task_id,
            output=None,
            error=DeviceError(
                device_name=self.device_name,
                message="camera unavailable",
                code="device_unavailable",
            ),
        )


class FailingMultimodalProvider:
    provider_name = "failing_multimodal"
    model_name = "failing-model"

    def describe(self, inputs, *, task_id=None, metadata=None):
        return ProviderResult(
            provider_name=self.provider_name,
            model_name=self.model_name,
            task_id=task_id,
            output=None,
            error=ProviderError(
                provider_name=self.provider_name,
                message="multimodal unavailable",
                code="provider_unavailable",
            ),
        )


def test_enabled_display_storage_adds_first_jpeg_as_safe_data_uri():
    camera = SequenceCameraProvider(
        (
            {"type": "image", "bytes": b"first-frame", "mime_type": "image/jpeg"},
            {"type": "image", "bytes": b"second-frame", "mime_type": "image/jpeg"},
        )
    )
    multimodal = SuccessfulMultimodalProvider()
    tool = CameraSceneTool(
        camera_provider=camera,
        multimodal_provider=multimodal,
        max_frames=2,
        store_raw_media=True,
    )

    result = tool.run(make_context())

    reference = result.payload["captured_frame_reference"]
    assert reference.startswith("data:image/jpeg;base64,")
    assert reference.endswith("Zmlyc3QtZnJhbWU=")
    assert "c2Vjb25kLWZyYW1l" not in reference
    assert multimodal.frames == tuple(camera.frames)
    assert result.payload["summary"] == "Phone and keys are visible."
    assert result.payload["visible_items"] == ("phone", "keys")
    assert "frames" not in result.payload


def test_disabled_display_storage_does_not_add_frame_reference():
    tool = CameraSceneTool(
        camera_provider=SequenceCameraProvider(
            ({"type": "image", "bytes": b"frame", "mime_type": "image/jpeg"},)
        ),
        multimodal_provider=SuccessfulMultimodalProvider(),
        max_frames=1,
        store_raw_media=False,
    )

    result = tool.run(make_context())

    assert "captured_frame_reference" not in result.payload


def test_unsupported_image_mime_type_is_not_exposed_for_display():
    tool = CameraSceneTool(
        camera_provider=SequenceCameraProvider(
            ({"type": "image", "bytes": b"frame", "mime_type": "image/svg+xml"},)
        ),
        multimodal_provider=SuccessfulMultimodalProvider(),
        max_frames=1,
        store_raw_media=True,
    )

    result = tool.run(make_context())

    assert "captured_frame_reference" not in result.payload


def test_camera_failure_does_not_expose_frame_reference():
    result = CameraSceneTool(
        camera_provider=FailingCameraProvider(),
        multimodal_provider=SuccessfulMultimodalProvider(),
        store_raw_media=True,
    ).run(make_context())

    assert result.payload["status"] == "unavailable"
    assert "captured_frame_reference" not in result.payload


def test_multimodal_failure_does_not_expose_captured_media():
    result = CameraSceneTool(
        camera_provider=SequenceCameraProvider(
            ({"type": "image", "bytes": b"private-frame", "mime_type": "image/jpeg"},)
        ),
        multimodal_provider=FailingMultimodalProvider(),
        max_frames=1,
        store_raw_media=True,
    ).run(make_context())

    assert result.payload["status"] == "unavailable"
    assert "captured_frame_reference" not in result.payload
    assert b"private-frame" not in repr(result.payload).encode()
