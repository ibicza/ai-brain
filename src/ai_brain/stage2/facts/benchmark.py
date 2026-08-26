"""Deterministic synthetic corpus and SQLite scale benchmarks."""

from __future__ import annotations

import json
import random
import shutil
import statistics
import time
import tracemalloc
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ai_brain.stage2.facts.canonical import (
    bytes_hash,
    canonical_json,
    content_hash,
    normalize_label,
    temporal_key,
)
from ai_brain.stage2.facts.models import (
    ActorIdentityType,
    ApprovalDecision,
    ApprovalStatus,
    Cardinality,
    ClaimRecord,
    ClaimStatus,
    ConflictGroup,
    ConflictResolutionEvent,
    ConflictResolutionKind,
    ConflictResolutionStatus,
    EntityRecord,
    EntityStatus,
    EvidenceLocationKind,
    EvidenceRecord,
    EvidenceRelation,
    ExtractionMethod,
    FactApprovalEnvelope,
    FactProposal,
    PredicateDefinition,
    ProposalSource,
    ProposalStatus,
    SourceKind,
    SourceRecord,
    SourceStatus,
    TemporalMode,
)
from ai_brain.stage2.facts.persistence import FactDatabase
from ai_brain.stage2.facts.values import FactValue, FactValueKind
from ai_brain.stage2.facts.version import (
    FACT_APPROVAL_POLICY_VERSION,
    FACT_MEMORY_SCHEMA_VERSION,
)

ENTITY_COUNT = 1_000
PREDICATE_COUNT = 25
SOURCE_COUNT = 200


