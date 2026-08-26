"""Trusted, CPU-only factual-memory API."""

from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.models import (
    ActorIdentityType,
    FactAnswerBundle,
    FactApprovalEnvelope,
    FactProposal,
    FactQuery,
    PredicateDefinition,
)
from ai_brain.stage2.facts.values import FactValue, FactValueKind

__all__ = [
    "ActorIdentityType",
    "FactAnswerBundle",
    "FactApprovalEnvelope",
    "FactMemory",
    "FactProposal",
    "FactQuery",
    "FactValue",
    "FactValueKind",
    "PredicateDefinition",
]
