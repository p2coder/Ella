from dataclasses import dataclass, field

from agent.context import AgentExecutionContext
from devices.camera import CameraProvider, MockCameraProvider
from providers.mock import MockMultimodalProvider
from providers.vision import MultimodalProvider

from .base import ToolResult


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

    def run(self, context: AgentExecutionContext) -> ToolResult:
        frames = []
        frame_limit = self.max_frames or 1
        for _ in range(frame_limit):
            camera_result = self.camera_provider.capture_frame(
                trace_id=context.trace_id
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
            "umbrella_visible": output.get("umbrella_visible"),
            "frames_captured": len(frames),
            "providers": {
                "camera": self.camera_provider.device_name,
                "multimodal": self.multimodal_provider.provider_name,
            },
            "raw_media_stored": self.store_raw_media,
        }
        if self.store_raw_media:
            payload["frames"] = tuple(frames)
        return ToolResult(
            tool_name=self.name,
            task_id=context.task_id,
            session_id=context.session_id,
            trace_id=context.trace_id,
            payload=payload,
        )

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
