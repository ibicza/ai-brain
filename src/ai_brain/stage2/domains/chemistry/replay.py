"""Fail-closed replay classification for chemistry result schema v3."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai_brain.stage2.domains.chemistry.calculations import (
    DEFAULT_ROUNDING_SPEC,
    ROUNDING_POLICY,
)
from ai_brain.stage2.domains.chemistry.knowledge_snapshot import claim_state_hash
from ai_brain.stage2.domains.chemistry.models import (
    ChemistryReplayStatus,
    ChemistryResultBundle,
)
from ai_brain.stage2.domains.chemistry.provenance import (
    DerivationResolutionError,
    resolve_source_derivation,
    source_state_hash,
)
from ai_brain.stage2.domains.chemistry.source_derivation import (
    EXTRACTION_POLICY_VERSION,
    SOURCE_CHAIN_VERSION,
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
        chain = manifest.get("source_chain", {})
        if (
            bundle.source_chain_version != SOURCE_CHAIN_VERSION
            or bundle.source_chain_version != chain.get("source_chain_version")
            or bundle.source_chain_hash != chain.get("source_chain_hash")
        ):
            return ChemistryReplayStatus.STALE_SOURCE_CHAIN
        if chain.get("extraction_policy_version") != EXTRACTION_POLICY_VERSION:
            return ChemistryReplayStatus.STALE_EXTRACTION_POLICY
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

        claim_status = _verify_claims(bundle, memory)
        if claim_status is not None:
            return claim_status
        current_evidence = tuple(
            sorted(
                memory.verify_evidence(value).evidence_hash
                for value in bundle.evidence_ids
            )
        )
        if current_evidence != tuple(sorted(bundle.evidence_hashes)):
            return ChemistryReplayStatus.STALE_EVIDENCE

        resolutions = []
        source_hashes = []
        source_states = []
        source_snapshots = []
        for source_id in bundle.derived_source_ids:
            state = memory.get_source_state(source_id)
            if state.status == SourceStatus.RETRACTED:
                return ChemistryReplayStatus.RETRACTED_SOURCE
            if state.status != SourceStatus.ACTIVE:
                return ChemistryReplayStatus.STALE_DERIVED_SOURCE
            source_hashes.append(state.record.record_hash)
            source_states.append(source_state_hash(state))
            source_snapshots.append(state.record.snapshot_hash)
            try:
                resolutions.append(
                    resolve_source_derivation(
                        state.record,
                        chain,
                        memory,
                        source_record_bindings=tuple(
                            manifest.get("source_record_bindings", ())
                        ),
                    )
                )
            except DerivationResolutionError as error:
                return _resolution_status(error.code)
        if tuple(sorted(source_hashes)) != tuple(
            sorted(bundle.derived_source_record_hashes)
        ):
            return ChemistryReplayStatus.STALE_DERIVED_SOURCE
        if tuple(sorted(source_snapshots)) != tuple(
            sorted(bundle.derived_source_snapshot_hashes)
        ):
            return ChemistryReplayStatus.DERIVATION_CONTENT_MISMATCH
        if tuple(sorted(source_states)) != tuple(
            sorted(bundle.derived_source_state_hashes)
        ):
            return ChemistryReplayStatus.STALE_DERIVED_SOURCE

        if tuple(
            sorted(item.derivation.derivation_id for item in resolutions)
        ) != tuple(sorted(bundle.derivation_ids)):
            return ChemistryReplayStatus.DERIVATION_SOURCE_MISMATCH
        if tuple(
            sorted(item.derivation.derivation_hash for item in resolutions)
        ) != tuple(sorted(bundle.derivation_hashes)):
            return ChemistryReplayStatus.STALE_DERIVATION_CHAIN
        if tuple(
            sorted(item.derivation.derivation_method.value for item in resolutions)
        ) != tuple(sorted(bundle.derivation_methods)):
            return ChemistryReplayStatus.DERIVATION_METHOD_CHANGED

        upstream = _upstream_rows(resolutions)
        if tuple(row[0] for row in upstream) != tuple(
            sorted(bundle.upstream_source_ids)
        ):
            return ChemistryReplayStatus.STALE_UPSTREAM_SOURCE
        if tuple(sorted(row[1] for row in upstream)) != tuple(
            sorted(bundle.upstream_source_record_hashes)
        ):
            return ChemistryReplayStatus.STALE_UPSTREAM_SOURCE
        if tuple(sorted(row[2] for row in upstream)) != tuple(
            sorted(bundle.upstream_source_snapshot_hashes)
        ):
            return ChemistryReplayStatus.STALE_UPSTREAM_SOURCE
        if tuple(sorted(row[3] for row in upstream)) != tuple(
            sorted(bundle.upstream_source_state_hashes)
        ):
            return ChemistryReplayStatus.STALE_UPSTREAM_SOURCE
        current_events = tuple(
            sorted({row[4] for row in upstream}, key=lambda value: value or "")
        )
        if current_events != tuple(
            sorted(bundle.upstream_status_event_hashes, key=lambda value: value or "")
        ):
            return ChemistryReplayStatus.STALE_UPSTREAM_SOURCE
        all_field_hashes = {
            item.evidence_hash
            for resolution in resolutions
            for item in resolution.derivation.field_level_mappings
        }
        if not set(bundle.field_mapping_evidence_hashes) <= all_field_hashes:
            return ChemistryReplayStatus.DERIVATION_CONTENT_MISMATCH
        return ChemistryReplayStatus.CURRENT
    except (KeyError, TypeError, ValueError):
        return ChemistryReplayStatus.INVALID_RESULT


def _verify_claims(
    bundle: ChemistryResultBundle, memory: FactMemory
) -> ChemistryReplayStatus | None:
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
    if tuple(sorted(current_claim_states)) != tuple(sorted(bundle.claim_state_hashes)):
        return ChemistryReplayStatus.STALE_ELEMENT_CLAIM
    return None


def _upstream_rows(resolutions: list[Any]) -> tuple[tuple[Any, ...], ...]:
    rows: dict[str, tuple[Any, ...]] = {}
    for resolution in resolutions:
        for row in zip(
            resolution.upstream_source_ids,
            resolution.upstream_source_record_hashes,
            resolution.upstream_source_snapshot_hashes,
            resolution.upstream_source_state_hashes,
            resolution.upstream_status_event_hashes,
            strict=True,
        ):
            rows[row[0]] = row
    return tuple(rows[key] for key in sorted(rows))


def _resolution_status(code: str) -> ChemistryReplayStatus:
    mapping = {
        "RETRACTED_UPSTREAM_SOURCE": ChemistryReplayStatus.RETRACTED_UPSTREAM_SOURCE,
        "UNAVAILABLE_UPSTREAM_SOURCE": ChemistryReplayStatus.UNAVAILABLE_UPSTREAM_SOURCE,
        "STALE_UPSTREAM_SOURCE": ChemistryReplayStatus.STALE_UPSTREAM_SOURCE,
        "DERIVATION_SOURCE_MISMATCH": ChemistryReplayStatus.DERIVATION_SOURCE_MISMATCH,
        "DERIVATION_CONTENT_MISMATCH": ChemistryReplayStatus.DERIVATION_CONTENT_MISMATCH,
        "DERIVATION_METHOD_CHANGED": ChemistryReplayStatus.DERIVATION_METHOD_CHANGED,
        "STALE_EXTRACTION_POLICY": ChemistryReplayStatus.STALE_EXTRACTION_POLICY,
        "STALE_SOURCE_CHAIN": ChemistryReplayStatus.STALE_SOURCE_CHAIN,
    }
    return mapping.get(code, ChemistryReplayStatus.STALE_DERIVATION_CHAIN)


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
        "derived_source_ids",
        "derived_source_record_hashes",
        "derived_source_snapshot_hashes",
        "derived_source_state_hashes",
        "derivation_ids",
        "derivation_hashes",
        "derivation_methods",
        "upstream_source_ids",
        "upstream_source_record_hashes",
        "upstream_source_snapshot_hashes",
        "upstream_source_state_hashes",
        "upstream_status_event_hashes",
        "field_mapping_evidence_hashes",
        "calculation_steps",
        "warnings",
    }
    return ChemistryResultBundle(
        **{
            key: tuple(value) if key in tuple_fields else value
            for key, value in result.items()
        }
    )
