from pathlib import Path

from agent.context import AgentExecutionContext
from memory import MemoryManagementRequest, MemoryManager
from sessions.completion import TaskCompletionPackage
from sessions.output import UserVisibleAgentOutput
from tools import ToolResult


def make_package() -> TaskCompletionPackage:
    context = AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        session_id="session-memory",
        task_id="task-memory",
        trace_id="trace-memory",
        handoff_goal="Give the user a short, necessary reminder before leaving.",
        memory_scope="task_local",
        allowed_tools=("mock_weather", "mock_checklist"),
        permissions=("read_context",),
    )
    return TaskCompletionPackage(
        context=context,
        summary="Prepared and delivered a short pre-leaving reminder.",
        user_visible_output=UserVisibleAgentOutput(
            process={"task_goal": "Prepare a short pre-leaving reminder."},
            final_response="Take your keys and phone. Consider an umbrella.",
        ),
        tool_results=(
            ToolResult(
                tool_name="mock_checklist",
                task_id="task-memory",
                session_id="session-memory",
                trace_id="trace-memory",
                payload={"items": ("phone", "keys", "wallet", "umbrella")},
            ),
        ),
    )


def test_memory_management_request_wraps_completion_package():
    package = make_package()

    request = MemoryManagementRequest.from_completion(package)

    assert request.completion == package
    assert request.task_id == "task-memory"
    assert request.session_id == "session-memory"
    assert request.trace_id == "trace-memory"


def test_memory_manager_appends_deterministic_memory_record(tmp_path: Path):
    memory_path = tmp_path / "memory.md"
    manager = MemoryManager(memory_path=memory_path)
    request = MemoryManagementRequest.from_completion(make_package())

    result = manager.handle(request)

    assert result.action == "appended"
    assert result.memory_path == memory_path
    assert memory_path.read_text(encoding="utf-8") == (
        "## Task task-memory\n"
        "- session_id: session-memory\n"
        "- trace_id: trace-memory\n"
        "- summary: Prepared and delivered a short pre-leaving reminder.\n"
        "- final_response: Take your keys and phone. Consider an umbrella.\n"
        "\n"
    )


def test_memory_manager_is_single_memory_update_entry_point(tmp_path: Path):
    manager = MemoryManager(memory_path=tmp_path / "memory.md")

    assert hasattr(manager, "handle")
    assert not hasattr(make_package(), "write_memory")
    assert not hasattr(make_package(), "memory_manager")
