from prompts.engine import PromptBuildResult, PromptEngine, PromptType


def test_strategy_selection_prompt_uses_structured_task_and_skill_context() -> None:
    context = {
        "task": {"goal": "Prepare a trip."},
        "visible_skills": (
            {
                "name": "travel_planning",
                "description": "Plan a trip.",
                "when_to_use": "Use for travel planning.",
            },
        ),
    }

    result = PromptEngine().build(PromptType.STRATEGY_SELECTION, context)

    assert isinstance(result, PromptBuildResult)
    assert result.prompt_type == PromptType.STRATEGY_SELECTION
    assert result.prompt_name == "strategy_selection"
    assert "travel_planning" in result.prompt
    assert "strict JSON" in result.prompt
    assert set(result.context_keys) == {"task", "visible_skills"}


def test_execution_decision_prompt_includes_strategy_skill_tools_and_observations() -> None:
    context = {
        "task": {"goal": "Prepare a trip."},
        "strategy": {"mode": "react", "skill_name": "travel_planning"},
        "selected_skill": {
            "name": "travel_planning",
            "content": "Use current travel facts.",
        },
        "visible_tools": (
            {"name": "get_weather", "description": "Get current weather."},
        ),
        "observations": (
            {"tool_name": "get_weather", "payload": {"summary": "Rain."}},
        ),
    }

    result = PromptEngine().build(PromptType.EXECUTION_DECISION, context)

    assert result.prompt_type == PromptType.EXECUTION_DECISION
    assert result.prompt_name == "execution_decision"
    assert "get_weather" in result.prompt
    assert "Rain." in result.prompt
    assert "CALL_TOOL" in result.prompt
    assert "COMPLETE" in result.prompt
    assert "WAIT" in result.prompt
    assert "REPLAN" in result.prompt
    assert set(result.context_keys) == {
        "observations",
        "selected_skill",
        "strategy",
        "task",
        "visible_tools",
    }


def test_execution_prompt_engine_only_builds_text() -> None:
    class ExplodingService:
        def generate(self, *_args, **_kwargs):
            raise AssertionError("PromptEngine must not call the LLM")

    result = PromptEngine().build(
        PromptType.EXECUTION_DECISION,
        {"llm_provider": ExplodingService()},
    )

    assert isinstance(result.prompt, str)


def test_execution_prompt_prevents_repeated_camera_scene_calls() -> None:
    result = PromptEngine().build(
        PromptType.EXECUTION_DECISION,
        {
            "task": {"goal": "Identify what the user is holding."},
            "visible_tools": (
                {"name": "camera_scene", "description": "Capture visual context."},
            ),
            "observations": (
                {
                    "tool_name": "camera_scene",
                    "payload": {
                        "status": "available",
                        "summary": "The user is holding a phone.",
                    },
                },
            ),
        },
    )

    assert "do not call camera_scene again" in result.prompt
    assert "COMPLETE" in result.prompt
    assert "insufficient" in result.prompt
    assert "unavailable" in result.prompt
