from agent.context import AgentExecutionContext
from sessions.completion import TaskCompletionPackage
from sessions.output import UserVisibleAgentOutput
from tools import ToolResult


def make_context() -> AgentExecutionContext:
    return AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        session_id="session-completion",
        task_id="task-completion",
        trace_id="trace-completion",
        handoff_goal="Give the user a short, necessary reminder before leaving.",
        memory_scope="task_local",
        allowed_tools=("mock_weather",),
        permissions=("read_context",),
    )


def make_output() -> UserVisibleAgentOutput:
    return UserVisibleAgentOutput(
        process={"task_goal": "Prepare a short pre-leaving reminder."},
        final_response="Take your keys and phone. Consider an umbrella.",
    )


def make_tool_result() -> ToolResult:
    return ToolResult(
        tool_name="mock_weather",
        task_id="task-completion",
        session_id="session-completion",
        trace_id="trace-completion",
        payload={"summary": "Light rain is possible later today."},
    )


def test_completion_package_carries_context_output_summary_and_tool_results():
    package = TaskCompletionPackage(
        context=make_context(),
        summary="Prepared a concise pre-leaving reminder.",
        user_visible_output=make_output(),
        tool_results=(make_tool_result(),),
    )

    assert package.context.task_id == "task-completion"
    assert package.context.session_id == "session-completion"
    assert package.context.trace_id == "trace-completion"
    assert package.summary == "Prepared a concise pre-leaving reminder."
    assert package.user_visible_output.final_response == (
        "Take your keys and phone. Consider an umbrella."
    )
    assert package.tool_results[0].tool_name == "mock_weather"


def test_completion_package_serializes_for_memory_boundary():
    package = TaskCompletionPackage(
        context=make_context(),
        summary="Prepared a concise pre-leaving reminder.",
        user_visible_output=make_output(),
        tool_results=(make_tool_result(),),
    )

    serialized = package.to_dict()

    assert serialized["context"]["task_id"] == "task-completion"
    assert serialized["summary"] == "Prepared a concise pre-leaving reminder."
    assert serialized["user_visible_output"]["final_response"] == (
        "Take your keys and phone. Consider an umbrella."
    )
    assert serialized["tool_results"][0]["trace_id"] == "trace-completion"
    assert "memory_record" not in serialized
