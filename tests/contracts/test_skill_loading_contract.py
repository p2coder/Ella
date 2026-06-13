from pathlib import Path

from skill import SkillLoader, SkillRegistry


def test_going_out_skill_is_discoverable_from_summary_metadata():
    loader = SkillLoader()
    registry = SkillRegistry()

    summaries = loader.discover_summaries()
    registry.register_all(summaries)
    going_out = registry.get("going_out")

    assert going_out is not None
    assert going_out.path == Path("skill/skills/going_out/SKILL.md")
    assert "leaving" in going_out.description.lower()
    assert "heading out" in going_out.when_to_use.lower()
    assert going_out.content is None
    assert not hasattr(going_out, "run")


def test_full_skill_content_is_loaded_only_after_explicit_request():
    loader = SkillLoader()

    summary = loader.load_summary("going_out")
    full_skill = loader.load_full("going_out")

    assert summary.content is None
    assert full_skill.name == summary.name
    assert full_skill.description == summary.description
    assert full_skill.when_to_use == summary.when_to_use
    assert full_skill.content is not None
    assert "# going_out" in full_skill.content
    assert "does not execute tools" in full_skill.content
    assert "call external APIs" in full_skill.content
