from demo.display_snapshot import RunDisplaySnapshot, TEXT_ONLY
from demo.web_ui import DEFAULT_HOST, render_web_ui_shell


def test_web_projection_distinguishes_task_state_and_failure_delivery():
    snapshot = RunDisplaySnapshot(
        user_input="<script>alert(1)</script>", transcript=None,
        captured_frame_reference=None, image_status=TEXT_ONLY,
        scene_summary="", visible_items=(), task_goal="goal",
        task_formulation_prompt_text="", final_response_prompt_text="",
        tool_results_summary="", final_response="failed safely",
        memory_status="not recorded", task_id="task-1", task_state="delivered",
        active_step_ids=("step-2",), terminal_outcome="failed",
        delivery_status="delivery succeeded",
    )
    html = render_web_ui_shell(snapshot)
    assert "task-1" in html
    assert "delivered" in html
    assert "failed" in html
    assert "step-2" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_web_ui_remains_localhost_only_by_default():
    assert DEFAULT_HOST == "127.0.0.1"
