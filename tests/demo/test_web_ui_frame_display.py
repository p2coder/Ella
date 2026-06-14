import inspect

from demo.display_snapshot import (
    CAMERA_FRAME,
    CAMERA_UNAVAILABLE,
    RunDisplaySnapshot,
)
from demo.web_ui import render_web_ui_shell


def make_snapshot(
    *,
    captured_frame_reference: str | None,
    image_status: str = CAMERA_FRAME,
    scene_summary: str = "Desk scene with a phone.",
    visible_items: tuple[str, ...] = ("phone", "keys"),
) -> RunDisplaySnapshot:
    return RunDisplaySnapshot(
        user_input="Ella, inspect the scene.",
        transcript=None,
        captured_frame_reference=captured_frame_reference,
        image_status=image_status,
        scene_summary=scene_summary,
        visible_items=visible_items,
        task_goal="Inspect the current scene.",
        task_formulation_prompt_text="TASK PROMPT",
        final_response_prompt_text="FINAL PROMPT",
        tool_results_summary="camera_scene: phone visible",
        final_response="Your phone is visible.",
        memory_status="appended",
    )


def test_web_ui_renders_safe_data_uri_as_captured_frame():
    reference = "data:image/png;base64,iVBORw0KGgo="

    html = render_web_ui_shell(
        make_snapshot(captured_frame_reference=reference)
    )

    assert '<img class="captured-frame"' in html
    assert f'src="{reference}"' in html
    assert 'alt="Captured camera frame"' in html


def test_web_ui_renders_safe_relative_frame_reference():
    reference = "display/frames/task-123.jpg"

    html = render_web_ui_shell(
        make_snapshot(captured_frame_reference=reference)
    )

    assert '<img class="captured-frame"' in html
    assert f'src="{reference}"' in html


def test_web_ui_shows_image_status_when_frame_is_missing():
    html = render_web_ui_shell(
        make_snapshot(
            captured_frame_reference=None,
            image_status=CAMERA_UNAVAILABLE,
        )
    )

    assert '<img class="captured-frame"' not in html
    assert "camera unavailable" in html
    assert "No captured frame is available." in html


def test_mock_reference_uses_placeholder_instead_of_browser_resource_load():
    html = render_web_ui_shell(
        make_snapshot(captured_frame_reference="mock://frame-1")
    )

    assert '<img class="captured-frame"' not in html
    assert 'src="mock://frame-1"' not in html
    assert "mock://frame-1" in html
    assert "camera frame" in html
    assert "No captured frame is available." in html


def test_scene_summary_and_visible_items_are_displayed_near_frame():
    html = render_web_ui_shell(
        make_snapshot(
            captured_frame_reference="data:image/png;base64,iVBORw0KGgo=",
            scene_summary="Phone is on the desk.",
            visible_items=("phone", "keys"),
        )
    )

    vision_start = html.index('<section class="panel vision-panel">')
    vision_end = html.index("</section>", vision_start)
    vision_html = html[vision_start:vision_end]

    assert "Phone is on the desk." in vision_html
    assert "phone, keys" in vision_html


def test_frame_related_text_is_html_escaped():
    html = render_web_ui_shell(
        make_snapshot(
            captured_frame_reference=None,
            image_status=CAMERA_UNAVAILABLE,
            scene_summary="<script>alert('scene')</script>",
            visible_items=("<phone>",),
        )
    )

    assert "<script>" not in html
    assert "&lt;script&gt;alert(&#x27;scene&#x27;)&lt;/script&gt;" in html
    assert "&lt;phone&gt;" in html


def test_serialized_mapping_cannot_inject_unsafe_image_source():
    data = make_snapshot(captured_frame_reference=None).to_dict()
    data["captured_frame_reference"] = 'javascript:alert("frame")'

    html = render_web_ui_shell(data)

    assert "javascript:" not in html
    assert '<img class="captured-frame"' not in html


def test_web_ui_has_no_camera_or_provider_integration():
    import demo.web_ui as web_ui_module

    source = inspect.getsource(web_ui_module)
    template = web_ui_module.TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "CameraSceneTool" not in source
    assert "CameraProvider" not in source
    assert "providers." not in source
    assert "devices." not in source
    assert "getUserMedia" not in template
    assert "navigator.mediaDevices" not in template
    assert "WebSocket" not in template
