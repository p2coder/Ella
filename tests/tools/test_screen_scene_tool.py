from agent.context import AgentExecutionContext
from devices.microphone import DeviceError, DeviceResult
from providers.base import ProviderError, ProviderResult
from providers.mock import MockMultimodalProvider
from tools.base import ToolResult
from tools.screen_scene import ScreenSceneTool


def make_context() -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        session_id="session-screen",
        task_id="task-screen",
        trace_id="trace-screen",
        handoff_goal="Identify what is currently visible on my screen.",
        memory_scope="task_local",
        allowed_tools=("screen_scene",),
        permissions=("read_context",),
    )


def test_screen_scene_tool_definition_is_self_describing():
    definition = ScreenSceneTool().definition

    assert definition.name == "screen_scene"
    assert "current screen" in definition.description.lower()
    assert definition.input_schema["type"] == "object"
    assert definition.output_schema["type"] == "object"
    assert "max_screenshots" in definition.input_schema["properties"]


def test_screen_scene_captures_bounded_screenshot_and_calls_multimodal():
    provider = RecordingMultimodalProvider()
    screen = CountingScreenProvider()
    tool = ScreenSceneTool(
        screen_provider=screen,
        multimodal_provider=provider,
        max_screenshots=1,
    )

    result = tool.run(make_context(), arguments={"max_screenshots": 1})

    assert isinstance(result, ToolResult)
    assert result.tool_name == "screen_scene"
    assert screen.capture_count == 1
    assert provider.calls == [
        {
            "frames": (
                {
                    "type": "image",
                    "bytes": b"screen-frame-1",
                    "mime_type": "image/png",
                    "source": "screen",
                },
            ),
            "task_id": "task-screen",
            "session_id": "session-screen",
            "handoff_goal": "Identify what is currently visible on my screen.",
        }
    ]
    assert result.payload["status"] == "available"
    assert result.payload["summary"] == "Screen shows an editor window."
    assert result.payload["visible_items"] == ("editor", "terminal")
    assert result.payload["screenshots_captured"] == 1


def test_screen_scene_rejects_unbounded_configuration():
    import pytest

    with pytest.raises(ValueError, match="bounded"):
        ScreenSceneTool(max_screenshots=None)


def test_screen_scene_rejects_runtime_limit_above_configured_bound():
    import pytest

    tool = ScreenSceneTool(max_screenshots=1)

    with pytest.raises(ValueError, match="configured limit"):
        tool.run(make_context(), arguments={"max_screenshots": 2})


def test_screen_unavailable_returns_safe_tool_result():
    tool = ScreenSceneTool(
        screen_provider=UnavailableScreenProvider(),
        multimodal_provider=MockMultimodalProvider(),
    )

    result = tool.run(make_context())

    assert result.payload == {
        "status": "unavailable",
        "summary": "Screen context is unavailable.",
        "error": {
            "source": "screen",
            "code": "permission_denied",
            "message": "screen capture permission was denied",
        },
        "screenshots_captured": 0,
    }


def test_multimodal_failure_returns_structured_screen_result():
    tool = ScreenSceneTool(
        screen_provider=CountingScreenProvider(),
        multimodal_provider=FailingMultimodalProvider(),
    )

    result = tool.run(make_context())

    assert result.payload == {
        "status": "unavailable",
        "summary": "Screen context could not be summarized.",
        "error": {
            "source": "multimodal_provider",
            "code": "provider_unavailable",
            "message": "multimodal unavailable",
        },
        "screenshots_captured": 1,
    }


class CountingScreenProvider:
    device_name = "counting_screen"

    def __init__(self) -> None:
        self.capture_count = 0

    def capture_screen(self, *, trace_id=None, metadata=None):
        self.capture_count += 1
        return DeviceResult(
            device_name=self.device_name,
            trace_id=trace_id,
            output={
                "type": "image",
                "bytes": f"screen-frame-{self.capture_count}".encode(),
                "mime_type": "image/png",
                "source": "screen",
            },
            metadata=dict(metadata or {}),
        )


class UnavailableScreenProvider:
    device_name = "unavailable_screen"

    def capture_screen(self, *, trace_id=None, metadata=None):
        return DeviceResult(
            device_name=self.device_name,
            trace_id=trace_id,
            output=None,
            error=DeviceError(
                device_name=self.device_name,
                message="screen capture permission was denied",
                code="permission_denied",
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
                "scene_summary": "Screen shows an editor window.",
                "visible_items": ("editor", "terminal"),
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
