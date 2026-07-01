import base64
from dataclasses import dataclass, field
from typing import Any

from agent.context import AgentExecutionContext
from devices.camera import CameraProvider, MockCameraProvider
from providers.mock import MockMultimodalProvider
from providers.vision import MultimodalProvider

from .base import ToolDefinition, ToolResult


SUPPORTED_DISPLAY_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


class _DisplayFrameReference(str):
    """Keep display data readable while redacting generic text summaries."""

    def __str__(self) -> str:
        return "[display frame omitted]"

    def __repr__(self) -> str:
        return "'[display frame omitted]'"


@dataclass(frozen=True, slots=True)
class CameraSceneTool:
    camera_provider: CameraProvider = field(default_factory=MockCameraProvider)
    multimodal_provider: MultimodalProvider = field(
        default_factory=MockMultimodalProvider
    )
    max_frames: int | None = 3
    max_duration_seconds: int | None = 3
    store_raw_media: bool = False
    name: str = "camera_scene"
    allowed_roles: tuple[str, ...] = ("main_agent",)

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=(
                "Use to capture a bounded visual scene summary when the current "
                "task needs fresh visual context. Do not use for continuous "
                "surveillance, unbounded capture, identity recognition, or when "
                "the task can be answered without visual context. If the task "
                "already has a successful camera_scene observation, do not call "
                "camera_scene again, even when the requested object is missing "
                "or the image is blurred, obstructed, poorly angled, or otherwise "
                "insufficient. Use the existing observation and explain what is "
                "visible, missing, or uncertain."
            ),
            schema_version="1.0",
            input_schema={
                "type": "object",
                "properties": {
                    "task_goal": {
                        "type": "string",
                        "description": "Current task goal supplied by execution.",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Current task session identifier.",
                    },
                    "max_frames": {
                        "type": "number",
                        "description": "Maximum bounded frames to capture.",
                        "minimum": 1,
                        **(
                            {"maximum": self.max_frames}
                            if self.max_frames is not None
                            else {}
                        ),
                    },
                    "max_duration_seconds": {
                        "type": "number",
                        "description": "Maximum bounded capture duration.",
                        "minimum": 1,
                        **(
                            {"maximum": self.max_duration_seconds}
                            if self.max_duration_seconds is not None
                            else {}
                        ),
                    },
                },
                "additionalProperties": False,
            },
            input_examples=(
                {"max_frames": 3, "max_duration_seconds": 3},
            ),
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
                    "frames_captured": {"type": "number"},
                    "providers": {"type": "object"},
                    "captured_frame_reference": {"type": "string"},
                    "error": {"type": "object"},
                },
                "required": ["status", "summary", "frames_captured"],
            },
        )

    def __post_init__(self) -> None:
        if self.max_frames is None and self.max_duration_seconds is None:
            raise ValueError("camera scene capture must be bounded")
        if self.max_frames is not None and self.max_frames < 1:
            raise ValueError("max_frames must be at least 1")
        if (
            self.max_duration_seconds is not None
            and self.max_duration_seconds < 1
        ):
            raise ValueError("max_duration_seconds must be at least 1")

    def run(
        self,
        context: AgentExecutionContext,
        arguments: dict[str, object] | None = None,
    ) -> ToolResult:
        print("[camera_scene.py]: camera is used")
        arguments = arguments or {}
        frame_limit = self._runtime_limit(
            arguments,
            "max_frames",
            self.max_frames,
        )
        duration_limit = self._runtime_limit(
            arguments,
            "max_duration_seconds",
            self.max_duration_seconds,
        )
        frames = []
        for _ in range(frame_limit or 1):
            camera_result = self.camera_provider.capture_frame(
                trace_id=context.trace_id,
                metadata={"max_duration_seconds": duration_limit},
            )
            if camera_result.failed:
                return self._unavailable_result(
                    context,
                    source="camera",
                    code=camera_result.error.code,
                    message=camera_result.error.message,
                    frames_captured=len(frames),
                    summary="Visual context is unavailable.",
                )
            frames.append(camera_result.output)

        multimodal_result = self.multimodal_provider.describe(
            {
                "frames": tuple(frames),
                "task_id": context.task_id,
                "session_id": context.session_id,
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
                frames_captured=len(frames),
                summary="Visual context could not be summarized.",
            )

        output = multimodal_result.output
        payload = {
            "status": "available",
            "summary": output["scene_summary"],
            "visible_items": output.get("visible_items", ()),
            "frames_captured": len(frames),
            "providers": {
                "camera": self.camera_provider.device_name,
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
            session_id=context.session_id,
            trace_id=context.trace_id,
            payload=payload,
        )

    @staticmethod
    def _runtime_limit(
        arguments: dict[str, object],
        name: str,
        configured_limit: int | None,
    ) -> int | None:
        requested = arguments.get(name, configured_limit)
        if requested is None:
            return None
        if isinstance(requested, bool) or not isinstance(requested, (int, float)):
            raise ValueError(f"{name} must be a number")
        if requested < 1:
            raise ValueError(f"{name} must be at least 1")
        if configured_limit is not None and requested > configured_limit:
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
        frames_captured: int,
        summary: str,
    ) -> ToolResult:
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            session_id=context.session_id,
            trace_id=context.trace_id,
            payload={
                "status": "unavailable",
                "summary": summary,
                "error": {
                    "source": source,
                    "code": code,
                    "message": message,
                },
                "frames_captured": frames_captured,
            },
        )
