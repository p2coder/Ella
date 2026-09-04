from agent.context import AgentExecutionContext, CapabilityScope
from memory import MemoryManagementRequest, MemoryManager
from tasks.completion import TaskCompletionPackage
from tasks.output import UserVisibleAgentOutput
from tools import ToolResult


def make_completion() -> TaskCompletionPackage:
    context = AgentExecutionContext(
        agent_id="ella-main",
        agent_role="main_agent",
        parent_agent_id=None,
        task_id="task-memory-contract",
        memory_scope="task_local",
        capability_scope=CapabilityScope("main_agent", (), ("mock_checklist",)),
        permissions=(),
    )
    return TaskCompletionPackage(
        context=context,
        summary="Prepared a deterministic mock reminder.",
        user_visible_output=UserVisibleAgentOutput(
            process={"source": "mock tools"},
            final_response="Take your keys and phone.",
        ),
        tool_results=(
            ToolResult(
                tool_name="mock_checklist",
                task_id=context.task_id,
                payload={"items": ("keys", "phone")},
            ),
        ),
    )


def test_memory_manager_is_the_single_write_boundary(tmp_path):
    completion = make_completion()
    request = MemoryManagementRequest.from_completion(completion)
    memory_path = tmp_path / "memory.md"

    result = MemoryManager(memory_path).handle(request)

    assert result.action == "appended"
    assert result.memory_path == memory_path
    assert not hasattr(completion, "write_memory")
    assert not hasattr(completion.user_visible_output, "write_memory")
    assert not hasattr(completion.tool_results[0], "write_memory")


def test_memory_request_and_record_retain_completion_context(tmp_path):
    completion = make_completion()
    request = MemoryManagementRequest.from_completion(completion)
    memory_path = tmp_path / "memory.md"

    MemoryManager(memory_path).handle(request)

    assert request.completion is completion
    assert request.task_id == "task-memory-contract"
    record = memory_path.read_text(encoding="utf-8")
    assert "task-memory-contract" in record
    assert completion.summary in record
    assert completion.user_visible_output.final_response in record
