from demo.display_snapshot import (
    CAMERA_FRAME,
    CAMERA_UNAVAILABLE,
    MOCK_IMAGE,
    TEXT_ONLY,
    RunDisplaySnapshot,
)


def test_snapshot_construction_from_explicit_values():
    snapshot = RunDisplaySnapshot(
        user_input="Ella，我要出门了",
        transcript="Ella，我要出门了",
        captured_frame_reference="mock://frame-1",
        image_status=MOCK_IMAGE,
        scene_summary="Desk scene with phone and keys.",
        visible_items=("phone", "keys"),
        task_goal="Give the user a short reminder before leaving.",
        task_formulation_prompt_text="formulation prompt",
        final_response_prompt_text="final prompt",
        tool_results_summary="camera_scene: phone and keys visible",
        final_response="Remember your phone and keys.",
        memory_status="recorded",
    )

    assert snapshot.user_input == "Ella，我要出门了"
    assert snapshot.image_status == MOCK_IMAGE
    assert snapshot.visible_items == ("phone", "keys")
    assert snapshot.final_response == "Remember your phone and keys."


def test_snapshot_serialization_is_deterministic():
    snapshot = RunDisplaySnapshot(
        user_input="text input",
        transcript=None,
        captured_frame_reference=None,
        image_status=TEXT_ONLY,
        scene_summary="",
        visible_items=("wallet", "phone"),
        task_goal="Answer the user.",
        task_formulation_prompt_text="formulation prompt",
        final_response_prompt_text="final prompt",
        tool_results_summary="",
        final_response="Done.",
        memory_status="not recorded",
    )

    expected = {
        "user_input": "text input",
        "transcript": None,
        "captured_frame_reference": None,
        "image_status": TEXT_ONLY,
        "scene_summary": "",
        "visible_items": ("wallet", "phone"),
        "task_goal": "Answer the user.",
        "task_formulation_prompt_text": "formulation prompt",
        "execution_decision_prompt_text": "",
        "final_response_prompt_text": "final prompt",
        "tool_results_summary": "",
        "final_response": "Done.",
        "memory_status": "not recorded",
        "timing_summary": "",
        "task_id": "",
        "task_state": "",
        "active_step_ids": (),
        "paused_from_state": "",
        "terminal_outcome": "",
        "delivery_status": "",
        "prompt_display_fields": (
            "task_formulation_prompt_text",
            "execution_decision_prompt_text",
            "final_response_prompt_text",
        ),
    }

    assert snapshot.to_dict() == expected
    assert snapshot.to_dict() == expected


def test_prompt_fields_are_present_and_redacted():
    snapshot = RunDisplaySnapshot(
        user_input="hello",
        transcript=None,
        captured_frame_reference=None,
        image_status=TEXT_ONLY,
        scene_summary="",
        visible_items=(),
        task_goal="Answer.",
        task_formulation_prompt_text=(
            "Authorization: Bearer sk-1234567890abcdef1234567890abcdef"
        ),
        final_response_prompt_text=(
            "DASHSCOPE_API_KEY=abcdef1234567890abcdef1234567890"
        ),
        tool_results_summary="",
        final_response="Done.",
        memory_status="not recorded",
    )

    serialized = snapshot.to_dict()

    assert serialized["task_formulation_prompt_text"] == (
        "Authorization: Bearer [REDACTED]"
    )
    assert serialized["final_response_prompt_text"] == "[REDACTED]"
    assert "sk-1234567890abcdef1234567890abcdef" not in str(serialized)
    assert "abcdef1234567890abcdef1234567890" not in str(serialized)
    assert serialized["prompt_display_fields"] == (
        "task_formulation_prompt_text",
        "execution_decision_prompt_text",
        "final_response_prompt_text",
    )


def test_image_status_supports_required_values():
    for image_status in (
        MOCK_IMAGE,
        CAMERA_FRAME,
        CAMERA_UNAVAILABLE,
        TEXT_ONLY,
    ):
        snapshot = RunDisplaySnapshot(
            user_input="hello",
            transcript=None,
            captured_frame_reference=None,
            image_status=image_status,
            scene_summary="",
            visible_items=(),
            task_goal="Answer.",
            task_formulation_prompt_text="",
            final_response_prompt_text="",
            tool_results_summary="",
            final_response="Done.",
            memory_status="not recorded",
        )
        assert snapshot.image_status == image_status


def test_invalid_image_status_raises_clear_error():
    try:
        RunDisplaySnapshot(
            user_input="hello",
            transcript=None,
            captured_frame_reference=None,
            image_status="streaming_camera",
            scene_summary="",
            visible_items=(),
            task_goal="Answer.",
            task_formulation_prompt_text="",
            final_response_prompt_text="",
            tool_results_summary="",
            final_response="Done.",
            memory_status="not recorded",
        )
    except ValueError as error:
        assert "unsupported image_status" in str(error)
    else:
        raise AssertionError("invalid image_status should raise ValueError")


def test_snapshot_does_not_call_runtime_or_providers():
    class ExplodingObject:
        def __str__(self):
            raise AssertionError("snapshot should not call external objects")

        def __getattr__(self, name):
            raise AssertionError(f"unexpected external access: {name}")

    external = ExplodingObject()
    snapshot = RunDisplaySnapshot(
        user_input="hello",
        transcript=None,
        captured_frame_reference=None,
        image_status=TEXT_ONLY,
        scene_summary="",
        visible_items=(),
        task_goal="Answer.",
        task_formulation_prompt_text="",
        final_response_prompt_text="",
        tool_results_summary="",
        final_response="Done.",
        memory_status="not recorded",
    )

    assert snapshot.to_dict()["user_input"] == "hello"
    assert not hasattr(snapshot, "runtime")
    assert not hasattr(snapshot, "provider")
    assert external is external


def test_snapshot_does_not_write_memory():
    snapshot = RunDisplaySnapshot(
        user_input="hello",
        transcript=None,
        captured_frame_reference=None,
        image_status=TEXT_ONLY,
        scene_summary="",
        visible_items=(),
        task_goal="Answer.",
        task_formulation_prompt_text="formulation prompt",
        final_response_prompt_text="final prompt",
        tool_results_summary="",
        final_response="Done.",
        memory_status="recorded",
    )

    serialized = snapshot.to_dict()

    assert not hasattr(snapshot, "write_memory")
    assert not hasattr(snapshot, "memory_manager")
    assert serialized["memory_status"] == "recorded"
    assert "write_memory" not in serialized
