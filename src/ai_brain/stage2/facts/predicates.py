"""Schema-driven factual predicate registry facade."""

from __future__ import annotations

from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.models import PredicateDefinition


class PredicateRegistry:
    def __init__(self, memory: FactMemory) -> None:
        self.memory = memory

    def add(self, **fields) -> PredicateDefinition:
        return self.memory.add_predicate(**fields)
