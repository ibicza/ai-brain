"""Exact-case chemical-element resolution outside the generic alias index."""

from __future__ import annotations

import re

from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.models import (
    EntityResolution,
    EntityResolutionStatus,
)

_SYMBOL = re.compile(r"[A-Z][a-z]?\Z")


def resolve_chemistry_element(
    memory: FactMemory, value: str, language: str | None = None
) -> EntityResolution:
    if not isinstance(value, str) or not value.strip():
        return EntityResolution(EntityResolutionStatus.UNKNOWN_ENTITY, (), "")
    token = value.strip()
    if _SYMBOL.fullmatch(token):
        matches = tuple(
            entity.entity_id
            for entity in memory.list_entities(entity_type="chemical_element")
            if entity.external_identifiers.get("symbol") == token
        )
        return EntityResolution(
            EntityResolutionStatus.EXACT
            if len(matches) == 1
            else EntityResolutionStatus.UNKNOWN_ENTITY,
            matches,
            token,
        )
    if re.fullmatch(r"[A-Za-z]{1,2}", token):
        return EntityResolution(EntityResolutionStatus.UNKNOWN_ENTITY, (), token)
    return memory.resolve_entity(token, language)