def generate_synthetic_corpus(
    root: Path,
    *,
    claim_count: int,
    seed: int = 26_000,
    entity_count: int = ENTITY_COUNT,
    predicate_count: int = PREDICATE_COUNT,
    source_count: int = SOURCE_COUNT,
) -> dict[str, Any]:
    if claim_count < 1:
        raise ValueError("claim_count must be positive")
    if root.exists() and any(root.iterdir()):
        raise ValueError("synthetic corpus target must be empty")
    database = FactDatabase.initialize(root)
    started = time.perf_counter()
    tracemalloc.start()
    specs = _claim_specs(
        claim_count,
        entity_count=entity_count,
        predicate_count=predicate_count,
        source_count=source_count,
    )
    documents: list[dict[str, Any]] = [{} for _ in range(source_count)]
    for spec in specs:
        documents[spec["source_index"]][str(spec["index"])] = spec["value"].to_dict()
    duplicate_count = claim_count // 20
    for index in range(duplicate_count):
        source_index = (specs[index]["source_index"] + 1) % source_count
        documents[source_index][f"duplicate-{index}"] = specs[index]["value"].to_dict()
    created_at = "2026-01-01T00:00:00Z"
    source_records = _source_records(database, documents, created_at)
    conflicts: list[tuple[str, str, dict[str, Any]]] = []
    with database.write() as connection:
        _insert_entities(connection, entity_count, created_at)
        predicates = _insert_predicates(connection, predicate_count)
        _insert_sources(connection, source_records)
        for spec in specs:
            predicate = predicates[spec["predicate_index"]]
            _insert_claim_artifacts(
                connection,
                spec,
                predicate,
                source_records[spec["source_index"]],
                created_at,
            )
            if spec["conflicts_with"] is not None:
                conflicts.append(
                    (
                        spec["claim_id"],
                        f"claim.synthetic.{spec['conflicts_with']:06d}",
                        spec,
                    )
                )
        for index in range(duplicate_count):
            _insert_duplicate_support(
                connection,
                specs[index],
                source_records[(specs[index]["source_index"] + 1) % source_count],
                created_at,
            )
        _insert_conflicts(connection, conflicts, created_at)
        _insert_retractions(connection, specs, created_at)
        _insert_source_retractions(connection, source_records, created_at)
        for start in range(0, claim_count, 1_000):
            end = min(start + 1_000, claim_count)
            database.append_audit(
                connection,
                "SYNTHETIC_CLAIM_BATCH_COMMITTED",
                {
                    "first_claim_id": specs[start]["claim_id"],
                    "last_claim_id": specs[end - 1]["claim_id"],
                    "count": end - start,
                    "batch_hash": content_hash(
                        [item["canonical_claim_hash"] for item in specs[start:end]]
                    ),
                },
                f"synthetic-batch-{start // 1_000:06d}",
            )
        database.append_audit(
            connection,
            "SYNTHETIC_CORPUS_COMMITTED",
            {
                "claim_count": claim_count,
                "seed": seed,
                "ground_truth_hash": content_hash(
                    [item["canonical_claim_hash"] for item in specs]
                ),
            },
            "m26-synthetic-corpus",
        )
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    manifest = {
        "schema_version": FACT_MEMORY_SCHEMA_VERSION,
        "seed": seed,
        "entity_count": entity_count,
        "predicate_count": predicate_count,
        "source_count": source_count,
        "accepted_claim_count": claim_count,
        "temporal_update_count": sum(item["temporal_update"] for item in specs),
        "intentional_conflict_count": len(conflicts),
        "claim_retraction_count": claim_count // 20,
        "duplicate_support_count": duplicate_count,
        "source_retraction_count": source_count // 20,
        "source_lineage_duplicate_count": source_count // 20,
        "value_kind_counts": _counts(item["value"].kind for item in specs),
        "temporal_mode_counts": _counts(
            _predicate_mode(item["predicate_index"]) for item in specs
        ),
        "memory_snapshot_hash": database.snapshot_hash(),
        "ground_truth_hash": content_hash(
            [item["canonical_claim_hash"] for item in specs]
        ),
        "generation_seconds": elapsed,
        "import_claims_per_second": claim_count / elapsed,
        "python_peak_memory_bytes": peak,
    }
    (root / "synthetic_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return manifest


def run_scale_benchmark(
    output_dir: Path,
    *,
    sizes: tuple[int, ...] = (1_000, 10_000, 100_000),
    seed: int = 26_000,
    samples: int = 500,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for size in sizes:
        root = output_dir / f"claims_{size}"
        manifest = generate_synthetic_corpus(root, claim_count=size, seed=seed + size)
        database = FactDatabase(root)
        metrics = _measure_database(database, size=size, samples=samples, seed=seed)
        metrics["generation"] = manifest
        results.append(metrics)
    report = {
        "status": "PASS",
        "seed": seed,
        "sizes": list(sizes),
        "results": results,
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    (output_dir / "m26_scale_benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return report


def _measure_database(
    database: FactDatabase, *, size: int, samples: int, seed: int
) -> dict[str, Any]:
    rng = random.Random(seed + size)
    with database.connect() as connection:
        connection.execute("PRAGMA optimize")
        query_specs = {
            "exact_subject_predicate": (
                "SELECT claim_id FROM claims WHERE subject_entity_id = ? AND predicate_id = ?",
                lambda: (
                    f"entity.synthetic.{rng.randrange(min(size, ENTITY_COUNT)):04d}",
                    f"predicate.synthetic.{rng.randrange(PREDICATE_COUNT):02d}",
                ),
            ),
            "valid_at": (
                """SELECT claim_id FROM claims WHERE subject_entity_id = ?
                   AND predicate_id = ? AND valid_from_key <= ? AND ? < valid_to_key""",
                lambda: (
                    f"entity.synthetic.{rng.randrange(min(size, ENTITY_COUNT)):04d}",
                    f"predicate.synthetic.{rng.randrange(PREDICATE_COUNT):02d}",
                    "2025-06-01T00:00:00Z",
                    "2025-06-01T00:00:00Z",
                ),
            ),
            "bitemporal": (
                """SELECT c.claim_id FROM claims c JOIN claim_status_events s
                   ON s.claim_id = c.claim_id WHERE c.subject_entity_id = ?
                   AND c.predicate_id = ? AND c.recorded_at <= ?
                   AND c.valid_from_key <= ? AND ? < c.valid_to_key""",
                lambda: (
                    f"entity.synthetic.{rng.randrange(min(size, ENTITY_COUNT)):04d}",
                    f"predicate.synthetic.{rng.randrange(PREDICATE_COUNT):02d}",
                    "2026-12-31T00:00:00Z",
                    "2025-06-01T00:00:00Z",
                    "2025-06-01T00:00:00Z",
                ),
            ),
            "conflict": (
                """SELECT g.conflict_group_id FROM conflict_groups g
                   WHERE g.subject_entity_id = ? AND g.predicate_id = ?
                   AND g.resolution_status = 'UNRESOLVED'""",
                lambda: (
                    f"entity.synthetic.{rng.randrange(min(size, ENTITY_COUNT)):04d}",
                    f"predicate.synthetic.{rng.randrange(PREDICATE_COUNT):02d}",
                ),
            ),
            "alias": (
                "SELECT entity_id FROM entity_aliases WHERE normalized_alias = ?",
                lambda: (
                    normalize_label(
                        f"Synthetic Entity {rng.randrange(min(size, ENTITY_COUNT)):04d}"
                    ),
                ),
            ),
            "history": (
                "SELECT * FROM claim_status_events WHERE claim_id = ? ORDER BY recorded_at",
                lambda: (f"claim.synthetic.{rng.randrange(size):06d}",),
            ),
        }
        latencies = {
            name: _latencies(connection, sql, parameters, samples)
            for name, (sql, parameters) in query_specs.items()
        }
        plans = {
            name: [
                row[3]
                for row in connection.execute(f"EXPLAIN QUERY PLAN {sql}", parameters())
            ]
            for name, (sql, parameters) in query_specs.items()
        }
        full_scan_queries = [
            name
            for name, rows in plans.items()
            if any("SCAN" in row and "USING INDEX" not in row for row in rows)
        ]
    integrity_started = time.perf_counter()
    integrity = database.integrity_check()
    integrity_seconds = time.perf_counter() - integrity_started
    backup_dir = database.root.parent / f"backup_{size}"
    backup_started = time.perf_counter()
    database.backup(backup_dir)
    backup_seconds = time.perf_counter() - backup_started
    restore_dir = database.root.parent / f"restore_{size}"
    restore_started = time.perf_counter()
    restored = FactDatabase.restore(backup_dir, restore_dir)
    restore_seconds = time.perf_counter() - restore_started
    export_dir = database.root.parent / f"export_{size}"
    export_started = time.perf_counter()
    database.export(export_dir)
    export_seconds = time.perf_counter() - export_started
    database_size = database.db_path.stat().st_size
    blob_size = sum(item["size"] for item in database.blobs.manifest())
    restored.integrity_check()
    shutil.rmtree(backup_dir)
    shutil.rmtree(restore_dir)
    shutil.rmtree(export_dir)
    return {
        "claim_count": size,
        "database_size_bytes": database_size,
        "source_blob_size_bytes": blob_size,
        "latency_ms": {name: _percentiles(rows) for name, rows in latencies.items()},
        "query_plans": plans,
        "full_scan_queries": full_scan_queries,
        "backup_seconds": backup_seconds,
        "restore_seconds": restore_seconds,
        "export_seconds": export_seconds,
        "integrity_check_seconds": integrity_seconds,
        "integrity": integrity,
    }


def _claim_specs(
    count: int, *, entity_count: int, predicate_count: int, source_count: int
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for index in range(count):
        entity_index = index % entity_count
        predicate_index = index % predicate_count
        conflict_with = None
        temporal_update = False
        if (
            index % 20 == 1
            and _predicate_cardinality((index - 1) % predicate_count)
            == Cardinality.SINGLE
        ):
            previous = specs[index - 1]
            entity_index = previous["entity_index"]
            predicate_index = previous["predicate_index"]
            conflict_with = index - 1
        elif index >= 3 and index % 10 == 3:
            previous = specs[index - 3]
            entity_index = previous["entity_index"]
            predicate_index = previous["predicate_index"]
            temporal_update = True
        value = _value(
            predicate_index,
            index + (1 if conflict_with is not None else 0),
            entity_count,
        )
        if conflict_with is not None and value == specs[conflict_with]["value"]:
            value = _different_value(value, index, entity_count)
        valid_from, valid_to = _valid_interval(predicate_index, index, temporal_update)
        if conflict_with is not None:
            valid_from = specs[conflict_with]["valid_from"]
            valid_to = specs[conflict_with]["valid_to"]
        identity = {
            "subject_entity_id": f"entity.synthetic.{entity_index:04d}",
            "predicate_id": f"predicate.synthetic.{predicate_index:02d}",
            "object_value": value,
            "qualifiers": {},
            "valid_from": valid_from,
            "valid_to": valid_to,
        }
        specs.append(
            {
                "index": index,
                "claim_id": f"claim.synthetic.{index:06d}",
                "proposal_id": f"proposal.synthetic.{index:06d}",
                "evidence_id": f"evidence.synthetic.{index:06d}",
                "entity_index": entity_index,
                "predicate_index": predicate_index,
                "source_index": index % source_count,
                "value": value,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "canonical_claim_hash": content_hash(identity),
                "conflicts_with": conflict_with,
                "temporal_update": temporal_update,
            }
        )
    return specs


def _source_records(
    database: FactDatabase, documents: list[dict[str, Any]], created_at: str
) -> list[SourceRecord]:
    result = []
    for index, document in enumerate(documents):
        raw = canonical_json(document).encode("utf-8")
        snapshot_hash = database.blobs.put(raw)
        family_index = index - 1 if index % 20 == 1 else index
        payload = {
            "source_id": f"source.synthetic.{index:03d}",
            "source_kind": SourceKind.LOCAL_DOCUMENT,
            "title": f"Synthetic evidence document {index:03d}",
            "author": "M-26 deterministic generator",
            "publisher": "ai-brain",
            "locator": f"synthetic:source:{index:03d}",
            "published_at": "2025-12-31",
            "retrieved_at": created_at,
            "language": "en" if index % 2 else "ru",
            "source_family": f"synthetic-lineage-{family_index:03d}",
            "trust_tier": "SYNTHETIC_T1",
            "content_hash": bytes_hash(raw),
            "snapshot_hash": snapshot_hash,
            "status": SourceStatus.ACTIVE,
            "license_metadata": {"usage": "synthetic-test-only"},
            "original_filename": f"source-{index:03d}.json",
            "media_type": "application/json",
            "created_at": created_at,
        }
        result.append(SourceRecord(**payload, record_hash=content_hash(payload)))
    return result


def _insert_entities(connection, count: int, created_at: str) -> None:
    for index in range(count):
        payload = {
            "entity_id": f"entity.synthetic.{index:04d}",
            "entity_type": "SYNTHETIC",
            "canonical_label_ru": f"Синтетическая сущность {index:04d}",
            "canonical_label_en": f"Synthetic Entity {index:04d}",
            "aliases_ru": (f"Сущность {index:04d}",),
            "aliases_en": (f"Entity {index:04d}",),
            "external_identifiers": {"synthetic": str(index)},
            "status": EntityStatus.ACTIVE,
            "created_at": created_at,
            "updated_at": created_at,
            "provenance": ({"generator": "m26", "seed": 26000},),
            "schema_version": FACT_MEMORY_SCHEMA_VERSION,
        }
        record = EntityRecord(**payload, content_hash=content_hash(payload))
        connection.execute(
            "INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                record.entity_id,
                record.entity_type,
                record.status,
                record.created_at,
                record.updated_at,
                record.content_hash,
                canonical_json(record),
            ),
        )
        for language, labels in (
            ("ru", (record.canonical_label_ru, *record.aliases_ru)),
            ("en", (record.canonical_label_en, *record.aliases_en)),
        ):
            connection.executemany(
                "INSERT INTO entity_aliases VALUES (?, ?, ?, ?)",
                (
                    (normalize_label(label), language, record.entity_id, label)
                    for label in labels
                ),
            )


def _insert_predicates(connection, count: int) -> list[PredicateDefinition]:
    result = []
    for index in range(count):
        payload = {
            "predicate_id": f"predicate.synthetic.{index:02d}",
            "canonical_name_ru": f"синтетический предикат {index:02d}",
            "canonical_name_en": f"synthetic predicate {index:02d}",
            "subject_entity_type": "SYNTHETIC",
            "object_kind": list(FactValueKind)[index % len(FactValueKind)],
            "cardinality": _predicate_cardinality(index),
            "temporal_mode": _predicate_mode(index),
            "allowed_qualifiers": {},
            "unit_dimension": "length" if index % len(FactValueKind) == 7 else None,
            "conflict_key_fields": (),
            "overlapping_intervals_permitted": False,
            "schema_version": 1,
            "active": True,
            "deprecated": False,
        }
        record = PredicateDefinition(**payload, content_hash=content_hash(payload))
        result.append(record)
        connection.execute(
            "INSERT INTO predicate_definitions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.predicate_id,
                record.subject_entity_type,
                record.object_kind,
                record.cardinality,
                record.temporal_mode,
                1,
                0,
                record.content_hash,
                canonical_json(record),
            ),
        )
    return result


def _insert_sources(connection, records: list[SourceRecord]) -> None:
    connection.executemany(
        "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            (
                record.source_id,
                record.source_family,
                record.source_kind,
                record.trust_tier,
                record.snapshot_hash,
                record.status,
                record.created_at,
                record.record_hash,
                canonical_json(record),
            )
            for record in records
        ),
    )


def _insert_claim_artifacts(
    connection,
    spec: dict[str, Any],
    predicate: PredicateDefinition,
    source: SourceRecord,
    created_at: str,
) -> None:
    evidence = _evidence(spec, source, created_at)
    connection.execute(
        "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            evidence.evidence_id,
            evidence.source_id,
            evidence.relation,
            evidence.snapshot_hash,
            evidence.approval_status,
            evidence.created_at,
            evidence.evidence_hash,
            canonical_json(evidence),
        ),
    )
    base = {
        "proposal_id": spec["proposal_id"],
        "source": ProposalSource.STRUCTURED_JSON,
        "subject_entity_id": f"entity.synthetic.{spec['entity_index']:04d}",
        "predicate_id": predicate.predicate_id,
        "object_value": spec["value"],
        "qualifiers": {},
        "valid_from": spec["valid_from"],
        "valid_to": spec["valid_to"],
        "source_ids": (source.source_id,),
        "evidence_ids": (evidence.evidence_id,),
        "reviewer_identity": None,
        "reviewer_identity_type": None,
        "created_at": created_at,
        "updated_at": created_at,
        "schema_version": FACT_MEMORY_SCHEMA_VERSION,
    }
    proposals = []
    for revision, status in enumerate(
        (
            ProposalStatus.RECEIVED,
            ProposalStatus.PARSED,
            ProposalStatus.EVIDENCE_ATTACHED,
            ProposalStatus.VALIDATED,
            ProposalStatus.REVIEWED,
        ),
        1,
    ):
        payload = {"revision": revision, "status": status, **base}
        if status == ProposalStatus.REVIEWED:
            payload.update(
                reviewer_identity="m26-synthetic-generator",
                reviewer_identity_type=ActorIdentityType.TRUSTED_PROCESS,
            )
        proposals.append(FactProposal(**payload, proposal_hash=content_hash(payload)))
    reviewed = proposals[-1]
    approval_payload = {
        "approval_id": f"approval.synthetic.{spec['index']:06d}",
        "proposal_id": spec["proposal_id"],
        "proposal_hash": reviewed.proposal_hash,
        "entity_hash": connection.execute(
            "SELECT content_hash FROM entities WHERE entity_id = ?",
            (base["subject_entity_id"],),
        ).fetchone()[0],
        "predicate_definition_hash": predicate.content_hash,
        "typed_value_hash": content_hash(spec["value"]),
        "qualifier_hash": content_hash({}),
        "valid_from": spec["valid_from"],
        "valid_to": spec["valid_to"],
        "source_hashes": (source.record_hash,),
        "evidence_hashes": (evidence.evidence_hash,),
        "reviewer_identity": "m26-synthetic-generator",
        "reviewer_identity_type": ActorIdentityType.TRUSTED_PROCESS,
        "supporting_evidence_hashes": (evidence.evidence_hash,),
        "independent_non_model_support": True,
        "decision": ApprovalDecision.APPROVE,
        "contested_approval": False,
        "policy_version": FACT_APPROVAL_POLICY_VERSION,
        "fact_memory_schema_version": FACT_MEMORY_SCHEMA_VERSION,
        "created_at": created_at,
    }
    approval = FactApprovalEnvelope(
        **approval_payload, approval_hash=content_hash(approval_payload)
    )
    approved_payload = {
        "revision": 6,
        "status": ProposalStatus.APPROVED,
        **base,
        "reviewer_identity": "m26-synthetic-generator",
        "reviewer_identity_type": ActorIdentityType.TRUSTED_PROCESS,
    }
    approved = FactProposal(
        **approved_payload, proposal_hash=content_hash(approved_payload)
    )
    committed_payload = {
        "revision": 7,
        "status": ProposalStatus.COMMITTED,
        **base,
        "reviewer_identity": "m26-synthetic-generator",
        "reviewer_identity_type": ActorIdentityType.TRUSTED_PROCESS,
    }
    committed = FactProposal(
        **committed_payload, proposal_hash=content_hash(committed_payload)
    )
    connection.executemany(
        "INSERT INTO proposals VALUES (?, ?, ?, ?, ?, ?)",
        (
            (
                row.proposal_id,
                row.revision,
                row.status,
                row.proposal_hash,
                row.created_at,
                canonical_json(row),
            )
            for row in (*proposals, approved, committed)
        ),
    )
    connection.execute(
        "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            approval.approval_id,
            approval.proposal_id,
            approval.proposal_hash,
            approval.decision,
            approval.created_at,
            approval.approval_hash,
            canonical_json(approval),
        ),
    )
    claim_payload = {
        "claim_id": spec["claim_id"],
        "subject_entity_id": base["subject_entity_id"],
        "predicate_id": predicate.predicate_id,
        "object_value": spec["value"],
        "qualifiers": {},
        "valid_from": spec["valid_from"],
        "valid_to": spec["valid_to"],
        "recorded_at": created_at,
        "status": ClaimStatus.SUPPORTED,
        "evidence_ids": (evidence.evidence_id,),
        "supporting_evidence_ids": (evidence.evidence_id,),
        "contradicting_evidence_ids": (),
        "source_family_support_set": (source.source_family,),
        "source_family_contradiction_set": (),
        "supersedes_claim_ids": (),
        "retraction_reason": None,
        "proposal_hash": approved.proposal_hash,
        "approval_hash": approval.approval_hash,
        "canonical_claim_hash": spec["canonical_claim_hash"],
        "schema_version": FACT_MEMORY_SCHEMA_VERSION,
    }
    claim = ClaimRecord(**claim_payload, claim_record_hash=content_hash(claim_payload))
    connection.execute(
        "INSERT INTO claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            claim.claim_id,
            claim.subject_entity_id,
            claim.predicate_id,
            content_hash(claim.object_value),
            content_hash(claim.qualifiers),
            temporal_key(claim.valid_from),
            temporal_key(claim.valid_to, upper=True),
            claim.recorded_at,
            claim.status,
            claim.canonical_claim_hash,
            claim.claim_record_hash,
            claim.proposal_hash,
            claim.approval_hash,
            canonical_json(claim),
        ),
    )
    transaction = {
        "claim_id": claim.claim_id,
        "evidence_id": evidence.evidence_id,
        "relation": EvidenceRelation.SUPPORTS,
        "attached_at": created_at,
    }
    connection.execute(
        "INSERT INTO claim_evidence VALUES (?, ?, ?, ?, ?)",
        (*transaction.values(), content_hash(transaction)),
    )
    _insert_status_event(connection, claim.claim_id, ClaimStatus.SUPPORTED, created_at)


