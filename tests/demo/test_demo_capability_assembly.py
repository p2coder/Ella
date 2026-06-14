import inspect
from pathlib import Path

from demo.cli_demo import DemoRuntime, run_demo


def test_demo_assembly_shares_capability_managers_with_session_boundary(
    tmp_path: Path,
):
    runtime = DemoRuntime.create_default(tmp_path / "memory.md")
    session_manager = runtime.task_runtime.session_manager
    executor = runtime.task_runtime.executor
    subagent = runtime.task_runtime.subagent

    assert executor is not None
    assert subagent is not None
    assert session_manager.skill_manager is subagent.skill_manager
    assert session_manager.skill_manager is executor.skill_manager
    assert session_manager.tool_manager is executor.tool_manager


def test_demo_does_not_define_a_hard_coded_permission_tuple():
    source = inspect.getsource(DemoRuntime.create_default)

    assert "allowed_tools=(" not in source
    assert "allowed_tools=[" not in source


def test_demo_keeps_managers_inside_application_assembly(tmp_path: Path):
    runtime = DemoRuntime.create_default(tmp_path / "memory.md")

    assert not hasattr(runtime, "skill_manager")
    assert not hasattr(runtime, "tool_manager")


def test_demo_output_remains_stable(tmp_path: Path):
    output = run_demo(
        input_text="Ella，看看当前画面，我要出门了",
        memory_path=tmp_path / "memory.md",
    )

    assert "[Ella Process]" in output
    assert "[Final Answer]" in output
    assert "[Memory]" in output
    assert "Mock scene contains phone, keys, wallet." in output
