"""Exact current-state replay for fact-derived educational graphs."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ai_brain.stage2.domains.chemistry.knowledge_snapshot import (
    ChemistryKnowledgeError,
    claim_state_hash,
    validate_fact_provenance,
)
from ai_brain.stage2.education.models import (
    EducationalReplayStatus,
    FactReplayClaimBinding,
    FactReplayDescriptor,
)
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.models import ClaimStatus, EvidenceConflictState


def make_fact_replay_descriptor(
    memory,
    manifest: dict[str, Any],
    *,
    subject_entity_id: str,
    requested_predicate: str,
    binding_predicates: tuple[str, ...],
    language: str,
    request_mode: str | None,
    role: str,
    current_value: Any,
    bindings: tuple[Any, ...],
) -> FactReplayDescriptor:
    if len(bindings) != len(binding_predicates) or not bindings:
        raise ValueError("fact replay requires one binding per exact predicate")
    rows = tuple(
        _claim_binding(memory, predicate, binding)
        for predicate, binding in zip(binding_predicates, bindings, strict=True)
    )
    answer_hash = content_hash(
        {
            "subject_entity_id": subject_entity_id,
            "requested_predicate": requested_predicate,
            "request_mode": request_mode,
            "language": language,
            "role": role,
            "binding_hashes": tuple(row.binding_hash for row in rows),
            "current_value": current_value,
        }
    )
    body = {
        "subject_entity_id": subject_entity_id,
        "requested_predicate": requested_predicate,
        "request_mode": request_mode,
        "language": language,
        "role": role,
        "bindings": rows,
        "source_chain_version": manifest["source_chain_version"],
        "source_chain_hash": manifest["source_chain_hash"],
        "fact_memory_snapshot_hash": manifest["fact_memory_snapshot_hash"],
        "current_value": current_value,
        "answer_hash": answer_hash,
    }
    return FactReplayDescriptor(**body, descriptor_hash=content_hash(body))


def descriptor_from_dict(row: dict[str, Any]) -> FactReplayDescriptor:
    if set(row) != set(FactReplayDescriptor.__dataclass_fields__):
        raise ValueError("invalid fact replay descriptor schema")
    bindings = tuple(_binding_from_dict(item) for item in row["bindings"])
    return FactReplayDescriptor(**{**row, "bindings": bindings})


def verify_descriptor_hash(descriptor: FactReplayDescriptor) -> None:
    body = asdict(descriptor)
    digest = body.pop("descriptor_hash")
    if content_hash(body) != digest:
        raise ValueError("fact replay descriptor hash mismatch")
    expected_answer_hash = content_hash(
        {
            "subject_entity_id": descriptor.subject_entity_id,
            "requested_predicate": descriptor.requested_predicate,
            "request_mode": descriptor.request_mode,
            "language": descriptor.language,
            "role": descriptor.role,
            "binding_hashes": tuple(row.binding_hash for row in descriptor.bindings),
            "current_value": descriptor.current_value,
        }
    )
    if descriptor.answer_hash != expected_answer_hash:
        raise ValueError("fact replay answer hash mismatch")


def replay_fact_descriptor(
    descriptor: FactReplayDescriptor, memory, manifest: dict[str, Any]
) -> EducationalReplayStatus:
    try:
        verify_descriptor_hash(descriptor)
    except (TypeError, ValueError):
        return EducationalReplayStatus.INVALID_SOURCE_RESULT
    if (
        descriptor.source_chain_version != manifest["source_chain_version"]
        or descriptor.source_chain_hash != manifest["source_chain_hash"]
    ):
        return EducationalReplayStatus.STALE_SOURCE_CHAIN
    if descriptor.fact_memory_snapshot_hash != manifest["fact_memory_snapshot_hash"]:
        return EducationalReplayStatus.STALE_FACT_MEMORY
    current_values: list[dict[str, Any]] = []
    for stored in descriptor.bindings:
        try:
            state = memory.get_claim_state(stored.claim_id)
        except (KeyError, TypeError, ValueError):
            return EducationalReplayStatus.STALE_CLAIM
        if (
            state.status not in {ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED}
            or state.evidence_conflict_state is EvidenceConflictState.CONTESTED
            or state.contradicting_evidence_ids
        ):
            return EducationalReplayStatus.STALE_CLAIM
        value = state.record.object_value.to_dict()
        if value != stored.current_value:
            return EducationalReplayStatus.STALE_FACT_VALUE
        if (
            state.record.claim_record_hash != stored.claim_record_hash
            or claim_state_hash(state) != stored.claim_state_hash
        ):
            return EducationalReplayStatus.STALE_CLAIM
        try:
            current = validate_fact_provenance(
                memory,
                manifest,
                descriptor.subject_entity_id,
                stored.predicate_id,
            )
        except KeyError as error:
            missing = str(error.args[0]).casefold() if error.args else ""
            return (
                EducationalReplayStatus.STALE_EVIDENCE
                if missing.startswith("ev_")
                else EducationalReplayStatus.STALE_SOURCE
            )
        except (ChemistryKnowledgeError, TypeError, ValueError) as error:
            return _status_from_provenance_error(str(error))
        if current.claim_id != stored.claim_id:
            return EducationalReplayStatus.STALE_CLAIM
        if (
            current.evidence_ids != stored.evidence_ids
            or current.evidence_hashes != stored.evidence_hashes
        ):
            return EducationalReplayStatus.STALE_EVIDENCE
        if (
            current.source_ids != stored.source_ids
            or current.source_record_hashes != stored.source_record_hashes
            or current.source_state_hashes != stored.source_state_hashes
        ):
            return EducationalReplayStatus.STALE_SOURCE
        if (
            current.derivation_ids != stored.derivation_ids
            or current.derivation_hashes != stored.derivation_hashes
        ):
            return EducationalReplayStatus.STALE_DERIVATION
        if (
            current.upstream_source_ids != stored.upstream_source_ids
            or current.upstream_source_record_hashes
            != stored.upstream_source_record_hashes
            or current.upstream_source_snapshot_hashes
            != stored.upstream_source_snapshot_hashes
            or current.upstream_source_state_hashes
            != stored.upstream_source_state_hashes
        ):
            return EducationalReplayStatus.STALE_UPSTREAM_SOURCE
        if current.binding_hash != stored.binding_hash:
            return EducationalReplayStatus.STALE_DERIVATION
        current_values.append(value)
    replayed = _result_value(descriptor, current_values)
    if replayed != descriptor.current_value:
        return EducationalReplayStatus.STALE_FACT_VALUE
    return EducationalReplayStatus.CURRENT


def _claim_binding(memory, predicate: str, binding) -> FactReplayClaimBinding:
    state = memory.get_claim_state(binding.claim_id)
    body = {
        "predicate_id": predicate,
        "current_value": state.record.object_value.to_dict(),
        "claim_id": binding.claim_id,
        "claim_record_hash": binding.claim_record_hash,
        "claim_state_hash": binding.claim_state_hash,
        "evidence_ids": binding.evidence_ids,
        "evidence_hashes": binding.evidence_hashes,
        "source_ids": binding.source_ids,
        "source_record_hashes": binding.source_record_hashes,
        "source_state_hashes": binding.source_state_hashes,
        "derivation_ids": binding.derivation_ids,
        "derivation_hashes": binding.derivation_hashes,
        "upstream_source_ids": binding.upstream_source_ids,
        "upstream_source_record_hashes": binding.upstream_source_record_hashes,
        "upstream_source_snapshot_hashes": binding.upstream_source_snapshot_hashes,
        "upstream_source_state_hashes": binding.upstream_source_state_hashes,
    }
    return FactReplayClaimBinding(**body, binding_hash=binding.binding_hash)


def _binding_from_dict(row: dict[str, Any]) -> FactReplayClaimBinding:
    if set(row) != set(FactReplayClaimBinding.__dataclass_fields__):
        raise ValueError("invalid fact replay claim binding schema")
    tuple_fields = {
        "evidence_ids",
        "evidence_hashes",
        "source_ids",
        "source_record_hashes",
        "source_state_hashes",
        "derivation_ids",
        "derivation_hashes",
        "upstream_source_ids",
        "upstream_source_record_hashes",
        "upstream_source_snapshot_hashes",
        "upstream_source_state_hashes",
    }
    return FactReplayClaimBinding(
        **{
            key: tuple(value) if key in tuple_fields else value
            for key, value in row.items()
        }
    )


def _result_value(
    descriptor: FactReplayDescriptor, values: list[dict[str, Any]]
) -> Any:
    if descriptor.request_mode == "STANDARD_INTERVAL":
        by_predicate = {
            row.predicate_id: value["value"]
            for row, value in zip(descriptor.bindings, values, strict=True)
        }
        return {
            "lower": by_predicate["standard_atomic_weight_lower"],
            "upper": by_predicate["standard_atomic_weight_upper"],
        }
    return values[0]["value"]


def _status_from_provenance_error(message: str) -> EducationalReplayStatus:
    lowered = message.casefold()
    if "upstream" in lowered:
        return EducationalReplayStatus.STALE_UPSTREAM_SOURCE
    if "derivation" in lowered or "field" in lowered:
        return EducationalReplayStatus.STALE_DERIVATION
    if "evidence" in lowered:
        return EducationalReplayStatus.STALE_EVIDENCE
    if "source" in lowered:
        return EducationalReplayStatus.STALE_SOURCE
    return EducationalReplayStatus.STALE_CLAIM
