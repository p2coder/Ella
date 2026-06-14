from dataclasses import dataclass
from pathlib import Path

from .registry import SkillDefinition


@dataclass(frozen=True, slots=True)
class SkillLoader:
    skills_root: Path = Path("skill/skills")

    def discover_summaries(self) -> tuple[SkillDefinition, ...]:
        if not self.skills_root.exists():
            return ()

        skills = []
        for skill_dir in sorted(self.skills_root.iterdir()):
            skill_file = skill_dir / "SKILL.md"
            if skill_file.is_file():
                skills.append(self._load(skill_file, include_content=False))
        return tuple(skills)

    def load_summary(self, skill_name: str) -> SkillDefinition:
        return self._load(self._skill_path(skill_name), include_content=False)

    def load_full(self, skill_name: str) -> SkillDefinition:
        return self._load(self._skill_path(skill_name), include_content=True)

    def _skill_path(self, skill_name: str) -> Path:
        return self.skills_root / skill_name / "SKILL.md"

    def _load(self, skill_path: Path, include_content: bool) -> SkillDefinition:
        if not skill_path.is_file():
            raise FileNotFoundError(f"skill file not found: {skill_path}")

        raw_content = skill_path.read_text(encoding="utf-8")
        metadata = self._parse_front_matter(raw_content)
        return SkillDefinition(
            name=metadata["name"],
            description=metadata["description"],
            when_to_use=metadata["when_to_use"],
            path=skill_path,
            allowed_roles=self._parse_allowed_roles(metadata.get("allowed_roles")),
            required_tools=self._parse_tool_names(metadata.get("required_tools")),
            optional_tools=self._parse_tool_names(metadata.get("optional_tools")),
            content=raw_content if include_content else None,
        )

    @staticmethod
    def _parse_allowed_roles(value: str | None) -> tuple[str, ...]:
        if value is None:
            return ("main_agent",)
        roles = tuple(role.strip() for role in value.split(",") if role.strip())
        return roles or ("main_agent",)

    @staticmethod
    def _parse_tool_names(value: str | None) -> tuple[str, ...]:
        if value is None:
            return ()
        return tuple(
            tool_name.strip()
            for tool_name in value.split(",")
            if tool_name.strip()
        )

    def _parse_front_matter(self, content: str) -> dict[str, str]:
        lines = content.splitlines()
        if not lines or lines[0] != "---":
            raise ValueError("skill file must start with front matter")

        metadata: dict[str, str] = {}
        for line in lines[1:]:
            if line == "---":
                break
            key, separator, value = line.partition(":")
            if not separator:
                continue
            metadata[key.strip()] = value.strip().strip('"')

        required = ("name", "description", "when_to_use")
        missing = [key for key in required if key not in metadata]
        if missing:
            raise ValueError(f"skill metadata missing fields: {', '.join(missing)}")
        return metadata
