"""Append-only audit replay facade."""

from __future__ import annotations

from typing import Any

from ai_brain.stage2.facts.memory import FactMemory


def replay_claim_lifecycle(memory: FactMemory, claim_id: str) -> list[dict[str, Any]]:
    return memory.database.audit_replay(claim_id)