def _evidence(
    spec: dict[str, Any], source: SourceRecord, created_at: str
) -> EvidenceRecord:
    payload = {
        "evidence_id": spec["evidence_id"],
        "source_id": source.source_id,
        "relation": EvidenceRelation.SUPPORTS,
        "snapshot_hash": source.snapshot_hash,
        "location_kind": EvidenceLocationKind.JSON_POINTER,
        "location": {"pointer": f"/{spec['index']}"},
        "excerpt_hash": bytes_hash(
            canonical_json(spec["value"].to_dict()).encode("utf-8")
        ),
        "extraction_method": ExtractionMethod.DETERMINISTIC,
        "extraction_confidence": "1",
        "reviewer": "m26-synthetic-generator",
        "reviewer_identity_type": ActorIdentityType.TRUSTED_PROCESS,
        "approval_status": ApprovalStatus.APPROVED,
        "created_at": created_at,
    }
    return EvidenceRecord(**payload, evidence_hash=content_hash(payload))


def _insert_duplicate_support(
    connection, spec: dict[str, Any], source: SourceRecord, created_at: str
) -> None:
    index = spec["index"]
    payload = {
        "evidence_id": f"evidence.synthetic.duplicate.{index:06d}",
        "source_id": source.source_id,
        "relation": EvidenceRelation.SUPPORTS,
        "snapshot_hash": source.snapshot_hash,
        "location_kind": EvidenceLocationKind.JSON_POINTER,
        "location": {"pointer": f"/duplicate-{index}"},
        "excerpt_hash": bytes_hash(
            canonical_json(spec["value"].to_dict()).encode("utf-8")
        ),
        "extraction_method": ExtractionMethod.DETERMINISTIC,
        "extraction_confidence": "1",
        "reviewer": "m26-synthetic-generator",
        "reviewer_identity_type": ActorIdentityType.TRUSTED_PROCESS,
        "approval_status": ApprovalStatus.APPROVED,
        "created_at": created_at,
    }
    evidence = EvidenceRecord(**payload, evidence_hash=content_hash(payload))
    connection.execute(
        "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            evidence.evidence_id,
            evidence.source_id,
            evidence.relation,
            evidence.snapshot_hash,
            evidence.approval_status,
            evidence.created_at,
            evidence.evidence_hash,
            canonical_json(evidence),
        ),
    )
    transaction = {
        "claim_id": spec["claim_id"],
        "evidence_id": evidence.evidence_id,
        "relation": evidence.relation,
        "attached_at": created_at,
    }
    connection.execute(
        "INSERT INTO claim_evidence VALUES (?, ?, ?, ?, ?)",
        (*transaction.values(), content_hash(transaction)),
    )


