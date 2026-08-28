"""Current-state chemistry knowledge snapshots with closed provenance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ai_brain.stage2.domains.chemistry.models import (
    AtomicWeightAnswerBundle,
    AtomicWeightKind,
    AtomicWeightRecordV2,
    AtomicWeightRequest,
    ChemistryKnowledgeSnapshotV3,
    ChemistryRoundingSpec,
    KnowledgeBinding,
)
from ai_brain.stage2.domains.chemistry.provenance import (
    DerivationResolutionError,
    resolve_source_derivation,
    source_state_hash,
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
    SourceKind,
    SourceStatus,
)
from ai_brain.stage2.facts.values import FactValue

ATOMIC_WEIGHTS = "ATOMIC_WEIGHTS"
AVOGADRO = "AVOGADRO"
_REQUIREMENTS = frozenset({ATOMIC_WEIGHTS, AVOGADRO})


class ChemistryKnowledgeError(ValueError):
    pass


@dataclass(frozen=True)
class _CurrentValue:
    value: FactValue
    binding: KnowledgeBinding
    recorded_at: str


def build_knowledge_snapshot(
    memory: FactMemory,
    domain_manifest: dict[str, Any],
    symbols: tuple[str, ...] | None = None,
    *,
    requirements: tuple[str, ...] = (ATOMIC_WEIGHTS, AVOGADRO),
) -> ChemistryKnowledgeSnapshotV3:
    _verify_manifest_hash(domain_manifest)
    selected_requirements = tuple(sorted(set(requirements)))
    if not set(selected_requirements) <= _REQUIREMENTS:
        raise ChemistryKnowledgeError("unknown chemistry knowledge requirement")
    selected = (
        (_element_symbols(memory) if symbols is None else tuple(sorted(set(symbols))))
        if ATOMIC_WEIGHTS in selected_requirements
        else ()
    )
    resolution_cache: dict[str, Any] = {}
    records_and_bindings = tuple(
        _atomic_weight_record(memory, symbol, domain_manifest, resolution_cache)
        for symbol in selected
    )
    records = tuple(item[0] for item in records_and_bindings)
    bindings = tuple(
        value.binding
        for _, record_bindings in records_and_bindings
        for value in record_bindings
    )
    avogadro = (
        _single(
            memory,
            "constant.avogadro",
            "avogadro_constant",
            domain_manifest,
            resolution_cache,
        )
        if AVOGADRO in selected_requirements
        else None
    )
    if avogadro is not None:
        bindings += (avogadro.binding,)
    chain = domain_manifest["source_chain"]
    body = {
        "knowledge_snapshot_version": CHEMISTRY_KNOWLEDGE_SNAPSHOT_VERSION,
        "domain_manifest_hash": domain_manifest["domain_manifest_hash"],
        "fact_memory_snapshot_hash": memory.database.snapshot_hash(),
        "atomic_weight_policy": CHEMISTRY_ATOMIC_WEIGHT_POLICY,
        "source_policy_version": CHEMISTRY_SOURCE_POLICY_VERSION,
        "formula_grammar_version": CHEMISTRY_FORMULA_GRAMMAR_VERSION,
        "calculation_policy_version": CHEMISTRY_CALCULATION_POLICY_VERSION,
        "rounding_policy_hash": content_hash(ChemistryRoundingSpec()),
        "element_records": records,
        "source_chain_version": chain["source_chain_version"],
        "source_chain_hash": chain["source_chain_hash"],
        "requirements": selected_requirements,
        "avogadro_constant": str(avogadro.value.value) if avogadro else None,
        "avogadro_claim_id": avogadro.binding.claim_id if avogadro else None,
        "avogadro_claim_record_hash": (
            avogadro.binding.claim_record_hash if avogadro else None
        ),
        "avogadro_claim_state_hash": (
            avogadro.binding.claim_state_hash if avogadro else None
        ),
        "avogadro_evidence_hashes": (
            avogadro.binding.evidence_hashes if avogadro else ()
        ),
        "avogadro_source_record_hashes": (
            avogadro.binding.source_record_hashes if avogadro else ()
        ),
        "bindings": bindings,
        "claim_ids": _collect(bindings, "claim_id"),
        "claim_record_hashes": _collect(bindings, "claim_record_hash"),
        "claim_state_hashes": _collect(bindings, "claim_state_hash"),
        "evidence_hashes": _flatten(bindings, "evidence_hashes"),
        "source_record_hashes": _flatten(bindings, "source_record_hashes"),
        "source_state_hashes": _flatten(bindings, "source_state_hashes"),
        "derivation_hashes": _flatten(bindings, "derivation_hashes"),
        "derivation_ids": _flatten(bindings, "derivation_ids"),
        "derivation_methods": _flatten(bindings, "derivation_methods"),
        "upstream_source_ids": _flatten(bindings, "upstream_source_ids"),
        "upstream_source_record_hashes": _flatten(
            bindings, "upstream_source_record_hashes"
        ),
        "upstream_source_snapshot_hashes": _flatten(
            bindings, "upstream_source_snapshot_hashes"
        ),
        "upstream_source_state_hashes": _flatten(
            bindings, "upstream_source_state_hashes"
        ),
        "upstream_status_event_hashes": _flatten_optional(
            bindings, "upstream_status_event_hashes"
        ),
        "field_mapping_evidence_hashes": _flatten(
            bindings, "field_mapping_evidence_hashes"
        ),
        "created_at": max(
            (
                item.recorded_at
                for item in (
                    *tuple(
                        value for _, values in records_and_bindings for value in values
                    ),
                    *((avogadro,) if avogadro else ()),
                )
            ),
            default="1970-01-01T00:00:00Z",
        ),
    }
    return ChemistryKnowledgeSnapshotV3(**body, snapshot_hash=content_hash(body))


def verify_knowledge_snapshot(
    snapshot: ChemistryKnowledgeSnapshotV3,
    memory: FactMemory,
    expected_domain_manifest: dict[str, Any],
) -> None:
    body = asdict(snapshot)
    digest = body.pop("snapshot_hash")
    if content_hash(body) != digest:
        raise ChemistryKnowledgeError("chemistry knowledge snapshot hash mismatch")
    if snapshot.knowledge_snapshot_version != CHEMISTRY_KNOWLEDGE_SNAPSHOT_VERSION:
        raise ChemistryKnowledgeError("incompatible chemistry knowledge snapshot")
    if (
        snapshot.domain_manifest_hash
        != expected_domain_manifest["domain_manifest_hash"]
    ):
        raise ChemistryKnowledgeError("stale chemistry domain manifest")
    current = build_knowledge_snapshot(
        memory,
        expected_domain_manifest,
        tuple(record.symbol for record in snapshot.element_records),
        requirements=snapshot.requirements,
    )
    if _dependency_hash(current) != _dependency_hash(snapshot):
        raise ChemistryKnowledgeError("chemistry current provenance state changed")


def atomic_weight_answer(
    memory: FactMemory,
    domain_manifest: dict[str, Any],
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
    snapshot = build_knowledge_snapshot(
        memory, domain_manifest, (symbol,), requirements=(ATOMIC_WEIGHTS,)
    )
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


def validate_fact_provenance(
    memory: FactMemory,
    domain_manifest: dict[str, Any],
    subject: str,
    predicate: str,
    *,
    resolution_cache: dict[str, Any] | None = None,
) -> KnowledgeBinding:
    """Resolve one controlled fact through its exact derived/upstream chain."""
    return _single(
        memory,
        subject,
        predicate,
        domain_manifest,
        resolution_cache,
    ).binding


def snapshot_to_dict(snapshot: ChemistryKnowledgeSnapshotV3) -> dict[str, Any]:
    return asdict(snapshot)


def snapshot_from_dict(payload: dict[str, Any]) -> ChemistryKnowledgeSnapshotV3:
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
    bindings = tuple(_binding_from_dict(row) for row in payload["bindings"])
    tuple_fields = {
        "requirements",
        "avogadro_evidence_hashes",
        "avogadro_source_record_hashes",
        "claim_ids",
        "claim_record_hashes",
        "claim_state_hashes",
        "evidence_hashes",
        "source_record_hashes",
        "source_state_hashes",
        "derivation_hashes",
        "derivation_ids",
        "derivation_methods",
        "upstream_source_ids",
        "upstream_source_record_hashes",
        "upstream_source_snapshot_hashes",
        "upstream_source_state_hashes",
        "upstream_status_event_hashes",
        "field_mapping_evidence_hashes",
    }
    normalized = {
        key: tuple(value) if key in tuple_fields else value
        for key, value in payload.items()
    }
    normalized["element_records"] = rows
    normalized["bindings"] = bindings
    return ChemistryKnowledgeSnapshotV3(**normalized)


def _element_symbols(memory: FactMemory) -> tuple[str, ...]:
    return tuple(
        sorted(
            entity.external_identifiers["symbol"]
            for entity in memory.list_entities(entity_type="chemical_element")
        )
    )


def _atomic_weight_record(
    memory: FactMemory,
    symbol: str,
    manifest: dict[str, Any],
    resolution_cache: dict[str, Any],
) -> tuple[AtomicWeightRecordV2, tuple[_CurrentValue, ...]]:
    resolution = resolve_chemistry_element(memory, symbol, "en")
    if len(resolution.entity_ids) != 1:
        raise ChemistryKnowledgeError(f"unknown exact element symbol: {symbol}")
    entity_id = resolution.entity_ids[0]
    number = _single(memory, entity_id, "atomic_number", manifest, resolution_cache)
    symbol_value = _single(
        memory, entity_id, "element_symbol", manifest, resolution_cache
    )
    kind_value = _single(
        memory, entity_id, "atomic_weight_kind", manifest, resolution_cache
    )
    abridged = _single(
        memory, entity_id, "conventional_atomic_weight", manifest, resolution_cache
    )
    abridged_uncertainty = _single(
        memory,
        entity_id,
        "conventional_atomic_weight_uncertainty",
        manifest,
        resolution_cache,
    )
    standard_notation = _single(
        memory,
        entity_id,
        "atomic_weight_standard_notation",
        manifest,
        resolution_cache,
    )
    abridged_notation = _single(
        memory,
        entity_id,
        "atomic_weight_abridged_notation",
        manifest,
        resolution_cache,
    )
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
        nominal = _single(
            memory, entity_id, "standard_atomic_weight", manifest, resolution_cache
        )
        uncertainty = _single(
            memory,
            entity_id,
            "standard_atomic_weight_uncertainty",
            manifest,
            resolution_cache,
        )
        related = (*common, nominal, uncertainty)
        standard_nominal = str(nominal.value.value)
        standard_uncertainty = str(uncertainty.value.value)
        lower = upper = None
    elif kind == AtomicWeightKind.INTERVAL:
        lower_value = _single(
            memory,
            entity_id,
            "standard_atomic_weight_lower",
            manifest,
            resolution_cache,
        )
        upper_value = _single(
            memory,
            entity_id,
            "standard_atomic_weight_upper",
            manifest,
            resolution_cache,
        )
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
        "evidence_hashes": _flatten(bindings, "evidence_hashes"),
        "source_record_hashes": _flatten(bindings, "source_record_hashes"),
        "derivation_hashes": _flatten(bindings, "derivation_hashes"),
        "policy_version": CHEMISTRY_SOURCE_POLICY_VERSION,
    }
    return AtomicWeightRecordV2(**body, record_hash=content_hash(body)), related


def _single(
    memory: FactMemory,
    subject: str,
    predicate: str,
    manifest: dict[str, Any],
    resolution_cache: dict[str, Any] | None = None,
) -> _CurrentValue:
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
    source_states = tuple(
        memory.get_source_state(value.source_id) for value in evidence
    )
    if any(value.status != SourceStatus.ACTIVE for value in source_states):
        raise ChemistryKnowledgeError(
            "inactive derived source blocks chemistry knowledge"
        )
    if any(
        value.record.source_kind != SourceKind.DERIVED_EXTRACT
        for value in source_states
    ):
        raise ChemistryKnowledgeError("production claim must use a derived source")
    try:
        cache = resolution_cache if resolution_cache is not None else {}
        for value in source_states:
            if value.record.source_id not in cache:
                cache[value.record.source_id] = resolve_source_derivation(
                    value.record,
                    manifest["source_chain"],
                    memory,
                    source_record_bindings=tuple(manifest["source_record_bindings"]),
                )
        resolutions = tuple(cache[value.record.source_id] for value in source_states)
    except DerivationResolutionError as error:
        raise ChemistryKnowledgeError(f"{error.code}: {error}") from error
    field_hashes = []
    for evidence_record, resolution in zip(evidence, resolutions, strict=True):
        pointer = str(evidence_record.location.get("pointer", ""))
        selected_fields = tuple(
            item.evidence_hash
            for item in resolution.derivation.field_level_mappings
            if item.output_field_name == pointer
            or item.output_field_name.startswith(pointer.rstrip("/") + "/")
        )
        if not selected_fields:
            raise ChemistryKnowledgeError(
                "claim evidence has no field mapping evidence"
            )
        field_hashes.extend(selected_fields)
    upstream = _upstream_rows(resolutions)
    binding_body = {
        "claim_id": record.claim_id,
        "claim_record_hash": record.claim_record_hash,
        "claim_state_hash": claim_state_hash(state),
        "claim_status": state.status.value,
        "claim_status_event_hash": state.transaction.status_event_hash,
        "evidence_ids": tuple(value.evidence_id for value in evidence),
        "evidence_hashes": tuple(value.evidence_hash for value in evidence),
        "evidence_relations": tuple(value.relation.value for value in evidence),
        "source_ids": tuple(value.record.source_id for value in source_states),
        "source_record_hashes": tuple(
            value.record.record_hash for value in source_states
        ),
        "source_state_hashes": tuple(
            source_state_hash(value) for value in source_states
        ),
        "source_status_event_hashes": tuple(
            value.status_event_hash for value in source_states
        ),
        "derived_exact_file_hashes": tuple(
            value.derivation.derived_file_byte_sha256 for value in resolutions
        ),
        "derived_canonical_content_hashes": tuple(
            value.derivation.derived_canonical_content_hash for value in resolutions
        ),
        "derivation_ids": tuple(
            value.derivation.derivation_id for value in resolutions
        ),
        "derivation_hashes": tuple(
            value.derivation.derivation_hash for value in resolutions
        ),
        "derivation_methods": tuple(
            value.derivation.derivation_method.value for value in resolutions
        ),
        "upstream_source_ids": tuple(row[0] for row in upstream),
        "upstream_source_record_hashes": tuple(row[1] for row in upstream),
        "upstream_source_snapshot_hashes": tuple(row[2] for row in upstream),
        "upstream_source_state_hashes": tuple(row[3] for row in upstream),
        "upstream_status_event_hashes": tuple(row[4] for row in upstream),
        "field_mapping_evidence_hashes": tuple(sorted(set(field_hashes))),
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


def _verify_manifest_hash(manifest: dict[str, Any]) -> None:
    body = dict(manifest)
    digest = body.pop("domain_manifest_hash", None)
    if content_hash(body) != digest:
        raise ChemistryKnowledgeError("chemistry domain manifest hash mismatch")
    if manifest.get("knowledge_snapshot_version") != (
        CHEMISTRY_KNOWLEDGE_SNAPSHOT_VERSION
    ):
        raise ChemistryKnowledgeError("incompatible chemistry domain manifest")


def _dependency_hash(snapshot: ChemistryKnowledgeSnapshotV3) -> str:
    body = asdict(snapshot)
    body.pop("snapshot_hash")
    body.pop("fact_memory_snapshot_hash")
    return content_hash(body)


def _binding_from_dict(row: dict[str, Any]) -> KnowledgeBinding:
    tuple_fields = {
        "evidence_ids",
        "evidence_hashes",
        "evidence_relations",
        "source_ids",
        "source_record_hashes",
        "source_state_hashes",
        "source_status_event_hashes",
        "derived_exact_file_hashes",
        "derived_canonical_content_hashes",
        "derivation_ids",
        "derivation_hashes",
        "derivation_methods",
        "upstream_source_ids",
        "upstream_source_record_hashes",
        "upstream_source_snapshot_hashes",
        "upstream_source_state_hashes",
        "upstream_status_event_hashes",
        "field_mapping_evidence_hashes",
    }
    return KnowledgeBinding(
        **{
            key: tuple(value) if key in tuple_fields else value
            for key, value in row.items()
        }
    )


def _upstream_rows(resolutions: tuple[Any, ...]) -> tuple[tuple[Any, ...], ...]:
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


def _collect(bindings: tuple[KnowledgeBinding, ...], field: str) -> tuple[str, ...]:
    return tuple(sorted({str(getattr(item, field)) for item in bindings}))


def _flatten(bindings: tuple[KnowledgeBinding, ...], field: str) -> tuple[str, ...]:
    return tuple(
        sorted({str(value) for item in bindings for value in getattr(item, field)})
    )


def _flatten_optional(
    bindings: tuple[KnowledgeBinding, ...], field: str
) -> tuple[str | None, ...]:
    values = {value for item in bindings for value in getattr(item, field)}
    return tuple(sorted(values, key=lambda value: "" if value is None else value))
