from pathlib import Path

from demo.cli_demo import run_demo


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
