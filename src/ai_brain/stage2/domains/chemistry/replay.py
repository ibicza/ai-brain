"""Fail-closed event-derived replay classification for chemistry result v2."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai_brain.stage2.domains.chemistry.calculations import (
    DEFAULT_ROUNDING_SPEC,
    ROUNDING_POLICY,
)
from ai_brain.stage2.domains.chemistry.knowledge_snapshot import (
    claim_state_hash,
    source_state_hash,
)
from ai_brain.stage2.domains.chemistry.models import (
    ChemistryReplayStatus,
    ChemistryResultBundle,
)
from ai_brain.stage2.domains.chemistry.version import (
    CHEMISTRY_ATOMIC_WEIGHT_POLICY,
    CHEMISTRY_CALCULATION_POLICY_VERSION,
    CHEMISTRY_DOMAIN_VERSION,
    CHEMISTRY_FORMULA_GRAMMAR_VERSION,
    CHEMISTRY_RESULT_SCHEMA_VERSION,
)
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.models import (
    ClaimStatus,
    EvidenceConflictState,
    SourceStatus,
)


def replay_chemistry_result(
    result: ChemistryResultBundle | dict[str, Any],
    memory: FactMemory,
    manifest: dict[str, Any],
) -> ChemistryReplayStatus:
    try:
        bundle = (
            result if isinstance(result, ChemistryResultBundle) else _from_dict(result)
        )
        body = asdict(bundle)
        digest = body.pop("result_hash")
        if content_hash(body) != digest:
            return ChemistryReplayStatus.INVALID_RESULT
        if (
            bundle.domain_version != CHEMISTRY_DOMAIN_VERSION
            or bundle.result_schema_version != CHEMISTRY_RESULT_SCHEMA_VERSION
        ):
            return ChemistryReplayStatus.INCOMPATIBLE_DOMAIN_VERSION
        if bundle.domain_manifest_hash != manifest.get("domain_manifest_hash"):
            return ChemistryReplayStatus.STALE_DOMAIN_MANIFEST
        if bundle.atomic_weight_policy != CHEMISTRY_ATOMIC_WEIGHT_POLICY:
            return ChemistryReplayStatus.STALE_ATOMIC_WEIGHT_POLICY
        if bundle.formula_grammar_version != CHEMISTRY_FORMULA_GRAMMAR_VERSION:
            return ChemistryReplayStatus.STALE_FORMULA_GRAMMAR
        if bundle.calculation_policy_version != CHEMISTRY_CALCULATION_POLICY_VERSION:
            return ChemistryReplayStatus.STALE_TOOL_IMPLEMENTATION
        if (
            bundle.rounding_policy != ROUNDING_POLICY
            or bundle.rounding_policy_hash != content_hash(DEFAULT_ROUNDING_SPEC)
        ):
            return ChemistryReplayStatus.STALE_ROUNDING_POLICY
        if not set(bundle.derivation_hashes) <= set(
            manifest.get("source_derivation_hashes", ())
        ):
            return ChemistryReplayStatus.STALE_DERIVATION_CHAIN

        current_claim_hashes = []
        current_claim_states = []
        for claim_id in bundle.claim_ids:
            state = memory.get_claim_state(claim_id)
            if state.status == ClaimStatus.RETRACTED:
                return ChemistryReplayStatus.RETRACTED_ELEMENT_CLAIM
            if state.status == ClaimStatus.SUPERSEDED:
                return ChemistryReplayStatus.SUPERSEDED_ELEMENT_CLAIM
            if state.status not in {ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED}:
                return ChemistryReplayStatus.CONFLICTING_ATOMIC_WEIGHT
            if (
                state.evidence_conflict_state == EvidenceConflictState.CONTESTED
                or state.contradicting_evidence_ids
            ):
                return ChemistryReplayStatus.CONTRADICTING_EVIDENCE
            current_claim_hashes.append(state.record.claim_record_hash)
            current_claim_states.append(claim_state_hash(state))
        if tuple(sorted(current_claim_hashes)) != tuple(sorted(bundle.claims_used)):
            return ChemistryReplayStatus.STALE_ELEMENT_CLAIM
        if tuple(sorted(current_claim_states)) != tuple(
            sorted(bundle.claim_state_hashes)
        ):
            return ChemistryReplayStatus.STALE_ELEMENT_CLAIM

        current_evidence = tuple(
            sorted(
                memory.verify_evidence(value).evidence_hash
                for value in bundle.evidence_ids
            )
        )
        if current_evidence != tuple(sorted(bundle.evidence_hashes)):
            return ChemistryReplayStatus.STALE_EVIDENCE

        source_hashes = []
        source_states = []
        for source_id in bundle.source_ids:
            state = memory.get_source_state(source_id)
            if state.status == SourceStatus.RETRACTED:
                return ChemistryReplayStatus.RETRACTED_SOURCE
            if state.status != SourceStatus.ACTIVE:
                return ChemistryReplayStatus.STALE_SOURCE
            source_hashes.append(state.record.record_hash)
            source_states.append(source_state_hash(state))
        if tuple(sorted(source_hashes)) != tuple(sorted(bundle.source_hashes)):
            return ChemistryReplayStatus.STALE_SOURCE
        if tuple(sorted(source_states)) != tuple(sorted(bundle.source_state_hashes)):
            return ChemistryReplayStatus.STALE_SOURCE
        if bundle.fact_memory_snapshot_hash != memory.database.snapshot_hash():
            return ChemistryReplayStatus.STALE_FACT_MEMORY
        return ChemistryReplayStatus.CURRENT
    except (KeyError, TypeError, ValueError):
        return ChemistryReplayStatus.INVALID_RESULT


def _from_dict(result: dict[str, Any]) -> ChemistryResultBundle:
    tuple_fields = {
        "claims_used",
        "claim_ids",
        "claim_state_hashes",
        "evidence_ids",
        "evidence_hashes",
        "source_ids",
        "source_hashes",
        "source_state_hashes",
        "derivation_hashes",
        "calculation_steps",
        "warnings",
    }
    return ChemistryResultBundle(
        **{
            key: tuple(value) if key in tuple_fields else value
            for key, value in result.items()
        }
    )
