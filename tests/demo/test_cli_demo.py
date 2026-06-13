from pathlib import Path

from demo.cli_demo import DemoRuntime, run_demo


def test_cli_demo_runs_going_out_flow_and_prints_visible_sections(tmp_path: Path):
    memory_path = tmp_path / "memory.md"

    output = run_demo(
        input_text="Ella，我要出门了",
        memory_path=memory_path,
    )

    assert "[Ella Process]" in output
    assert "I understood that the user is preparing to go out." in output
    assert "I selected the going_out skill." in output
    assert "I checked the mock context and prepared a short reminder." in output
    assert "[Final Answer]" in output
    assert "keys" in output
    assert "phone" in output
    assert "umbrella" in output
    assert "[Memory]" in output
    assert str(memory_path) in output


def test_cli_demo_writes_memory_through_memory_manager(tmp_path: Path):
    memory_path = tmp_path / "memory.md"

    run_demo(
        input_text="Ella，我要出门了",
        memory_path=memory_path,
    )

    memory_text = memory_path.read_text(encoding="utf-8")
    assert "## Task " in memory_text
    assert "- session_id: " in memory_text
    assert "- trace_id: " in memory_text
    assert "Prepared going-out reminder with mock tools." in memory_text


def test_demo_runtime_reuses_stable_capability_managers(tmp_path: Path):
    runtime = DemoRuntime.create_default()
    skill_manager = runtime.skill_manager
    tool_manager = runtime.tool_manager
    versions = (skill_manager.version, tool_manager.version)

    run_demo("Ella，我要出门了", tmp_path / "first.md", runtime)
    run_demo("Ella，我要出门了", tmp_path / "second.md", runtime)

    assert runtime.skill_manager is skill_manager
    assert runtime.tool_manager is tool_manager
    assert (skill_manager.version, tool_manager.version) == versions
