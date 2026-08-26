from dataclasses import replace

from demo.display_snapshot import CAMERA_FRAME, RunDisplaySnapshot
from demo.page_viewer import render_snapshot_html
from demo.web_ui import LocalWebUIShell, render_web_ui_shell


def make_snapshot() -> RunDisplaySnapshot:
    return RunDisplaySnapshot(
        user_input="<hello>",
        transcript=None,
        captured_frame_reference="mock://frame-1",
        image_status=CAMERA_FRAME,
        scene_summary="<scene>",
        visible_items=("<phone>",),
        task_goal="Answer the user.",
        final_response_prompt_text="FINAL prompt <answer>",
        tool_results_summary="camera_scene: <tool>",
        final_response="<final>",
        memory_status="recorded",
        execution_decision_prompt_text="EXECUTION prompt",
        first_decision_prompt_text="FIRST prompt",
        verification_prompt_text="VERIFY prompt",
    )


def test_snapshot_carries_all_prompt_display_fields():
    data = make_snapshot().to_dict()

    assert data["prompt_display_fields"] == (
        "first_decision_prompt_text",
        "execution_decision_prompt_text",
        "verification_prompt_text",
        "final_response_prompt_text",
    )
    assert data["first_decision_prompt_text"] == "FIRST prompt"
    assert data["execution_decision_prompt_text"] == "EXECUTION prompt"
    assert data["final_response_prompt_text"] == "FINAL prompt <answer>"


def test_page_viewer_displays_all_prompts_with_safe_title():
    html = render_snapshot_html(make_snapshot())

    assert "Prompt Sent to LLM" in html
    assert "First decision prompt" in html
    assert "Execution decision prompt" in html
    assert "Final response prompt" in html
    assert "FIRST prompt" in html
    assert "EXECUTION prompt" in html
    assert "FINAL prompt &lt;answer&gt;" in html


def test_web_ui_displays_all_prompts_from_snapshot():
    html = render_web_ui_shell(make_snapshot())

    assert "Prompt Sent to LLM" in html
    assert "First decision prompt" in html
    assert "Execution decision prompt" in html
    assert "Verification prompt" in html
    assert "Final response prompt" in html
    assert "FIRST prompt" in html
    assert "EXECUTION prompt" in html
    assert "VERIFY prompt" in html
    assert "FINAL prompt &lt;answer&gt;" in html


def test_web_ui_explains_when_a_prompt_was_not_invoked():
    snapshot = replace(make_snapshot(), first_decision_prompt_text="")

    html = render_web_ui_shell(snapshot)

    assert "Not invoked for this run." in html
    assert '<pre class="prompt-text"></pre>' not in html


def test_prompt_display_avoids_hidden_reasoning_labels():
    html = render_web_ui_shell(make_snapshot()) + render_snapshot_html(make_snapshot())

    assert "Reasoning" not in html
    assert "Chain of Thought" not in html
    assert "Model Thinking" not in html


def test_prompt_display_escapes_user_model_and_prompt_text():
    html = render_web_ui_shell(make_snapshot())

    assert "<hello>" not in html
    assert "<scene>" not in html
    assert "<phone>" not in html
    assert "<tool>" not in html
    assert "<final>" not in html
    assert "<answer>" not in html
    assert "&lt;hello&gt;" in html
    assert "&lt;scene&gt;" in html
    assert "&lt;phone&gt;" in html
    assert "&lt;tool&gt;" in html
    assert "&lt;final&gt;" in html
    assert "&lt;answer&gt;" in html


def test_page_renderer_does_not_call_runtime_or_external_services():
    shell = LocalWebUIShell()

    assert not hasattr(shell, "event_runtime")
    assert not hasattr(shell, "task_runtime")
    assert not hasattr(shell, "llm_provider")
    assert not hasattr(shell, "tool_manager")
    assert not hasattr(shell, "camera_provider")
    assert not hasattr(shell, "microphone_provider")
    assert not hasattr(shell, "memory_manager")

    assert "Prompt Sent to LLM" in shell.render(make_snapshot())
