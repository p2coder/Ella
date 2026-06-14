from pathlib import Path

from skill.loader import SkillLoader
from skill.manager import SkillManager
from skill.registry import SkillDefinition, SkillRegistry


def write_skill(
    skills_root: Path,
    *,
    name: str,
    required_tools: str | None = None,
    optional_tools: str | None = None,
) -> Path:
    skill_dir = skills_root / name
    skill_dir.mkdir(parents=True)
    required_line = (
        "" if required_tools is None else f"required_tools: {required_tools}\n"
    )
    optional_line = (
        "" if optional_tools is None else f"optional_tools: {optional_tools}\n"
    )
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: Description for {name}.\n"
        f"when_to_use: Use {name} for its matching task.\n"
        f"{required_line}"
        f"{optional_line}"
        "---\n"
        f"\n# {name}\n",
        encoding="utf-8",
    )
    return skill_file


def test_skill_loader_parses_required_tools(tmp_path: Path) -> None:
    write_skill(
        tmp_path,
        name="with_required",
        required_tools="mock_weather, mock_checklist",
    )

    skill = SkillLoader(tmp_path).load_summary("with_required")

    assert skill.required_tools == ("mock_weather", "mock_checklist")


def test_skill_loader_parses_optional_tools(tmp_path: Path) -> None:
    write_skill(
        tmp_path,
        name="with_optional",
        optional_tools="camera_scene, mock_vision_summary",
    )

    skill = SkillLoader(tmp_path).load_summary("with_optional")

    assert skill.optional_tools == ("camera_scene", "mock_vision_summary")


def test_going_out_skill_declares_expected_tool_names() -> None:
    skill = SkillLoader().load_summary("going_out")

    assert skill.required_tools == ("mock_weather", "mock_checklist")
    assert skill.optional_tools == ("camera_scene", "mock_vision_summary")


def test_skill_definitions_store_tool_names_not_tool_instances() -> None:
    skill = SkillDefinition(
        name="metadata_only",
        description="Metadata only.",
        when_to_use="Use as metadata only.",
        path=Path("skill/skills/metadata_only/SKILL.md"),
        required_tools=("mock_weather",),
        optional_tools=("camera_scene",),
    )

    assert skill.required_tools == ("mock_weather",)
    assert skill.optional_tools == ("camera_scene",)
    assert not hasattr(skill, "tool")
    assert not hasattr(skill, "run")
    assert all(isinstance(tool_name, str) for tool_name in skill.required_tools)


def test_missing_tool_metadata_remains_backward_compatible(tmp_path: Path) -> None:
    write_skill(tmp_path, name="legacy")

    skill = SkillLoader(tmp_path).load_summary("legacy")

    assert skill.required_tools == ()
    assert skill.optional_tools == ()


def test_summary_exposes_tool_references_without_execution() -> None:
    skill = SkillDefinition(
        name="summary_skill",
        description="Summary skill.",
        when_to_use="Use for summary.",
        path=Path("skill/skills/summary_skill/SKILL.md"),
        required_tools=("mock_weather",),
        optional_tools=("camera_scene",),
    )

    assert skill.summary() == {
        "name": "summary_skill",
        "description": "Summary skill.",
        "when_to_use": "Use for summary.",
        "required_tools": ("mock_weather",),
        "optional_tools": ("camera_scene",),
    }


def test_required_tools_are_not_an_execution_plan() -> None:
    skill = SkillDefinition(
        name="not_plan",
        description="References tools only.",
        when_to_use="Use when matching.",
        path=Path("skill/skills/not_plan/SKILL.md"),
        required_tools=("mock_weather", "mock_checklist"),
    )

    assert skill.required_tools == ("mock_weather", "mock_checklist")
    assert not hasattr(skill, "execution_plan")
    assert not hasattr(skill, "execute")


def test_registry_and_manager_do_not_execute_tools(tmp_path: Path) -> None:
    write_skill(
        tmp_path,
        name="directory_only",
        required_tools="mock_weather",
        optional_tools="camera_scene",
    )
    manager = SkillManager(loader=SkillLoader(tmp_path))
    discovered = manager.refresh()

    assert discovered[0].required_tools == ("mock_weather",)
    assert manager.get_summary("directory_only").optional_tools == ("camera_scene",)
    assert not hasattr(manager, "execute")


def test_skill_references_do_not_bypass_tool_runtime_validation() -> None:
    registry = SkillRegistry()
    skill = SkillDefinition(
        name="references_missing_tool",
        description="References a missing tool.",
        when_to_use="Use when matching.",
        path=Path("skill/skills/references_missing_tool/SKILL.md"),
        required_tools=("not_registered",),
    )

    registry.register(skill)

    assert registry.get("references_missing_tool").required_tools == ("not_registered",)
    assert not hasattr(registry.get("references_missing_tool"), "tool_manager")
    assert not hasattr(registry.get("references_missing_tool"), "tool")
