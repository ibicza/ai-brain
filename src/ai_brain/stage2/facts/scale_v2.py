"""M-26.1 compatibility scale regression over existing schema-v1 corpora."""

from __future__ import annotations

import json
import random
import sqlite3
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_brain.stage2.facts.benchmark import (
    _latencies,
    _measure_database,
    _percentiles,
)
from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage2.facts.memory import FactMemory, _conflict_from_json
from ai_brain.stage2.facts.migration import migrate_v1_to_v2
from ai_brain.stage2.facts.models import (
    ActorIdentityType,
    ConflictResolutionEvent,
    ConflictResolutionKind,
    ConflictResolutionStatus,
    EvidenceRelation,
)


def run_m261_scale_regression(
    output_dir: Path,
    *,
    v1_roots: dict[int, Path],
    samples: int = 500,
    seed: int = 26_100,
) -> dict[str, Any]:
    output = output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("M-26.1 scale output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for size in sorted(v1_roots):
        actual_claim_count = _v1_claim_count(v1_roots[size])
        if actual_claim_count != size:
            raise ValueError(
                f"schema-v1 corpus labeled {size} contains {actual_claim_count} claims"
            )
        target = output / f"claims_{size}_v2"
        migration_started = time.perf_counter()
        migration = migrate_v1_to_v2(v1_roots[size], target)
        migration_seconds = time.perf_counter() - migration_started
        memory = FactMemory.open(target)
        mix = augment_v2_scale_mix(
            memory,
            contradiction_count=max(10, size // 100),
            resolution_count=max(5, size // 200),
        )
        metrics = _measure_database(
            memory.database,
            size=size,
            samples=samples,
            seed=seed,
        )
        metrics.update(
            migration_seconds=migration_seconds,
            migration_manifest_sha256=migration["migration_manifest_sha256"],
            polarity_and_history=_measure_v2_queries(
                memory,
                size=size,
                samples=samples,
                seed=seed,
            ),
            mixed_artifacts=mix,
        )
        results.append(metrics)
    report = {
        "status": "PASS",
        "schema_version": 2,
        "sizes": sorted(v1_roots),
        "samples": samples,
        "results": results,
    }
    (output / "m261_scale_regression.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return report


def _v1_claim_count(root: Path) -> int:
    with sqlite3.connect(root.resolve() / "fact_memory.sqlite3") as connection:
        return int(connection.execute("SELECT COUNT(*) FROM claims").fetchone()[0])


def augment_v2_scale_mix(
    memory: FactMemory,
    *,
    contradiction_count: int,
    resolution_count: int,
) -> dict[str, int]:
    created_at = "2026-03-01T00:00:00Z"
    contradiction_hashes = []
    resolution_hashes = []
    with memory.database.write() as connection:
        rows = connection.execute(
            """SELECT ce.claim_id, e.payload_json FROM claim_evidence ce
               JOIN evidence e ON e.evidence_id = ce.evidence_id
               WHERE ce.relation = 'SUPPORTS'
               ORDER BY ce.claim_id, ce.evidence_id LIMIT ?""",
            (contradiction_count,),
        )
        for index, row in enumerate(rows):
            payload = json.loads(row["payload_json"])
            payload.pop("evidence_hash", None)
            payload.update(
                evidence_id=f"evidence.m261.contradiction.{index:06d}",
                relation=EvidenceRelation.CONTRADICTS,
                reviewer="m261-scale-generator",
                reviewer_identity_type=ActorIdentityType.TRUSTED_PROCESS,
                created_at=created_at,
            )
            evidence_hash = content_hash(payload)
            payload["evidence_hash"] = evidence_hash
            connection.execute(
                "INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    payload["evidence_id"],
                    payload["source_id"],
                    EvidenceRelation.CONTRADICTS,
                    payload["snapshot_hash"],
                    payload["approval_status"],
                    created_at,
                    evidence_hash,
                    canonical_json(payload),
                ),
            )
            attachment = {
                "claim_id": row["claim_id"],
                "evidence_id": payload["evidence_id"],
                "relation": EvidenceRelation.CONTRADICTS,
                "attached_at": created_at,
            }
            connection.execute(
                "INSERT INTO claim_evidence VALUES (?, ?, ?, ?, ?)",
                (*attachment.values(), content_hash(attachment)),
            )
            contradiction_hashes.append(evidence_hash)

        conflicts = connection.execute(
            "SELECT payload_json FROM conflict_groups ORDER BY conflict_group_id LIMIT ?",
            (resolution_count,),
        )
        for row in conflicts:
            group = _conflict_from_json(row[0])
            remaining = (group.claim_ids[-1],)
            evidence_row = connection.execute(
                """SELECT evidence_id FROM claim_evidence
                   WHERE claim_id = ? AND relation = 'SUPPORTS'
                   ORDER BY evidence_id LIMIT 1""",
                remaining,
            ).fetchone()
            evidence_ids = (evidence_row[0],) if evidence_row else ()
            payload = {
                "event_id": f"conflict_resolution_m261_{uuid4().hex}",
                "conflict_group_id": group.conflict_group_id,
                "prior_status": ConflictResolutionStatus.UNRESOLVED,
                "new_status": ConflictResolutionStatus.RESOLVED,
                "resolution_kind": ConflictResolutionKind.MANUAL_RESOLUTION,
                "selected_claim_ids": remaining,
                "remaining_claim_ids": remaining,
                "evidence_ids": evidence_ids,
                "actor_identity": "m261-scale-generator",
                "actor_identity_type": ActorIdentityType.TRUSTED_PROCESS,
                "reason": "synthetic reviewed scale resolution",
                "recorded_at": created_at,
            }
            event = ConflictResolutionEvent(
                **payload,
                event_hash=content_hash(payload),
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
            resolution_hashes.append(event.event_hash)
        memory.database.append_audit(
            connection,
            "M261_SCALE_MIX_ADDED",
            {
                "contradicting_evidence_hashes": tuple(contradiction_hashes),
                "conflict_resolution_hashes": tuple(resolution_hashes),
            },
        )
    memory.verify()
    return {
        "contradicting_evidence_count": len(contradiction_hashes),
        "conflict_resolution_event_count": len(resolution_hashes),
    }


def _measure_v2_queries(
    memory: FactMemory,
    *,
    size: int,
    samples: int,
    seed: int,
) -> dict[str, Any]:
    rng = random.Random(seed + size)
    with memory.database.connect() as connection:
        queries = {
            "evidence_polarity": (
                """SELECT relation, COUNT(*) FROM claim_evidence
                   WHERE claim_id = ? GROUP BY relation""",
                lambda: (f"claim.synthetic.{rng.randrange(size):06d}",),
            ),
            "historical_status": (
                """SELECT status FROM claim_status_events
                   WHERE claim_id = ? AND recorded_at <= ?
                   ORDER BY recorded_at DESC LIMIT 1""",
                lambda: (
                    f"claim.synthetic.{rng.randrange(size):06d}",
                    "2026-01-15T00:00:00Z",
                ),
            ),
            "conflict_as_of": (
                """SELECT new_status FROM conflict_resolution_events
                   WHERE conflict_group_id = ? AND recorded_at <= ?
                   ORDER BY recorded_at DESC LIMIT 1""",
                lambda: (
                    f"conflict.synthetic.{rng.randrange(max(1, size // 20)):06d}",
                    "2026-04-01T00:00:00Z",
                ),
            ),
        }
        latencies = {
            name: _percentiles(_latencies(connection, sql, parameters, samples))
            for name, (sql, parameters) in queries.items()
        }
        plans = {
            name: [
                row[3]
                for row in connection.execute(
                    f"EXPLAIN QUERY PLAN {sql}",
                    parameters(),
                )
            ]
            for name, (sql, parameters) in queries.items()
        }
    full_scans = [
        name
        for name, rows in plans.items()
        if any("SCAN" in row and "USING INDEX" not in row for row in rows)
    ]
    return {
        "latency_ms": latencies,
        "query_plans": plans,
        "full_scan_queries": full_scans,
    }
