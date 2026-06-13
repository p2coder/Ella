from sessions.output import UserVisibleAgentOutput


def test_user_visible_output_represents_process_and_final_response():
    output = UserVisibleAgentOutput(
        process={
            "vision_summary": "Desk contains a laptop, headphones, and a water bottle.",
            "weather_summary": "Light rain is possible later today.",
            "steps": (
                "Check visible scene.",
                "Check mock weather.",
                "Prepare a short reminder.",
            ),
        },
        final_response="Take your keys and phone. It may rain, so consider an umbrella.",
    )

    assert output.process["vision_summary"].startswith("Desk contains")
    assert output.final_response == (
        "Take your keys and phone. It may rain, so consider an umbrella."
    )
    assert output.show_process is True
    assert output.process_collapsed is False


def test_user_visible_output_serializes_visibility_flags():
    output = UserVisibleAgentOutput(
        process={"task_goal": "Prepare a short pre-leaving reminder."},
        final_response="Phone, keys, wallet, and umbrella.",
        show_process=False,
        process_collapsed=True,
    )

    assert output.to_dict() == {
        "process": {"task_goal": "Prepare a short pre-leaving reminder."},
        "final_response": "Phone, keys, wallet, and umbrella.",
        "show_process": False,
        "process_collapsed": True,
    }


def test_user_visible_output_is_not_completion_package():
    output = UserVisibleAgentOutput(
        process={},
        final_response="Phone, keys, wallet, and umbrella.",
    )

    assert not hasattr(output, "tool_results")
    assert not hasattr(output, "memory_request")
