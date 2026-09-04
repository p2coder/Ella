import base64
import binascii
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
import re


MOCK_IMAGE = "mock image"
CAMERA_FRAME = "camera frame"
CAMERA_UNAVAILABLE = "camera unavailable"
TEXT_ONLY = "text-only"

SUPPORTED_IMAGE_STATUSES = (
    MOCK_IMAGE,
    CAMERA_FRAME,
    CAMERA_UNAVAILABLE,
    TEXT_ONLY,
)

SAFE_IMAGE_MIME_TYPES = (
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
)
DATA_IMAGE_PATTERN = re.compile(
    r"^data:(image/(?:jpeg|png|webp|gif));base64,([A-Za-z0-9+/]+={0,2})$"
)
MOCK_IMAGE_PATTERN = re.compile(r"^mock://[A-Za-z0-9._-]+$")
DISPLAY_PATH_ROOT = "display"


@dataclass(frozen=True, slots=True)
class RunDisplaySnapshot:
    user_input: str
    transcript: str | None
    captured_frame_reference: str | None
    image_status: str
    scene_summary: str
    visible_items: tuple[str, ...]
    task_goal: str
    tool_results_summary: str
    final_response: str
    memory_status: str
    timing_summary: str = ""
    task_id: str = ""
    task_state: str = ""
    paused_from_state: str = ""
    terminal_outcome: str = ""
    delivery_status: str = ""
    goal_state: str = ""
    terminal_execution_state: str = ""

    def __post_init__(self) -> None:
        if self.image_status not in SUPPORTED_IMAGE_STATUSES:
            raise ValueError(f"unsupported image_status: {self.image_status}")
        if not _is_safe_frame_reference(self.captured_frame_reference):
            raise ValueError(
                "unsafe captured_frame_reference: expected an image data URI "
                "or a controlled display-relative path"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "user_input": self.user_input,
            "transcript": self.transcript,
            "captured_frame_reference": self.captured_frame_reference,
            "image_status": self.image_status,
            "scene_summary": self.scene_summary,
            "visible_items": self.visible_items,
            "task_goal": self.task_goal,
            "tool_results_summary": self.tool_results_summary,
            "final_response": self.final_response,
            "memory_status": self.memory_status,
            "timing_summary": self.timing_summary,
            "task_id": self.task_id,
            "task_state": self.task_state,
            "paused_from_state": self.paused_from_state,
            "terminal_outcome": self.terminal_outcome,
            "delivery_status": self.delivery_status,
            "goal_state": self.goal_state,
            "terminal_execution_state": self.terminal_execution_state,
        }


def _is_safe_frame_reference(reference: str | None) -> bool:
    if reference is None:
        return True
    if not isinstance(reference, str) or not reference:
        return False
    if MOCK_IMAGE_PATTERN.fullmatch(reference):
        return True

    data_match = DATA_IMAGE_PATTERN.fullmatch(reference)
    if data_match is not None:
        mime_type, encoded = data_match.groups()
        if mime_type not in SAFE_IMAGE_MIME_TYPES:
            return False
        try:
            base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            return False
        return True

    if "://" in reference or PureWindowsPath(reference).is_absolute():
        return False
    path = PurePosixPath(reference)
    if path.is_absolute() or ".." in path.parts:
        return False
    return len(path.parts) > 1 and path.parts[0] == DISPLAY_PATH_ROOT