def _insert_conflicts(
    connection,
    conflicts: list[tuple[str, str, dict[str, Any]]],
    created_at: str,
) -> None:
    for index, (left, right, spec) in enumerate(conflicts):
        payload = {
            "conflict_group_id": f"conflict.synthetic.{index:06d}",
            "claim_ids": tuple(sorted((left, right))),
            "subject_entity_id": f"entity.synthetic.{spec['entity_index']:04d}",
            "predicate_id": f"predicate.synthetic.{spec['predicate_index']:02d}",
            "overlapping_interval": (spec["valid_from"], spec["valid_to"]),
            "conflict_reason": "SYNTHETIC_SINGLE_OVERLAP",
            "resolution_status": ConflictResolutionStatus.UNRESOLVED,
            "created_at": created_at,
            "resolved_at": None,
            "resolution_evidence_ids": (),
        }
        group = ConflictGroup(**payload, group_hash=content_hash(payload))
        connection.execute(
            "INSERT INTO conflict_groups VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                group.conflict_group_id,
                group.subject_entity_id,
                group.predicate_id,
                group.resolution_status,
                group.created_at,
                group.group_hash,
                canonical_json(group),
            ),
        )
        connection.executemany(
            "INSERT INTO conflict_group_claims VALUES (?, ?)",
            ((group.conflict_group_id, claim_id) for claim_id in group.claim_ids),
        )
        event_payload = {
            "event_id": f"resolution.{group.conflict_group_id}.initial",
            "conflict_group_id": group.conflict_group_id,
            "prior_status": ConflictResolutionStatus.UNRESOLVED,
            "new_status": ConflictResolutionStatus.UNRESOLVED,
            "resolution_kind": ConflictResolutionKind.INITIAL_STATE,
            "selected_claim_ids": (),
            "remaining_claim_ids": group.claim_ids,
            "evidence_ids": (),
            "evidence_links": (),
            "actor_identity": "m26-synthetic-generator",
            "actor_identity_type": ActorIdentityType.TRUSTED_PROCESS,
            "reason": "synthetic conflict created",
            "recorded_at": created_at,
        }
        event = ConflictResolutionEvent(
            **event_payload,
            event_hash=content_hash(event_payload),
        )
        connection.execute(
            "INSERT INTO conflict_resolution_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.conflict_group_id,
                event.prior_status,
                event.new_status,
                event.resolution_kind,
                event.actor_identity,
                event.actor_identity_type,
                event.recorded_at,
                event.event_hash,
                canonical_json(event),
            ),
        )


