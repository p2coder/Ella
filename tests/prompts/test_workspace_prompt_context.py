from prompts.engine import PromptEngine


class FakeTool:
    pass


def build_workspace_prompt(workspace, **extra_context):
    return PromptEngine().build(
        "EXECUTION_DECISION",
        {"workspace": workspace, **extra_context},
    ).prompt


def test_workspace_renders_overall_and_current_goal():
    prompt = build_workspace_prompt(
        {
            "overall_goal": "Help the user prepare for the afternoon.",
            "current_goal": "Decide whether a tool is needed.",
        }
    )

    assert "WorkSpace:" in prompt
    assert "overall_goal" in prompt
    assert "Help the user prepare for the afternoon." in prompt
    assert "current_goal" in prompt
    assert "Decide whether a tool is needed." in prompt


def test_workspace_renders_observations():
    prompt = build_workspace_prompt(
        {
            "observations": (
                {
                    "tool_name": "calendar_summary",
                    "status": "failed",
                    "failure_reason": "permission denied",
                },
                {
                    "tool_name": "note_lookup",
                    "summary": "No matching note was found.",
                },
            )
        }
    )

    assert "observations" in prompt
    assert "calendar_summary" in prompt
    assert "permission denied" in prompt
    assert "No matching note was found." in prompt


def test_workspace_renders_visible_skills():
    prompt = build_workspace_prompt(
        {
            "visible_skills": (
                {
                    "name": "planning",
                    "description": "Help organize a task into steps.",
                    "use_case_summary": "Useful for multi-step work.",
                    "failure_notes": "May not apply to casual chat.",
                    "tool_references_summary": "Can use note_lookup.",
                },
            )
        }
    )

    assert "visible_skills" in prompt
    assert "planning" in prompt
    assert "Help organize a task into steps." in prompt
    assert "Useful for multi-step work." in prompt
    assert "Can use note_lookup." in prompt


def test_workspace_renders_visible_tools_with_schema_and_examples():
    prompt = build_workspace_prompt(
        {
            "visible_tools": (
                {
                    "name": "note_lookup",
                    "description": "Find a note by keyword.",
                    "input_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                    "input_examples": ({"query": "meeting"},),
                    "output_schema": {
                        "type": "object",
                        "properties": {"summary": {"type": "string"}},
                    },
                    "limitations": "Cannot access private files directly.",
                },
            )
        }
    )

    assert "visible_tools" in prompt
    assert "note_lookup" in prompt
    assert "input_schema" in prompt
    assert "input_examples" in prompt
    assert "meeting" in prompt
    assert "output_schema" in prompt
    assert "Cannot access private files directly." in prompt


def test_workspace_excludes_sensitive_runtime_resources():
    prompt = build_workspace_prompt(
        {
            "visible_tools": (
                {
                    "name": "unsafe_tool",
                    "description": "Should be sanitized.",
                    "api_key": "sk-abcdefghijklmnopqrstuvwxyz",
                    "authorization_header": "Bearer abcdefghijklmnopqrstuvwxyz",
                    "local_path": "/Users/wx/secret.txt",
                    "raw_media": b"not prompt safe",
                    "tool_instance": FakeTool(),
                },
            ),
            "current_step_state": {
                "debug_path": "file:///Users/wx/private.png",
                "class_object": FakeTool(),
            },
        }
    )

    assert "sk-abcdefghijklmnopqrstuvwxyz" not in prompt
    assert "Bearer abcdefghijklmnopqrstuvwxyz" not in prompt
    assert "/Users/wx/secret.txt" not in prompt
    assert "file:///Users/wx/private.png" not in prompt
    assert "not prompt safe" not in prompt
    assert "FakeTool" not in prompt
    assert "[REDACTED]" in prompt
    assert "[UNSUPPORTED_OBJECT]" in prompt


def test_workspace_and_memory_are_distinct_prompt_sections():
    result = PromptEngine().build(
        "FINAL_RESPONSE",
        {
            "memory_context": "The user prefers concise answers.",
            "workspace": {
                "current_goal": "Answer the current question.",
            },
        },
    )

    memory_index = result.prompt.index("Memory:")
    workspace_index = result.prompt.index("WorkSpace:")

    assert memory_index < workspace_index
    assert "The user prefers concise answers." in result.prompt
    assert "Answer the current question." in result.prompt


def test_skill_and_tool_policy_sections_do_not_duplicate_runtime_lists():
    prompt = build_workspace_prompt(
        {
            "visible_skills": (
                {"name": "rare_skill_name", "description": "Visible skill."},
            ),
            "visible_tools": (
                {"name": "rare_tool_name", "description": "Visible tool."},
            ),
        }
    )

    instruction = prompt.split("WorkSpace:", 1)[0]
    assert "rare_skill_name" not in instruction
    assert "rare_tool_name" not in instruction
    assert "rare_skill_name" in prompt
    assert "rare_tool_name" in prompt
