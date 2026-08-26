from demo.display_snapshot import CAMERA_FRAME, RunDisplaySnapshot
from demo.page_viewer import LocalPageViewer, render_snapshot_html


def make_snapshot() -> RunDisplaySnapshot:
    return RunDisplaySnapshot(
        user_input="Ella，我要出门了",
        transcript="Ella，我要出门了",
        captured_frame_reference="mock://frame-1",
        image_status=CAMERA_FRAME,
        scene_summary="Desk scene with phone and keys.",
        visible_items=("phone", "keys"),
        task_goal="Give the user a short reminder before leaving.",
        final_response_prompt_text="FINAL RESPONSE PROMPT",
        tool_results_summary="camera_scene: phone and keys visible",
        final_response="Remember your phone and keys.",
        memory_status="recorded",
    )


def test_page_viewer_renders_required_sections():
    html = render_snapshot_html(make_snapshot())

    assert "Input" in html
    assert "Vision" in html
    assert "Prompt Sent to LLM" in html
    assert "Agent" in html
    assert "Answer" in html


def test_page_viewer_renders_snapshot_fields():
    html = render_snapshot_html(make_snapshot())

    assert "Ella，我要出门了" in html
    assert "camera frame" in html
    assert "mock://frame-1" in html
    assert "Desk scene with phone and keys." in html
    assert "phone, keys" in html
    assert "Give the user a short reminder before leaving." in html
    assert "FINAL RESPONSE PROMPT" in html
    assert "FINAL RESPONSE PROMPT" in html
    assert "camera_scene: phone and keys visible" in html
    assert "Remember your phone and keys." in html
    assert "recorded" in html


def test_prompt_section_uses_safe_title_and_no_reasoning_labels():
    html = render_snapshot_html(make_snapshot())

    assert "Prompt Sent to LLM" in html
    assert "Reasoning" not in html
    assert "Chain of Thought" not in html
    assert "Model Thinking" not in html


def test_prompt_details_are_collapsible():
    html = render_snapshot_html(make_snapshot())

    assert "<details" in html
    assert "FINAL RESPONSE PROMPT" in html
    assert "FINAL RESPONSE PROMPT" in html


def test_viewer_accepts_serialized_snapshot_data():
    snapshot_data = make_snapshot().to_dict()

    html = render_snapshot_html(snapshot_data)

    assert "Prompt Sent to LLM" in html
    assert "Remember your phone and keys." in html


def test_renderer_escapes_html_content():
    snapshot = RunDisplaySnapshot(
        user_input="<script>alert('x')</script>",
        transcript=None,
        captured_frame_reference=None,
        image_status=CAMERA_FRAME,
        scene_summary="<b>unsafe</b>",
        visible_items=("<phone>",),
        task_goal="Answer safely.",
        final_response_prompt_text="<prompt>",
        tool_results_summary="<tool>",
        final_response="<answer>",
        memory_status="recorded",
    )

    html = render_snapshot_html(snapshot)

    assert "<script>" not in html
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in html
    assert "&lt;b&gt;unsafe&lt;/b&gt;" in html
    assert "&lt;answer&gt;" in html


def test_renderer_does_not_call_runtime_or_providers():
    class ExplodingSnapshot:
        def to_dict(self):
            return make_snapshot().to_dict()

        def __getattr__(self, name):
            raise AssertionError(f"unexpected external access: {name}")

    html = render_snapshot_html(ExplodingSnapshot())

    assert "Remember your phone and keys." in html


def test_page_viewer_can_write_local_html_file(tmp_path):
    output_path = tmp_path / "display.html"

    written_path = LocalPageViewer().write_snapshot(make_snapshot(), output_path)

    assert written_path == output_path
    html = output_path.read_text(encoding="utf-8")
    assert "Prompt Sent to LLM" in html
    assert "Remember your phone and keys." in html
