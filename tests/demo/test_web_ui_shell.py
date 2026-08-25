from demo.display_snapshot import CAMERA_FRAME, RunDisplaySnapshot
from demo.web_ui import LocalWebUIShell, render_web_ui_shell


def make_snapshot() -> RunDisplaySnapshot:
    return RunDisplaySnapshot(
        user_input="<script>alert('input')</script>",
        transcript="Ella，我要出门了",
        captured_frame_reference="mock://frame-1",
        image_status=CAMERA_FRAME,
        scene_summary="<b>Desk scene with phone and keys.</b>",
        visible_items=("<phone>", "keys"),
        task_goal="Give the user a short reminder before leaving.",
        task_formulation_prompt_text="TASK FORMULATION PROMPT",
        final_response_prompt_text="FINAL RESPONSE PROMPT",
        tool_results_summary="camera_scene: phone and keys visible",
        final_response="<answer>Remember your phone and keys.</answer>",
        memory_status="recorded",
        first_decision_prompt_text="FIRST DECISION PROMPT",
        execution_decision_prompt_text="EXECUTION DECISION PROMPT",
        verification_prompt_text="VERIFICATION PROMPT",
    )


def test_web_ui_shell_renders_required_sections():
    html = render_web_ui_shell()

    assert "Input" in html
    assert "Vision" in html
    assert "Agent" in html
    assert "Tool results" in html
    assert "Answer" in html
    assert "Prompt Sent to LLM" in html


def test_text_input_and_submit_placeholder_are_present():
    html = render_web_ui_shell()

    assert "<textarea" in html
    assert 'name="user_input"' in html
    assert "<button" in html
    assert "Submit" in html
    assert 'id="submit-button"' in html
    assert "aria-busy" in html


def test_prompt_section_renders_runtime_boundaries():
    html = render_web_ui_shell(make_snapshot())

    assert "Prompt Sent to LLM" in html
    assert "TASK FORMULATION PROMPT" not in html
    assert "FIRST DECISION PROMPT" in html
    assert "EXECUTION DECISION PROMPT" in html
    assert "VERIFICATION PROMPT" in html
    assert "FINAL RESPONSE PROMPT" in html
    assert "Reasoning" not in html
    assert "Chain of Thought" not in html
    assert "Model Thinking" not in html


def test_web_ui_shell_renders_snapshot_data_when_provided():
    html = render_web_ui_shell(make_snapshot())

    assert "Ella，我要出门了" in html
    assert "camera frame" in html
    assert "mock://frame-1" in html
    assert "camera_scene: phone and keys visible" in html
    assert "recorded" in html


def test_web_ui_shell_escapes_user_and_model_text():
    html = render_web_ui_shell(make_snapshot())

    assert "<script>alert('input')</script>" not in html
    assert "&lt;script&gt;alert(&#x27;input&#x27;)&lt;/script&gt;" in html
    assert "&lt;b&gt;Desk scene with phone and keys.&lt;/b&gt;" in html
    assert "&lt;phone&gt;" in html
    assert "&lt;answer&gt;Remember your phone and keys.&lt;/answer&gt;" in html


def test_renderer_does_not_call_runtime_providers_devices_tools_or_memory():
    shell = LocalWebUIShell()

    assert not hasattr(shell, "event_runtime")
    assert not hasattr(shell, "task_runtime")
    assert not hasattr(shell, "provider")
    assert not hasattr(shell, "device")
    assert not hasattr(shell, "tool")
    assert not hasattr(shell, "memory_manager")

    html = shell.render(make_snapshot())
    assert "Prompt Sent to LLM" in html
