from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    name: str
    description: str
    when_to_use: str
    path: Path
    allowed_roles: tuple[str, ...] = ("main_agent",)
    content: str | None = None

    def summary(self) -> dict[str, str]:
        return {
            "name": self.name,
            "description": self.description,
            "when_to_use": self.when_to_use,
        }


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        self._skills[skill.name] = skill

    def register_all(self, skills: Iterable[SkillDefinition]) -> None:
        for skill in skills:
            self.register(skill)

    def unregister(self, skill_name: str) -> None:
        self._skills.pop(skill_name, None)

    def get(self, skill_name: str) -> SkillDefinition | None:
        return self._skills.get(skill_name)

    def list_summaries(self) -> tuple[dict[str, str], ...]:
        return tuple(skill.summary() for skill in self._skills.values())

    def list_definitions(self) -> tuple[SkillDefinition, ...]:
        return tuple(self._skills.values())
