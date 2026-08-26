"""Exact factual entity registry facade."""

from __future__ import annotations

from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.models import EntityRecord, EntityResolution


class EntityRegistry:
    def __init__(self, memory: FactMemory) -> None:
        self.memory = memory

    def add(self, **fields) -> EntityRecord:
        return self.memory.add_entity(**fields)

    def add_alias(self, entity_id: str, alias: str, language: str) -> None:
        self.memory.add_entity_alias(entity_id, alias, language)

    def resolve(self, value: str, language: str | None = None) -> EntityResolution:
        return self.memory.resolve_entity(value, language)
