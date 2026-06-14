from dataclasses import replace

import pytest

from demo.display_snapshot import (
    CAMERA_FRAME,
    CAMERA_UNAVAILABLE,
    TEXT_ONLY,
    RunDisplaySnapshot,
)


def make_snapshot(
    *,
    captured_frame_reference: str | None,
    image_status: str = CAMERA_FRAME,
) -> RunDisplaySnapshot:
    return RunDisplaySnapshot(
        user_input="Ella, inspect the scene.",
        transcript=None,
        captured_frame_reference=captured_frame_reference,
        image_status=image_status,
        scene_summary="Desk scene.",
        visible_items=("phone",),
        task_goal="Inspect the scene.",
        task_formulation_prompt_text="TASK PROMPT",
        final_response_prompt_text="FINAL PROMPT",
        tool_results_summary="camera_scene: phone visible",
        final_response="Your phone is visible.",
        memory_status="appended",
    )


def test_snapshot_accepts_safe_image_data_uri():
    reference = "data:image/png;base64,iVBORw0KGgo="

    snapshot = make_snapshot(captured_frame_reference=reference)

    assert snapshot.captured_frame_reference == reference
    assert snapshot.to_dict()["captured_frame_reference"] == reference


def test_snapshot_accepts_controlled_display_relative_path():
    reference = "display/frames/task-123.jpg"

    snapshot = make_snapshot(captured_frame_reference=reference)

    assert snapshot.captured_frame_reference == reference


def test_snapshot_preserves_safe_mock_reference_for_existing_demo_contract():
    snapshot = make_snapshot(captured_frame_reference="mock://frame-1")

    assert snapshot.captured_frame_reference == "mock://frame-1"


@pytest.mark.parametrize(
    "reference",
    (
        "file:///Users/user/private.jpg",
        "/Users/user/private.jpg",
        "C:\\Users\\user\\private.jpg",
        "display/../private.jpg",
        "../private.jpg",
        "https://example.com/frame.jpg",
    ),
)
def test_snapshot_rejects_unsafe_frame_references(reference: str):
    with pytest.raises(ValueError, match="unsafe captured_frame_reference"):
        make_snapshot(captured_frame_reference=reference)


def test_snapshot_rejects_invalid_or_non_image_data_uri():
    for reference in (
        "data:text/plain;base64,SGVsbG8=",
        "data:image/png;base64,not valid base64!",
        "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=",
    ):
        with pytest.raises(ValueError, match="unsafe captured_frame_reference"):
            make_snapshot(captured_frame_reference=reference)


def test_no_frame_keeps_existing_image_status_values():
    unavailable = make_snapshot(
        captured_frame_reference=None,
        image_status=CAMERA_UNAVAILABLE,
    )
    text_only = replace(unavailable, image_status=TEXT_ONLY)

    assert unavailable.captured_frame_reference is None
    assert unavailable.image_status == CAMERA_UNAVAILABLE
    assert text_only.captured_frame_reference is None
    assert text_only.image_status == TEXT_ONLY


def test_frame_serialization_is_deterministic():
    snapshot = make_snapshot(
        captured_frame_reference="display/frames/task-123.webp"
    )

    first = snapshot.to_dict()
    second = snapshot.to_dict()

    assert first == second
    assert first["captured_frame_reference"] == "display/frames/task-123.webp"


def test_snapshot_frame_contract_has_no_runtime_or_service_dependencies():
    snapshot = make_snapshot(captured_frame_reference=None, image_status=TEXT_ONLY)

    assert not hasattr(snapshot, "runtime")
    assert not hasattr(snapshot, "provider")
    assert not hasattr(snapshot, "device")
    assert not hasattr(snapshot, "tool")
    assert not hasattr(snapshot, "memory_manager")