def _insert_retractions(
    connection, specs: list[dict[str, Any]], created_at: str
) -> None:
    retracted_at = "2026-02-01T00:00:00Z"
    for spec in specs[::20]:
        _insert_status_event(
            connection,
            spec["claim_id"],
            ClaimStatus.RETRACTED,
            retracted_at,
            reason="synthetic retraction",
        )


def _insert_source_retractions(
    connection, sources: list[SourceRecord], created_at: str
) -> None:
    for source in sources[::20]:
        payload = {
            "event_id": f"status.{source.source_id}",
            "source_id": source.source_id,
            "status": SourceStatus.RETRACTED,
            "actor": "m26-synthetic-generator",
            "actor_identity_type": ActorIdentityType.TRUSTED_PROCESS,
            "reason": "synthetic source retraction",
            "recorded_at": "2026-02-01T00:00:00Z",
        }
        connection.execute(
            "INSERT INTO source_status_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (*payload.values(), content_hash(payload)),
        )


def _insert_status_event(
    connection,
    claim_id: str,
    status: ClaimStatus,
    recorded_at: str,
    *,
    reason: str | None = None,
) -> None:
    payload = {
        "event_id": f"status.{claim_id}.{status}",
        "claim_id": claim_id,
        "status": status,
        "actor": "m26-synthetic-generator",
        "actor_identity_type": ActorIdentityType.TRUSTED_PROCESS,
        "reason": reason,
        "recorded_at": recorded_at,
    }
    connection.execute(
        "INSERT INTO claim_status_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (*payload.values(), content_hash(payload)),
    )


