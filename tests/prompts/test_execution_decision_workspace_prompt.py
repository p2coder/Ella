from prompts.engine import PromptEngine


def test_execution_decision_prompt_includes_workspace_section():
    result = PromptEngine().build(
        "EXECUTION_DECISION",
        {
            "workspace": {
                "current_goal": "Answer the user.",
                "visible_tools": (),
                "observations": (),
            }
        },
    )

    assert "SystemPrompt:" in result.prompt
    assert "Instruction:" in result.prompt
    assert "WorkSpace:" in result.prompt
    assert "OutputContract:" in result.prompt


def test_execution_decision_reads_visible_capabilities_from_workspace():
    result = PromptEngine().build(
        "EXECUTION_DECISION",
        {
            "workspace": {
                "visible_skills": (
                    {
                        "name": "planning",
                        "description": "Plan multi-step work.",
                    },
                ),
                "visible_tools": (
                    {
                        "name": "note_lookup",
                        "description": "Find notes.",
                        "input_schema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                        "input_examples": ({"query": "todo"},),
                    },
                ),
            }
        },
    )

    assert "Read concrete visible Skill summaries" in result.prompt
    assert "only from WorkSpace" in result.prompt
    assert "visible_skills" in result.prompt
    assert "planning" in result.prompt
    assert "visible_tools" in result.prompt
    assert "note_lookup" in result.prompt
    assert "input_examples" in result.prompt


def test_execution_decision_observations_are_in_workspace():
    result = PromptEngine().build(
        "EXECUTION_DECISION",
        {
            "workspace": {
                "observations": (
                    {
                        "tool_name": "note_lookup",
                        "status": "available",
                        "summary": "Found a matching note.",
                    },
                )
            }
        },
    )

    assert "WorkSpace:" in result.prompt
    assert "observations" in result.prompt
    assert "Found a matching note." in result.prompt


def test_execution_decision_prompt_does_not_require_tool_use():
    result = PromptEngine().build(
        "EXECUTION_DECISION",
        {"workspace": {"current_goal": "Say hello back."}},
    )

    assert "Tool is an optional capability" in result.prompt
    assert "COMPLETE is valid" in result.prompt
