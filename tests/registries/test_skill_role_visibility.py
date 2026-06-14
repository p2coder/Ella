from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from skill.loader import SkillLoader
from skill.manager import SkillManager
from skill.registry import SkillDefinition


def write_skill(
    skills_root: Path,
    *,
    name: str,
    allowed_roles: str | None,
) -> Path:
    skill_dir = skills_root / name
    skill_dir.mkdir(parents=True)
    role_line = "" if allowed_roles is None else f"allowed_roles: {allowed_roles}\n"
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: Description for {name}.\n"
        f"when_to_use: Use {name} for its matching task.\n"
        f"{role_line}"
        "---\n"
        f"\n# {name}\n",
        encoding="utf-8",
    )
    return skill_file


def test_loader_parses_allowed_roles_from_skill_metadata(tmp_path: Path):
    write_skill(
        tmp_path,
        name="specialized",
        allowed_roles="main_agent, specialist_agent",
    )

    skill = SkillLoader(tmp_path).load_summary("specialized")

    assert skill.allowed_roles == ("main_agent", "specialist_agent")


def test_missing_allowed_roles_defaults_to_main_agent(tmp_path: Path):
    write_skill(tmp_path, name="legacy", allowed_roles=None)

    skill = SkillLoader(tmp_path).load_summary("legacy")

    assert skill.allowed_roles == ("main_agent",)


def test_skill_role_metadata_is_immutable():
    skill = SkillDefinition(
        name="fixed",
        description="Fixed skill.",
        when_to_use="Use for a fixed task.",
        path=Path("skill/skills/fixed/SKILL.md"),
        allowed_roles=("main_agent",),
    )

    with pytest.raises(FrozenInstanceError):
        skill.allowed_roles = ("specialist_agent",)


def test_manager_lists_and_resolves_only_summaries_visible_to_role(
    tmp_path: Path,
):
    write_skill(tmp_path, name="main_only", allowed_roles="main_agent")
    write_skill(
        tmp_path,
        name="specialist_only",
        allowed_roles="specialist_agent",
    )
    manager = SkillManager(loader=SkillLoader(tmp_path))
    manager.refresh()

    assert tuple(
        summary["name"]
        for summary in manager.list_summaries_for_role("main_agent")
    ) == ("main_only",)
    assert tuple(
        summary["name"]
        for summary in manager.list_summaries_for_role("specialist_agent")
    ) == ("specialist_only",)
    assert manager.get_summary_for_role("main_only", "main_agent") is not None
    assert manager.get_summary_for_role("main_only", "specialist_agent") is None


def test_going_out_remains_visible_to_main_agent():
    manager = SkillManager()
    manager.refresh()

    skill = manager.get_summary_for_role("going_out", "main_agent")

    assert skill is not None
    assert skill.allowed_roles == ("main_agent",)


def test_visibility_lookup_does_not_load_or_execute_skill(tmp_path: Path):
    write_skill(tmp_path, name="metadata_only", allowed_roles="main_agent")
    manager = SkillManager(loader=SkillLoader(tmp_path))
    manager.refresh()

    skill = manager.get_summary_for_role("metadata_only", "main_agent")

    assert skill is not None
    assert skill.content is None
    assert not hasattr(skill, "run")
