import base64
from dataclasses import dataclass, field
from typing import Any

from agent.context import AgentExecutionContext
from devices.screen import MockScreenProvider, ScreenProvider
from providers.mock import MockMultimodalProvider
from providers.vision import MultimodalProvider

from .base import ToolDefinition, ToolResult
from .camera_scene import SUPPORTED_DISPLAY_MIME_TYPES, _DisplayFrameReference


@dataclass(frozen=True, slots=True)
class ScreenSceneTool:
    screen_provider: ScreenProvider = field(default_factory=MockScreenProvider)
    multimodal_provider: MultimodalProvider = field(
        default_factory=MockMultimodalProvider
    )
    max_screenshots: int | None = 1
    store_raw_media: bool = False
    name: str = "screen_scene"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Purpose: Capture the current screen and summarize visible app, "
                "window, document, web page, or UI content through a multimodal "
                "model. Use when: The request depends on what is currently visible "
                "on screen, including an on-screen error or UI guidance. Do not "
                "use when: The request concerns the physical room, hidden windows, "
                "credentials, continuous monitoring, or can be answered without "
                "screen context. Execution behavior: Capture only the configured "
                "bounded number of screenshots. Failure and limitations: The result "
                "covers visible screen content only and cannot establish what is "
                "hidden, occluded, or outside the captured display."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {
                    "task_goal": {
                        "type": "string",
                        "description": "Current task goal supplied by execution.",
                    },
                    "max_screenshots": {
                        "type": "number",
                        "description": "Maximum bounded screenshots to capture.",
                        "minimum": 1,
                        **(
                            {"maximum": self.max_screenshots}
                            if self.max_screenshots is not None
                            else {}
                        ),
                    },
                },
                "additionalProperties": False,
            },
            input_examples=({"max_screenshots": 1},),
            output_schema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["available", "unavailable"],
                    },
                    "summary": {"type": "string"},
                    "visible_items": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "screenshots_captured": {"type": "number"},
                    "providers": {"type": "object"},
                    "captured_frame_reference": {"type": "string"},
                    "error": {"type": "object"},
                },
                "required": ["status", "summary", "screenshots_captured"],
            },
        )

    def __post_init__(self) -> None:
        if self.max_screenshots is None:
            raise ValueError("screen scene capture must be bounded")
        if self.max_screenshots < 1:
            raise ValueError("max_screenshots must be at least 1")

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict[str, object] | None = None,
    ) -> ToolResult:
        arguments = arguments or {}
        screenshot_limit = self._runtime_limit(
            arguments,
            "max_screenshots",
            self.max_screenshots,
        )
        frames = []
        for _ in range(screenshot_limit):
            screen_result = self.screen_provider.capture_screen(
                trace_id=context.trace_id,
                metadata={"max_screenshots": screenshot_limit},
            )
            if screen_result.failed:
                return self._unavailable_result(
                    context,
                    source="screen",
                    code=screen_result.error.code,
                    message=screen_result.error.message,
                    screenshots_captured=len(frames),
                    summary="Screen context is unavailable.",
                )
            frames.append(screen_result.output)

        multimodal_result = self.multimodal_provider.describe(
            {
                "frames": tuple(frames),
                "task_id": context.task_id,
                "handoff_goal": context.handoff_goal,
            },
            trace_id=context.trace_id,
        )
        if multimodal_result.failed:
            return self._unavailable_result(
                context,
                source="multimodal_provider",
                code=multimodal_result.error.code,
                message=multimodal_result.error.message,
                screenshots_captured=len(frames),
                summary="Screen context could not be summarized.",
            )

        output = multimodal_result.output
        payload = {
            "status": "available",
            "summary": output["scene_summary"],
            "visible_items": output.get("visible_items", ()),
            "screenshots_captured": len(frames),
            "providers": {
                "screen": self.screen_provider.device_name,
                "multimodal": self.multimodal_provider.provider_name,
            },
            "raw_media_stored": self.store_raw_media,
        }
        if self.store_raw_media:
            display_reference = self._display_frame_reference(frames[0])
            if display_reference is not None:
                payload["captured_frame_reference"] = display_reference
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            trace_id=context.trace_id,
            payload=payload,
        )

    @staticmethod
    def _runtime_limit(
        arguments: dict[str, object],
        name: str,
        configured_limit: int,
    ) -> int:
        requested = arguments.get(name, configured_limit)
        if isinstance(requested, bool) or not isinstance(requested, (int, float)):
            raise ValueError(f"{name} must be a number")
        if requested < 1:
            raise ValueError(f"{name} must be at least 1")
        if requested > configured_limit:
            raise ValueError(
                f"{name} must not exceed configured limit {configured_limit}"
            )
        return int(requested)

    @staticmethod
    def _display_frame_reference(frame: Any) -> str | None:
        if not isinstance(frame, dict):
            return None
        mime_type = frame.get("mime_type")
        encoded_bytes = frame.get("bytes")
        if mime_type not in SUPPORTED_DISPLAY_MIME_TYPES:
            return None
        if not isinstance(encoded_bytes, (bytes, bytearray, memoryview)):
            return None
        encoded = base64.b64encode(bytes(encoded_bytes)).decode("ascii")
        return _DisplayFrameReference(f"data:{mime_type};base64,{encoded}")

    def _unavailable_result(
        self,
        context: AgentExecutionContext,
        *,
        source: str,
        code: str,
        message: str,
        screenshots_captured: int,
        summary: str,
    ) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            trace_id=context.trace_id,
            payload={
                "status": "unavailable",
                "summary": summary,
                "error": {
                    "source": source,
                    "code": code,
                    "message": message,
                },
                "screenshots_captured": screenshots_captured,
            },
        )