def _value(predicate_index: int, index: int, entity_count: int) -> FactValue:
    kind = list(FactValueKind)[predicate_index % len(FactValueKind)]
    if kind == FactValueKind.STRING:
        return FactValue.create(kind, f"value-{index}")
    if kind == FactValueKind.INTEGER:
        return FactValue.create(kind, index)
    if kind == FactValueKind.DECIMAL:
        return FactValue.create(kind, f"{index}.25")
    if kind == FactValueKind.BOOLEAN:
        return FactValue.create(kind, bool(index % 2))
    if kind == FactValueKind.DATE:
        return FactValue.create(kind, _date_text(index))
    if kind == FactValueKind.DATETIME:
        return FactValue.create(kind, f"{_date_text(index)}T12:00:00+03:00")
    if kind == FactValueKind.ENTITY_REF:
        return FactValue.create(
            kind, f"entity.synthetic.{(index + 1) % entity_count:04d}"
        )
    if kind == FactValueKind.QUANTITY:
        return FactValue.create(kind, f"{index}.5", unit="m", original_unit="metres")
    return FactValue.create(kind, f"ENUM_{index % 11}")


def _different_value(value: FactValue, index: int, entity_count: int) -> FactValue:
    if value.kind == FactValueKind.BOOLEAN:
        return FactValue.create(value.kind, not value.value)
    if value.kind == FactValueKind.ENTITY_REF:
        return FactValue.create(
            value.kind, f"entity.synthetic.{(index + 7) % entity_count:04d}"
        )
    if value.kind == FactValueKind.ENUM:
        return FactValue.create(value.kind, f"ENUM_CONFLICT_{index % 11}")
    raise AssertionError(f"unexpected equal generated value: {value.kind}")


