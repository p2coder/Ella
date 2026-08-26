import inspect

from demo.display_snapshot import TEXT_ONLY, RunDisplaySnapshot
from demo.page_viewer import render_snapshot_html
from demo.web_ui import render_web_ui_shell
from prompts import templates
from prompts.engine import PromptEngine, PromptType


class ExplodingExternalService:
    def generate(self, *args, **kwargs):
        raise AssertionError("PromptEngine must not call providers")

    def run(self, *args, **kwargs):
        raise AssertionError("PromptEngine must not execute tools")

    def handle(self, *args, **kwargs):
        raise AssertionError("PromptEngine must not write memory")

    def query(self, *args, **kwargs):
        raise AssertionError("PromptEngine must not query memory")

    def capture(self, *args, **kwargs):
        raise AssertionError("PromptEngine must not access devices")


def test_prompt_engine_accepts_structured_context_and_outputs_string():
    result = PromptEngine().build(
        PromptType.EXECUTION_DECISION,
        {
            "memory_context": {"recent": ("User prefers concise answers.",)},
            "workspace": {
                "overall_goal": "Answer the user.",
                "visible_skills": ({"name": "general_help"},),
                "visible_tools": ({"name": "lookup", "description": "Search."},),
            },
        },
    )

    assert isinstance(result.prompt, str)
    assert result.prompt_type == PromptType.EXECUTION_DECISION
    assert "Memory:" in result.prompt
    assert "WorkSpace:" in result.prompt
    assert "general_help" in result.prompt
    assert "lookup" in result.prompt


def test_prompt_engine_does_not_call_external_runtime_services():
    external = ExplodingExternalService()

    prompt = PromptEngine().build(
        PromptType.FINAL_RESPONSE,
        {
            "workspace": {
                "provider": external,
                "tool": external,
                "memory": external,
                "device": external,
            },
            "memory_context": {"memory_manager": external},
        },
    ).prompt

    assert "[UNSUPPORTED_OBJECT]" in prompt


def test_prompt_engine_source_has_no_runtime_service_imports_or_calls():
    source = inspect.getsource(PromptEngine)

    forbidden_tokens = (
        "LLMProvider",
        "ToolManager",
        "MemoryManager",
        "CameraProvider",
        "MicrophoneProvider",
        ".generate(",
        ".run(",
        ".handle(",
        ".capture(",
    )
    for token in forbidden_tokens:
        assert token not in source


def test_system_prompt_is_not_going_out_specific():
    system_prompt = templates.ELLA_SYSTEM_PROMPT.lower()

    assert "going_out" not in system_prompt
    assert "umbrella" not in system_prompt
    assert "leaving" not in system_prompt
    assert "companion" in system_prompt
    assert "task execution" in system_prompt


def test_skill_and_tool_policy_are_generic_only():
    skill_policy = templates.SKILL_POLICY_PROMPT
    tool_policy = templates.TOOL_POLICY_PROMPT

    assert "going_out" not in skill_policy
    assert "camera_scene" not in tool_policy
    assert "mock_weather" not in tool_policy
    assert "Skill is guidance" in skill_policy
    assert "If no Skill fits" in skill_policy
    assert "Tool is an optional capability" in tool_policy
    assert "If no suitable Tool is available" in tool_policy


def test_concrete_skills_and_tools_are_supplied_through_workspace():
    prompt = PromptEngine().build(
        PromptType.EXECUTION_DECISION,
        {
            "workspace": {
                "visible_skills": (
                    {
                        "name": "desk_inspection",
                        "description": "Use visual evidence for desk checks.",
                    },
                ),
                "visible_tools": (
                    {
                        "name": "camera_scene",
                        "description": "Capture bounded visual context.",
                    },
                ),
            }
        },
    ).prompt

    assert "WorkSpace:" in prompt
    assert "desk_inspection" in prompt
    assert "camera_scene" in prompt


def test_execution_decision_contract_is_single_action():
    prompt = PromptEngine().build(PromptType.EXECUTION_DECISION, {}).prompt

    assert "Return one strict JSON object" in prompt
    assert "One execution decision may choose at most one action" in prompt
    assert "CALL_TOOL may use exactly one visible tool" in prompt
    assert "CALL_TOOL" in prompt
    assert "SUBMIT_RESULT" in prompt


def test_no_suitable_tool_or_skill_does_not_imply_task_failure():
    prompt = PromptEngine().build(PromptType.EXECUTION_DECISION, {}).prompt

    assert "If no Skill fits" in prompt
    assert "continue without Skill instead of failing" in prompt
    assert "If no suitable Tool is available" in prompt
    assert "SUBMIT_RESULT" in prompt


def test_page_prompt_labels_avoid_hidden_reasoning_terms():
    snapshot = RunDisplaySnapshot(
        user_input="hello",
        transcript=None,
        captured_frame_reference=None,
        image_status=TEXT_ONLY,
        scene_summary="",
        visible_items=(),
        task_goal="Respond.",
        final_response_prompt_text="FINAL",
        tool_results_summary="",
        final_response="Hi.",
        memory_status="appended",
        execution_decision_prompt_text="EXECUTION",
    )

    html = render_web_ui_shell(snapshot) + render_snapshot_html(snapshot)

    assert "Prompt Sent to LLM" in html
    assert "Reasoning" not in html
    assert "Chain of Thought" not in html
    assert "Model Thinking" not in html


def test_prompt_output_redacts_api_key_like_secrets():
    prompt = PromptEngine().build(
        PromptType.FINAL_RESPONSE,
        {
            "workspace": {
                "visible_tools": (),
                "accidental_secret": "sk-1234567890abcdef",
                "local_path": "/Users/example/.secret",
            },
            "memory_context": "Bearer abcdefghijklmnopqrstuvwxyz",
        },
    ).prompt

    assert "sk-1234567890abcdef" not in prompt
    assert "Bearer abcdefghijklmnopqrstuvwxyz" not in prompt
    assert "/Users/example/.secret" not in prompt
    assert "[REDACTED]" in prompt
