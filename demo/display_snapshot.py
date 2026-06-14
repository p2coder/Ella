from dataclasses import dataclass
from typing import ClassVar

from prompts.engine import redact_prompt_text


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


@dataclass(frozen=True, slots=True)
class RunDisplaySnapshot:
    user_input: str
    transcript: str | None
    captured_frame_reference: str | None
    image_status: str
    scene_summary: str
    visible_items: tuple[str, ...]
    task_goal: str
    task_formulation_prompt_text: str
    final_response_prompt_text: str
    tool_results_summary: str
    final_response: str
    memory_status: str

    prompt_display_fields: ClassVar[tuple[str, str]] = (
        "task_formulation_prompt_text",
        "final_response_prompt_text",
    )

    def __post_init__(self) -> None:
        if self.image_status not in SUPPORTED_IMAGE_STATUSES:
            raise ValueError(f"unsupported image_status: {self.image_status}")
        object.__setattr__(
            self,
            "task_formulation_prompt_text",
            redact_prompt_text(self.task_formulation_prompt_text),
        )
        object.__setattr__(
            self,
            "final_response_prompt_text",
            redact_prompt_text(self.final_response_prompt_text),
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
            "task_formulation_prompt_text": self.task_formulation_prompt_text,
            "final_response_prompt_text": self.final_response_prompt_text,
            "tool_results_summary": self.tool_results_summary,
            "final_response": self.final_response,
            "memory_status": self.memory_status,
            "prompt_display_fields": self.prompt_display_fields,
        }
