from pathlib import Path

from agent.context import AgentExecutionContext, CapabilityScope
from memory import MemoryManagementRequest, MemoryManager
from tasks.completion import TaskCompletionPackage
from tasks.output import UserVisibleAgentOutput
from tools import ToolResult


def make_package() -> TaskCompletionPackage:
    context = AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-memory",
        trace_id="trace-memory",
        handoff_goal="Give the user a short, necessary reminder before leaving.",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ("mock_weather", "mock_checklist")),
        permissions=("read_context",),
    )
    return TaskCompletionPackage(
        context=context,
        summary="Prepared and delivered a short pre-leaving reminder.",
        user_visible_output=UserVisibleAgentOutput(
            process={
                "task_goal": "Prepare a short pre-leaving reminder.",
                "user_input": "Ella，我要出门了，需要带什么？",
            },
            final_response="Take your keys and phone. Consider an umbrella.",
        ),
        tool_results=(
            ToolResult(
                tool_name="mock_checklist",
                task_id="task-memory",
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
        "- trace_id: trace-memory\n"
        "- user_input: Ella，我要出门了，需要带什么？\n"
        "- summary: Prepared and delivered a short pre-leaving reminder.\n"
        "- final_response: Take your keys and phone. Consider an umbrella.\n"
        "\n"
    )


def test_memory_manager_is_single_memory_update_entry_point(tmp_path: Path):
    manager = MemoryManager(memory_path=tmp_path / "memory.md")

    assert hasattr(manager, "handle")
    assert not hasattr(make_package(), "write_memory")
    assert not hasattr(make_package(), "memory_manager")


def test_memory_manager_stores_every_submitted_memory_record(tmp_path: Path):
    memory_path = tmp_path / "memory.md"
    manager = MemoryManager(memory_path=memory_path)
    request = MemoryManagementRequest.from_completion(make_package())

    first = manager.handle(request)
    second = manager.handle(request)

    assert first.action == "appended"
    assert second.action == "appended"
    memory_text = memory_path.read_text(encoding="utf-8")
    assert memory_text.count("## Task task-memory") == 2
    assert memory_text.count(
        "- user_input: Ella，我要出门了，需要带什么？"
    ) == 2
    assert memory_text.count(
        "- final_response: Take your keys and phone. Consider an umbrella."
    ) == 2


def test_memory_manager_query_returns_all_stored_memory(tmp_path: Path):
    memory_path = tmp_path / "memory.md"
    manager = MemoryManager(memory_path=memory_path)
    request = MemoryManagementRequest.from_completion(make_package())
    manager.handle(request)
    manager.handle(request)

    result = manager.query()

    assert result.action == "loaded_all"
    assert result.memory_path == memory_path
    assert result.content == memory_path.read_text(encoding="utf-8")
    assert result.content.count("## Task task-memory") == 2


def test_memory_manager_query_missing_memory_returns_empty_content(
    tmp_path: Path,
):
    memory_path = tmp_path / "missing-memory.md"

    result = MemoryManager(memory_path=memory_path).query()

    assert result.action == "loaded_all"
    assert result.memory_path == memory_path
    assert result.content == ""