def _valid_interval(
    predicate_index: int, index: int, temporal_update: bool
) -> tuple[str | None, str | None]:
    mode = _predicate_mode(predicate_index)
    if mode == TemporalMode.ATEMPORAL:
        return None, None
    if mode == TemporalMode.EVENT:
        return _date_text(index), None
    if temporal_update:
        return "2025-01-01", None
    return "2020-01-01", "2025-01-01"


def _date_text(index: int) -> str:
    return (datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=index)).date().isoformat()


def _predicate_mode(index: int) -> TemporalMode:
    kind = list(FactValueKind)[index % len(FactValueKind)]
    if kind in {FactValueKind.BOOLEAN, FactValueKind.ENTITY_REF}:
        return TemporalMode.EVENT
    return (TemporalMode.ATEMPORAL, TemporalMode.VALID_INTERVAL, TemporalMode.EVENT)[
        index % 3
    ]


def _predicate_cardinality(index: int) -> Cardinality:
    return Cardinality.MULTI if index % 5 == 4 else Cardinality.SINGLE


def _latencies(connection, sql: str, parameters, samples: int) -> list[float]:
    rows = []
    for _ in range(samples):
        started = time.perf_counter_ns()
        connection.execute(sql, parameters()).fetchall()
        rows.append((time.perf_counter_ns() - started) / 1_000_000)
    return rows


def _percentiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "p50": statistics.median(ordered),
        "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
        "p99": ordered[min(len(ordered) - 1, int(len(ordered) * 0.99))],
    }


def _counts(values) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = str(value)
        result[key] = result.get(key, 0) + 1
    return result
