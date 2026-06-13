from pathlib import Path

from skill.loader import SkillLoader
from skill.registry import SkillDefinition, SkillRegistry


def test_skill_registry_registers_and_looks_up_skill_summary():
    registry = SkillRegistry()
    skill = SkillDefinition(
        name="going_out",
        description="Prepare a short reminder before the user leaves.",
        when_to_use="Use when the user says they are heading out.",
        path=Path("skill/skills/going_out/SKILL.md"),
    )

    registry.register(skill)

    assert registry.get("going_out") == skill
    assert registry.list_summaries() == (
        {
            "name": "going_out",
            "description": "Prepare a short reminder before the user leaves.",
            "when_to_use": "Use when the user says they are heading out.",
        },
    )


def test_skill_loader_loads_going_out_summary_from_skill_file():
    loader = SkillLoader()

    skill = loader.load_summary("going_out")

    assert skill.name == "going_out"
    assert "leaving" in skill.description.lower()
    assert "heading out" in skill.when_to_use.lower()
    assert skill.path == Path("skill/skills/going_out/SKILL.md")
    assert skill.content is None


def test_skill_loader_loads_full_skill_only_when_requested():
    loader = SkillLoader()

    summary = loader.load_summary("going_out")
    full_skill = loader.load_full("going_out")

    assert summary.content is None
    assert full_skill.content is not None
    assert "MVP going-out reminder scenario" in full_skill.content
    assert full_skill.name == summary.name


def test_registry_can_discover_going_out_without_executing_it():
    loader = SkillLoader()
    registry = SkillRegistry()

    registry.register_all(loader.discover_summaries())

    assert registry.get("going_out") is not None
    assert registry.list_summaries()[0]["name"] == "going_out"
    assert not hasattr(registry.get("going_out"), "run")
