"""FactMemory-bound chemistry knowledge snapshots."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from ai_brain.stage2.domains.chemistry.models import (
    AtomicWeightKind,
    AtomicWeightRecord,
    ChemistryKnowledgeSnapshot,
)
from ai_brain.stage2.domains.chemistry.version import (
    CHEMISTRY_ATOMIC_WEIGHT_POLICY,
    CHEMISTRY_CALCULATION_POLICY_VERSION,
    CHEMISTRY_FORMULA_GRAMMAR_VERSION,
    CHEMISTRY_SOURCE_POLICY_VERSION,
)
from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage2.facts.memory import FactMemory
from ai_brain.stage2.facts.values import FactValue


class ChemistryKnowledgeError(ValueError):
    pass


def build_knowledge_snapshot(
    memory: FactMemory,
    domain_manifest_hash: str,
    symbols: tuple[str, ...] | None = None,
) -> ChemistryKnowledgeSnapshot:
    selected = _element_symbols(memory) if symbols is None else symbols
    records = tuple(_atomic_weight_record(memory, symbol) for symbol in selected)
    avogadro = _single(memory, "constant.avogadro", "avogadro_constant")
    claim_hashes = tuple(
        sorted(
            {item for record in records for item in record.claim_hashes}
            | {avogadro.claim_hash}
        )
    )
    evidence_hashes = tuple(
        sorted(
            {item for record in records for item in record.evidence_hashes}
            | set(avogadro.evidence_hashes)
        )
    )
    source_hashes = tuple(
        sorted(
            {item for record in records for item in record.source_hashes}
            | set(avogadro.source_hashes)
        )
    )
    body = {
        "domain_manifest_hash": domain_manifest_hash,
        "fact_memory_snapshot_hash": memory.database.snapshot_hash(),
        "atomic_weight_policy": CHEMISTRY_ATOMIC_WEIGHT_POLICY,
        "source_policy_version": CHEMISTRY_SOURCE_POLICY_VERSION,
        "formula_grammar_version": CHEMISTRY_FORMULA_GRAMMAR_VERSION,
        "calculation_policy_version": CHEMISTRY_CALCULATION_POLICY_VERSION,
        "element_records": records,
        "avogadro_constant": str(avogadro.value.value),
        "avogadro_claim_hash": avogadro.claim_hash,
        "avogadro_evidence_hashes": avogadro.evidence_hashes,
        "avogadro_source_hashes": avogadro.source_hashes,
        "claim_hashes": claim_hashes,
        "evidence_hashes": evidence_hashes,
        "source_hashes": source_hashes,
    }
    return ChemistryKnowledgeSnapshot(**body, snapshot_hash=content_hash(body))


def verify_knowledge_snapshot(
    snapshot: ChemistryKnowledgeSnapshot,
    memory: FactMemory,
    expected_domain_manifest_hash: str,
) -> None:
    body = asdict(snapshot)
    digest = body.pop("snapshot_hash")
    if content_hash(body) != digest:
        raise ChemistryKnowledgeError("chemistry knowledge snapshot hash mismatch")
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
        raise ChemistryKnowledgeError("chemistry claims, evidence, or sources changed")


def snapshot_to_dict(snapshot: ChemistryKnowledgeSnapshot) -> dict[str, Any]:
    return asdict(snapshot)


def snapshot_from_dict(payload: dict[str, Any]) -> ChemistryKnowledgeSnapshot:
    rows = tuple(
        AtomicWeightRecord(
            **{
                **row,
                "standard_kind": AtomicWeightKind(row["standard_kind"]),
                "claim_hashes": tuple(row["claim_hashes"]),
                "evidence_hashes": tuple(row["evidence_hashes"]),
                "source_hashes": tuple(row["source_hashes"]),
            }
        )
        for row in payload["element_records"]
    )
    normalized = {
        **payload,
        "element_records": rows,
        "avogadro_evidence_hashes": tuple(payload["avogadro_evidence_hashes"]),
        "avogadro_source_hashes": tuple(payload["avogadro_source_hashes"]),
        "claim_hashes": tuple(payload["claim_hashes"]),
        "evidence_hashes": tuple(payload["evidence_hashes"]),
        "source_hashes": tuple(payload["source_hashes"]),
    }
    return ChemistryKnowledgeSnapshot(**normalized)


def _element_symbols(memory: FactMemory) -> tuple[str, ...]:
    with memory.database.connect() as connection:
        rows = connection.execute(
            "SELECT payload_json FROM claims WHERE predicate_id = 'element_symbol' ORDER BY subject_entity_id"
        ).fetchall()
    return tuple(json.loads(row[0])["object_value"]["value"] for row in rows)


def _atomic_weight_record(memory: FactMemory, symbol: str) -> AtomicWeightRecord:
    kind_answer = _single(memory, symbol, "atomic_weight_kind")
    conventional = _single(memory, symbol, "conventional_atomic_weight")
    kind = AtomicWeightKind(str(kind_answer.value.value))
    if kind == AtomicWeightKind.SINGLE:
        standard = _single(memory, symbol, "standard_atomic_weight")
        related = (kind_answer, conventional, standard)
        standard_value = str(standard.value.value)
        lower = upper = None
    elif kind == AtomicWeightKind.INTERVAL:
        lower_answer = _single(memory, symbol, "standard_atomic_weight_lower")
        upper_answer = _single(memory, symbol, "standard_atomic_weight_upper")
        related = (kind_answer, conventional, lower_answer, upper_answer)
        standard_value = None
        lower = str(lower_answer.value.value)
        upper = str(upper_answer.value.value)
    else:
        raise ChemistryKnowledgeError(
            f"unsupported atomic-weight kind for {symbol}: {kind}"
        )
    body = {
        "element_entity_id": f"element.{symbol}",
        "symbol": symbol,
        "standard_kind": kind,
        "conventional_value": str(conventional.value.value),
        "standard_value": standard_value,
        "interval_lower": lower,
        "interval_upper": upper,
        "unit": "1",
        "claim_hashes": tuple(sorted(item.claim_hash for item in related)),
        "evidence_hashes": tuple(
            sorted({value for item in related for value in item.evidence_hashes})
        ),
        "source_hashes": tuple(
            sorted({value for item in related for value in item.source_hashes})
        ),
        "policy_version": CHEMISTRY_SOURCE_POLICY_VERSION,
    }
    return AtomicWeightRecord(**body, record_hash=content_hash(body))


@dataclass(frozen=True)
class _KnowledgeClaim:
    claim_hash: str
    value: FactValue
    evidence_hashes: tuple[str, ...]
    source_hashes: tuple[str, ...]


def _single(memory: FactMemory, subject: str, predicate: str) -> _KnowledgeClaim:
    resolution = memory.resolve_entity(subject)
    if len(resolution.entity_ids) != 1:
        raise ChemistryKnowledgeError(f"trusted entity unavailable: {subject}")
    with memory.database.connect() as connection:
        claim_rows = connection.execute(
            """SELECT payload_json FROM claims
               WHERE subject_entity_id = ? AND predicate_id = ?
               ORDER BY recorded_at""",
            (resolution.entity_ids[0], predicate),
        ).fetchall()
        if len(claim_rows) != 1:
            raise ChemistryKnowledgeError(
                f"trusted single fact unavailable: {subject}/{predicate}"
            )
        claim = json.loads(claim_rows[0][0])
        if claim["status"] not in {"SUPPORTED", "CORROBORATED"}:
            raise ChemistryKnowledgeError(
                f"trusted claim is not approved: {subject}/{predicate}"
            )
        evidence_hashes = []
        source_hashes = []
        for evidence_id in claim["supporting_evidence_ids"]:
            evidence = memory.verify_evidence(evidence_id, require_approved=True)
            source_row = connection.execute(
                "SELECT payload_json FROM sources WHERE source_id = ?",
                (evidence.source_id,),
            ).fetchone()
            if source_row is None:
                raise ChemistryKnowledgeError("chemistry evidence source is missing")
            source = json.loads(source_row[0])
            if source["status"] != "ACTIVE":
                raise ChemistryKnowledgeError("chemistry evidence source is inactive")
            evidence_hashes.append(evidence.evidence_hash)
            source_hashes.append(source["record_hash"])
    return _KnowledgeClaim(
        claim_hash=claim["canonical_claim_hash"],
        value=FactValue.from_dict(claim["object_value"]),
        evidence_hashes=tuple(sorted(evidence_hashes)),
        source_hashes=tuple(sorted(source_hashes)),
    )
