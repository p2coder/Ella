from dataclasses import dataclass, field

from .loader import SkillLoader
from .registry import SkillDefinition, SkillRegistry


@dataclass(slots=True)
class SkillManager:
    loader: SkillLoader = field(default_factory=SkillLoader)
    registry: SkillRegistry = field(default_factory=SkillRegistry)
    version: int = 0

    def register(self, skill: SkillDefinition) -> None:
        self.registry.register(skill)
        self.version += 1

    def unregister(self, skill_name: str) -> None:
        if self.registry.get(skill_name) is not None:
            self.registry.unregister(skill_name)
            self.version += 1

    def refresh(self) -> tuple[SkillDefinition, ...]:
        discovered = self.loader.discover_summaries()
        current = {skill.name: skill for skill in self.registry.list_definitions()}
        incoming = {skill.name: skill for skill in discovered}
        if current != incoming:
            for skill_name in tuple(current):
                self.registry.unregister(skill_name)
            self.registry.register_all(discovered)
            self.version += 1
        return discovered

    def get_summary(self, skill_name: str) -> SkillDefinition | None:
        return self.registry.get(skill_name)

    def list_summaries(self) -> tuple[dict[str, str], ...]:
        return self.registry.list_summaries()

    def load_full(self, skill_name: str) -> SkillDefinition:
        if self.registry.get(skill_name) is None:
            raise KeyError(f"skill is not registered: {skill_name}")
        return self.loader.load_full(skill_name)
