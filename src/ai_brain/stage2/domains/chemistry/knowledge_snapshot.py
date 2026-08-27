"""Current-state FactMemory-bound chemistry knowledge snapshots (schema v2)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ai_brain.stage2.domains.chemistry.models import (
    AtomicWeightAnswerBundle,
    AtomicWeightKind,
    AtomicWeightRecordV2,
    AtomicWeightRequest,
    ChemistryKnowledgeSnapshotV2,
    ChemistryRoundingSpec,
    KnowledgeBinding,
)
from ai_brain.stage2.domains.chemistry.resolver import resolve_chemistry_element
from ai_brain.stage2.domains.chemistry.version import (
    CHEMISTRY_ATOMIC_WEIGHT_POLICY,
    CHEMISTRY_CALCULATION_POLICY_VERSION,
    CHEMISTRY_FORMULA_GRAMMAR_VERSION,
    CHEMISTRY_KNOWLEDGE_SNAPSHOT_VERSION,
    CHEMISTRY_SOURCE_POLICY_VERSION,
)
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.models import (
    ClaimStatus,
    EvidenceConflictState,
    EvidenceRelation,
    QueryStatus,
    SourceStatus,
)
from ai_brain.stage2.facts.values import FactValue


class ChemistryKnowledgeError(ValueError):
    pass


@dataclass(frozen=True)
class _CurrentValue:
    value: FactValue
    binding: KnowledgeBinding
    recorded_at: str


def build_knowledge_snapshot(
    memory: FactMemory,
    domain_manifest_hash: str,
    symbols: tuple[str, ...] | None = None,
) -> ChemistryKnowledgeSnapshotV2:
    selected = (
        _element_symbols(memory) if symbols is None else tuple(sorted(set(symbols)))
    )
    records_and_bindings = tuple(
        _atomic_weight_record(memory, symbol) for symbol in selected
    )
    records = tuple(item[0] for item in records_and_bindings)
    bindings = tuple(
        value.binding
        for _, record_bindings in records_and_bindings
        for value in record_bindings
    )
    avogadro = _single(memory, "constant.avogadro", "avogadro_constant")
    bindings += (avogadro.binding,)
    body = {
        "knowledge_snapshot_version": CHEMISTRY_KNOWLEDGE_SNAPSHOT_VERSION,
        "domain_manifest_hash": domain_manifest_hash,
        "fact_memory_snapshot_hash": memory.database.snapshot_hash(),
        "atomic_weight_policy": CHEMISTRY_ATOMIC_WEIGHT_POLICY,
        "source_policy_version": CHEMISTRY_SOURCE_POLICY_VERSION,
        "formula_grammar_version": CHEMISTRY_FORMULA_GRAMMAR_VERSION,
        "calculation_policy_version": CHEMISTRY_CALCULATION_POLICY_VERSION,
        "rounding_policy_hash": content_hash(ChemistryRoundingSpec()),
        "element_records": records,
        "avogadro_constant": str(avogadro.value.value),
        "avogadro_claim_id": avogadro.binding.claim_id,
        "avogadro_claim_record_hash": avogadro.binding.claim_record_hash,
        "avogadro_claim_state_hash": avogadro.binding.claim_state_hash,
        "avogadro_evidence_hashes": avogadro.binding.evidence_hashes,
        "avogadro_source_record_hashes": avogadro.binding.source_record_hashes,
        "bindings": bindings,
        "claim_ids": tuple(sorted(item.claim_id for item in bindings)),
        "claim_record_hashes": tuple(
            sorted(item.claim_record_hash for item in bindings)
        ),
        "claim_state_hashes": tuple(sorted(item.claim_state_hash for item in bindings)),
        "evidence_hashes": tuple(
            sorted({value for item in bindings for value in item.evidence_hashes})
        ),
        "source_record_hashes": tuple(
            sorted({value for item in bindings for value in item.source_record_hashes})
        ),
        "source_state_hashes": tuple(
            sorted({value for item in bindings for value in item.source_state_hashes})
        ),
        "derivation_hashes": tuple(
            sorted({value for item in bindings for value in item.derivation_hashes})
        ),
        "created_at": max(
            (
                item.recorded_at
                for item in (
                    *tuple(
                        value for _, values in records_and_bindings for value in values
                    ),
                    avogadro,
                )
            ),
            default="1970-01-01T00:00:00Z",
        ),
    }
    return ChemistryKnowledgeSnapshotV2(**body, snapshot_hash=content_hash(body))


def verify_knowledge_snapshot(
    snapshot: ChemistryKnowledgeSnapshotV2,
    memory: FactMemory,
    expected_domain_manifest_hash: str,
) -> None:
    body = asdict(snapshot)
    digest = body.pop("snapshot_hash")
    if content_hash(body) != digest:
        raise ChemistryKnowledgeError("chemistry knowledge snapshot hash mismatch")
    if snapshot.knowledge_snapshot_version != CHEMISTRY_KNOWLEDGE_SNAPSHOT_VERSION:
        raise ChemistryKnowledgeError("incompatible chemistry knowledge snapshot")
    if snapshot.domain_manifest_hash != expected_domain_manifest_hash:
        raise ChemistryKnowledgeError("stale chemistry domain manifest")
    if snapshot.fact_memory_snapshot_hash != memory.database.snapshot_hash():
        raise ChemistryKnowledgeError("stale chemistry FactMemory snapshot")
    if snapshot.atomic_weight_policy != CHEMISTRY_ATOMIC_WEIGHT_POLICY:
        raise ChemistryKnowledgeError("stale atomic-weight policy")
    current = build_knowledge_snapshot(
        memory,
        expected_domain_manifest_hash,
        tuple(record.symbol for record in snapshot.element_records),
    )
    if current.snapshot_hash != snapshot.snapshot_hash:
        raise ChemistryKnowledgeError(
            "chemistry current claim/evidence/source state changed"
        )


def atomic_weight_answer(
    memory: FactMemory,
    domain_manifest_hash: str,
    element: str,
    *,
    language: str = "en",
    requested: AtomicWeightRequest | str = AtomicWeightRequest.ALL,
) -> AtomicWeightAnswerBundle:
    resolution = resolve_chemistry_element(memory, element, language)
    if len(resolution.entity_ids) != 1:
        raise ChemistryKnowledgeError("unknown or case-invalid chemistry element")
    entity = memory.get_entity(resolution.entity_ids[0])
    symbol = entity.external_identifiers["symbol"]
    snapshot = build_knowledge_snapshot(memory, domain_manifest_hash, (symbol,))
    record = snapshot.element_records[0]
    selected = AtomicWeightRequest(requested)
    warnings = (
        ("STANDARD_INTERVAL_REPRESENTS_NATURAL_VARIABILITY",)
        if record.standard_kind == AtomicWeightKind.INTERVAL
        else ("STANDARD_UNCERTAINTY_NOT_A_NATURAL_VARIABILITY_INTERVAL",)
    )
    body = {
        "element_entity_id": record.element_entity_id,
        "exact_symbol": record.symbol,
        "atomic_number": record.atomic_number,
        "standard_kind": record.standard_kind,
        "standard_nominal": record.standard_nominal,
        "standard_uncertainty": record.standard_uncertainty,
        "standard_interval_lower": record.standard_interval_lower,
        "standard_interval_upper": record.standard_interval_upper,
        "abridged_value": record.abridged_value,
        "abridged_uncertainty": record.abridged_uncertainty,
        "value_requested": selected,
        "source_record_hashes": record.source_record_hashes,
        "evidence_hashes": record.evidence_hashes,
        "derivation_hashes": record.derivation_hashes,
        "fact_memory_snapshot_hash": snapshot.fact_memory_snapshot_hash,
        "warnings": warnings,
    }
    return AtomicWeightAnswerBundle(**body, answer_hash=content_hash(body))


def snapshot_to_dict(snapshot: ChemistryKnowledgeSnapshotV2) -> dict[str, Any]:
    return asdict(snapshot)


def snapshot_from_dict(payload: dict[str, Any]) -> ChemistryKnowledgeSnapshotV2:
    rows = tuple(
        AtomicWeightRecordV2(
            **{
                **row,
                "standard_kind": AtomicWeightKind(row["standard_kind"]),
                "claim_ids": tuple(row["claim_ids"]),
                "claim_record_hashes": tuple(row["claim_record_hashes"]),
                "claim_state_hashes": tuple(row["claim_state_hashes"]),
                "evidence_hashes": tuple(row["evidence_hashes"]),
                "source_record_hashes": tuple(row["source_record_hashes"]),
                "derivation_hashes": tuple(row["derivation_hashes"]),
            }
        )
        for row in payload["element_records"]
    )
    bindings = tuple(
        KnowledgeBinding(
            **{
                **row,
                "evidence_ids": tuple(row["evidence_ids"]),
                "evidence_hashes": tuple(row["evidence_hashes"]),
                "evidence_relations": tuple(row["evidence_relations"]),
                "source_ids": tuple(row["source_ids"]),
                "source_record_hashes": tuple(row["source_record_hashes"]),
                "source_state_hashes": tuple(row["source_state_hashes"]),
                "source_status_event_hashes": tuple(row["source_status_event_hashes"]),
                "derivation_hashes": tuple(row["derivation_hashes"]),
            }
        )
        for row in payload["bindings"]
    )
    normalized = {
        **payload,
        "element_records": rows,
        "bindings": bindings,
        "avogadro_evidence_hashes": tuple(payload["avogadro_evidence_hashes"]),
        "avogadro_source_record_hashes": tuple(
            payload["avogadro_source_record_hashes"]
        ),
        "claim_ids": tuple(payload["claim_ids"]),
        "claim_record_hashes": tuple(payload["claim_record_hashes"]),
        "claim_state_hashes": tuple(payload["claim_state_hashes"]),
        "evidence_hashes": tuple(payload["evidence_hashes"]),
        "source_record_hashes": tuple(payload["source_record_hashes"]),
        "source_state_hashes": tuple(payload["source_state_hashes"]),
        "derivation_hashes": tuple(payload["derivation_hashes"]),
    }
    return ChemistryKnowledgeSnapshotV2(**normalized)


def _element_symbols(memory: FactMemory) -> tuple[str, ...]:
    return tuple(
        sorted(
            entity.external_identifiers["symbol"]
            for entity in memory.list_entities(entity_type="chemical_element")
        )
    )


def _atomic_weight_record(
    memory: FactMemory, symbol: str
) -> tuple[AtomicWeightRecordV2, tuple[_CurrentValue, ...]]:
    resolution = resolve_chemistry_element(memory, symbol, "en")
    if len(resolution.entity_ids) != 1:
        raise ChemistryKnowledgeError(f"unknown exact element symbol: {symbol}")
    entity_id = resolution.entity_ids[0]
    number = _single(memory, entity_id, "atomic_number")
    symbol_value = _single(memory, entity_id, "element_symbol")
    kind_value = _single(memory, entity_id, "atomic_weight_kind")
    abridged = _single(memory, entity_id, "conventional_atomic_weight")
    abridged_uncertainty = _single(
        memory, entity_id, "conventional_atomic_weight_uncertainty"
    )
    standard_notation = _single(memory, entity_id, "atomic_weight_standard_notation")
    abridged_notation = _single(memory, entity_id, "atomic_weight_abridged_notation")
    kind = AtomicWeightKind(str(kind_value.value.value))
    common = (
        number,
        symbol_value,
        kind_value,
        abridged,
        abridged_uncertainty,
        standard_notation,
        abridged_notation,
    )
    if kind == AtomicWeightKind.SINGLE:
        nominal = _single(memory, entity_id, "standard_atomic_weight")
        uncertainty = _single(memory, entity_id, "standard_atomic_weight_uncertainty")
        related = (*common, nominal, uncertainty)
        standard_nominal = str(nominal.value.value)
        standard_uncertainty = str(uncertainty.value.value)
        lower = upper = None
    elif kind == AtomicWeightKind.INTERVAL:
        lower_value = _single(memory, entity_id, "standard_atomic_weight_lower")
        upper_value = _single(memory, entity_id, "standard_atomic_weight_upper")
        related = (*common, lower_value, upper_value)
        standard_nominal = standard_uncertainty = None
        lower = str(lower_value.value.value)
        upper = str(upper_value.value.value)
    else:
        raise ChemistryKnowledgeError(f"unsupported atomic-weight kind: {kind}")
    bindings = tuple(value.binding for value in related)
    body = {
        "element_entity_id": entity_id,
        "symbol": str(symbol_value.value.value),
        "atomic_number": int(number.value.value),
        "standard_kind": kind,
        "standard_nominal": standard_nominal,
        "standard_uncertainty": standard_uncertainty,
        "standard_interval_lower": lower,
        "standard_interval_upper": upper,
        "standard_source_notation": str(standard_notation.value.value),
        "abridged_value": str(abridged.value.value),
        "abridged_uncertainty": str(abridged_uncertainty.value.value),
        "abridged_source_notation": str(abridged_notation.value.value),
        "unit": "1",
        "claim_ids": tuple(sorted(item.claim_id for item in bindings)),
        "claim_record_hashes": tuple(
            sorted(item.claim_record_hash for item in bindings)
        ),
        "claim_state_hashes": tuple(sorted(item.claim_state_hash for item in bindings)),
        "evidence_hashes": tuple(
            sorted({item for binding in bindings for item in binding.evidence_hashes})
        ),
        "source_record_hashes": tuple(
            sorted(
                {item for binding in bindings for item in binding.source_record_hashes}
            )
        ),
        "derivation_hashes": tuple(
            sorted({item for binding in bindings for item in binding.derivation_hashes})
        ),
        "policy_version": CHEMISTRY_SOURCE_POLICY_VERSION,
    }
    return AtomicWeightRecordV2(**body, record_hash=content_hash(body)), related


def _single(memory: FactMemory, subject: str, predicate: str) -> _CurrentValue:
    answer = memory.query(
        memory.make_query(
            subject=subject,
            predicate_id=predicate,
            accepted_statuses=(ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED),
            include_conflicts=True,
            include_evidence=True,
            language="en",
        )
    )
    if answer.answer_status != QueryStatus.EXACT_SINGLE or len(answer.claims) != 1:
        raise ChemistryKnowledgeError(
            f"unsafe current chemistry fact {subject}/{predicate}: {answer.answer_status}"
        )
    selected = answer.claims[0]
    if (
        selected.evidence_conflict_state != EvidenceConflictState.CLEAR
        or selected.contradicting_evidence_ids
        or "CONTRADICTING_EVIDENCE_PRESENT" in answer.warnings
    ):
        raise ChemistryKnowledgeError(
            "contradicting evidence blocks chemistry knowledge"
        )
    state = memory.get_claim_state(selected.claim_id)
    if state.status not in {ClaimStatus.SUPPORTED, ClaimStatus.CORROBORATED}:
        raise ChemistryKnowledgeError(f"inactive chemistry claim: {state.status}")
    record = memory.get_claim_record(selected.claim_id)
    evidence = tuple(
        memory.verify_evidence(value) for value in selected.supporting_evidence_ids
    )
    if not evidence or any(
        value.relation != EvidenceRelation.SUPPORTS for value in evidence
    ):
        raise ChemistryKnowledgeError("approved supporting evidence is required")
    sources = tuple(memory.get_source_state(value.source_id) for value in evidence)
    if any(value.status != SourceStatus.ACTIVE for value in sources):
        raise ChemistryKnowledgeError("inactive source blocks chemistry knowledge")
    derivations = tuple(
        sorted(
            {
                value.record.license_metadata.get("derivation_hash")
                for value in sources
                if value.record.license_metadata.get("derivation_hash")
            }
        )
    )
    if len(derivations) != len({value.source_id for value in evidence}):
        raise ChemistryKnowledgeError("production chemistry evidence lacks derivation")
    binding_body = {
        "claim_id": record.claim_id,
        "claim_record_hash": record.claim_record_hash,
        "claim_state_hash": claim_state_hash(state),
        "claim_status": state.status.value,
        "claim_status_event_hash": state.transaction.status_event_hash,
        "evidence_ids": tuple(value.evidence_id for value in evidence),
        "evidence_hashes": tuple(value.evidence_hash for value in evidence),
        "evidence_relations": tuple(value.relation.value for value in evidence),
        "source_ids": tuple(value.record.source_id for value in sources),
        "source_record_hashes": tuple(value.record.record_hash for value in sources),
        "source_state_hashes": tuple(source_state_hash(value) for value in sources),
        "source_status_event_hashes": tuple(
            value.status_event_hash for value in sources
        ),
        "derivation_hashes": derivations,
    }
    binding = KnowledgeBinding(**binding_body, binding_hash=content_hash(binding_body))
    return _CurrentValue(record.object_value, binding, record.recorded_at)


def claim_state_hash(state: Any) -> str:
    return content_hash(
        {
            "claim_record_hash": state.record.claim_record_hash,
            "status": state.status,
            "status_event_hash": state.transaction.status_event_hash,
            "supporting_evidence_ids": state.supporting_evidence_ids,
            "contradicting_evidence_ids": state.contradicting_evidence_ids,
            "evidence_conflict_state": state.evidence_conflict_state,
        }
    )


def source_state_hash(state: Any) -> str:
    return content_hash(
        {
            "source_record_hash": state.record.record_hash,
            "status": state.status,
            "status_event_hash": state.status_event_hash,
        }
    )
