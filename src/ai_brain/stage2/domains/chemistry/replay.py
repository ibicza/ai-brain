"""Fail-closed replay classification for chemistry result bundles."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai_brain.stage2.domains.chemistry.models import (
    ChemistryReplayStatus,
    ChemistryResultBundle,
)
from ai_brain.stage2.domains.chemistry.version import (
    CHEMISTRY_ATOMIC_WEIGHT_POLICY,
    CHEMISTRY_CALCULATION_POLICY_VERSION,
    CHEMISTRY_DOMAIN_VERSION,
    CHEMISTRY_FORMULA_GRAMMAR_VERSION,
)
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.memory import FactMemory


def replay_chemistry_result(
    result: ChemistryResultBundle | dict[str, Any],
    memory: FactMemory,
    manifest: dict[str, Any],
) -> ChemistryReplayStatus:
    try:
        bundle = (
            result
            if isinstance(result, ChemistryResultBundle)
            else ChemistryResultBundle(**result)
        )
        body = asdict(bundle)
        digest = body.pop("result_hash")
        if content_hash(body) != digest:
            return ChemistryReplayStatus.INVALID_RESULT
        if bundle.domain_version != CHEMISTRY_DOMAIN_VERSION:
            return ChemistryReplayStatus.INCOMPATIBLE_DOMAIN_VERSION
        if bundle.domain_manifest_hash != manifest.get("domain_manifest_hash"):
            return ChemistryReplayStatus.STALE_DOMAIN_MANIFEST
        if bundle.atomic_weight_policy != CHEMISTRY_ATOMIC_WEIGHT_POLICY:
            return ChemistryReplayStatus.STALE_ATOMIC_WEIGHT_POLICY
        if bundle.formula_grammar_version != CHEMISTRY_FORMULA_GRAMMAR_VERSION:
            return ChemistryReplayStatus.STALE_FORMULA_GRAMMAR
        if bundle.calculation_policy_version != CHEMISTRY_CALCULATION_POLICY_VERSION:
            return ChemistryReplayStatus.STALE_TOOL_IMPLEMENTATION
        if bundle.fact_memory_snapshot_hash != memory.database.snapshot_hash():
            return ChemistryReplayStatus.STALE_FACT_MEMORY
        with memory.database.connect() as connection:
            current_claims = {
                row[0]
                for row in connection.execute("SELECT canonical_claim_hash FROM claims")
            }
            current_evidence = {
                row[0]
                for row in connection.execute("SELECT evidence_hash FROM evidence")
            }
            current_sources = {
                row[0]
                for row in connection.execute(
                    "SELECT record_hash FROM sources WHERE status = 'ACTIVE'"
                )
            }
        if not set(bundle.claims_used) <= current_claims:
            return ChemistryReplayStatus.STALE_ELEMENT_CLAIM
        if not set(bundle.evidence_hashes) <= current_evidence:
            return ChemistryReplayStatus.STALE_EVIDENCE
        if not set(bundle.source_hashes) <= current_sources:
            return ChemistryReplayStatus.STALE_SOURCE
        return ChemistryReplayStatus.CURRENT
    except (KeyError, TypeError, ValueError):
        return ChemistryReplayStatus.INVALID_RESULT
