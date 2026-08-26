from types import SimpleNamespace

from app_runtime import _current_model_output, _usage_projection
from demo.display_snapshot import RunDisplaySnapshot, TEXT_ONLY
from demo.web_ui import render_web_ui_shell


def _snapshot() -> RunDisplaySnapshot:
    return RunDisplaySnapshot(
        user_input="A long user request",
        transcript=None,
        captured_frame_reference=None,
        image_status=TEXT_ONLY,
        scene_summary="",
        visible_items=(),
        task_goal="",
        final_response_prompt_text="SECRET PROMPT",
        tool_results_summary="",
        final_response="Public final response",
        memory_status="recorded",
        task_id="task-1",
        task_state="reasoning",
    )


def test_improved_ui_hides_prompts_and_places_controls_below_task_id():
    html = render_web_ui_shell(_snapshot())
    assert "SECRET PROMPT" not in html
    assert "Prompt Sent to LLM" not in html
    assert html.index("task-1") < html.index('data-task-action="pause"')
    assert "用户输入" in html
    assert "最终输出" in html
    assert "模型输出" in html
    assert "实时同步中" in html


def test_improved_ui_has_collapsible_timing_and_usage_metrics():
    html = render_web_ui_shell(_snapshot())
    assert 'class="metrics"' in html
    assert 'aria-controls="execution-details"' in html
    assert 'id="total-duration"' in html
    assert 'id="token-usage"' in html
    assert 'id="cache-hit-rate"' in html


def test_usage_projection_calculates_cache_hit_rate_when_available():
    task = SimpleNamespace(
        task_local_state={
            "provider_usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "prompt_tokens_details": {"cached_tokens": 60},
            }
        }
    )
    assert _usage_projection(task) == {
        "token_usage": 120,
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "cached_tokens": 60,
        "cache_hit_rate": 60.0,
    }


def test_current_model_output_prefers_safe_draft():
    task = SimpleNamespace(
        completion=None,
        task_local_state={"draft_final_response": "visible draft"},
    )
    assert _current_model_output(task) == "visible draft"
