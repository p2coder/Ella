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

    def get_summary_for_role(
        self,
        skill_name: str,
        agent_role: str,
    ) -> SkillDefinition | None:
        skill = self.registry.get(skill_name)
        if skill is None or agent_role not in skill.allowed_roles:
            return None
        return skill

    def list_summaries(self) -> tuple[dict[str, str], ...]:
        return self.registry.list_summaries()

    def list_summaries_for_role(
        self,
        agent_role: str,
    ) -> tuple[dict[str, str], ...]:
        return tuple(
            skill.summary()
            for skill in self.registry.list_definitions()
            if agent_role in skill.allowed_roles
        )

    def load_full(self, skill_name: str) -> SkillDefinition:
        if self.registry.get(skill_name) is None:
            raise KeyError(f"skill is not registered: {skill_name}")
        return self.loader.load_full(skill_name)
