"""Fail-closed, non-destructive FactMemory schema-v1 to schema-v2 migration."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_brain.stage2.facts.canonical import (
    bytes_hash,
    canonical_json,
    content_hash,
    temporal_key,
    utc_now,
)
from ai_brain.stage2.facts.memory import FactMemory, _evidence_from_json
from ai_brain.stage2.facts.models import (
    ActorIdentityType,
    ConflictResolutionEvent,
    ConflictResolutionIntegrityStatus,
    ConflictResolutionKind,
    ConflictResolutionStatus,
    EvidenceRelation,
)
from ai_brain.stage2.facts.persistence import (
    _SCHEMA,
    FactDatabase,
)
from ai_brain.stage2.facts.sources import ContentAddressedSourceStore
from ai_brain.stage2.facts.version import (
    FACT_CONFLICT_POLICY_VERSION,
    FACT_MEMORY_APPLICATION_ID,
    FACT_MEMORY_MIGRATION_VERSION,
    FACT_MEMORY_SCHEMA_VERSION,
)


class FactMemoryMigrationError(RuntimeError):
    pass


def create_v3_compatibility_fixture(v4_root: Path, v3_root: Path) -> dict[str, Any]:
    """Project a verified v4 memory into a structural v3 migration fixture."""
    source = FactMemory.open(v4_root)
    source.verify()
    target = v3_root.resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError("schema-v3 fixture target must be empty")
    shutil.copytree(v4_root.resolve(), target, dirs_exist_ok=True)
    connection = sqlite3.connect(target / "fact_memory.sqlite3")
    connection.row_factory = sqlite3.Row
    try:
        for row in tuple(
            connection.execute(
                "SELECT event_id, payload_json FROM conflict_resolution_events"
            )
        ):
            payload = json.loads(row["payload_json"])
            payload.pop("event_hash")
            payload.pop("policy_version", None)
            payload.pop("integrity_status", None)
            payload.pop("legacy_event_hash", None)
            digest = content_hash(payload)
            payload["event_hash"] = digest
            connection.execute(
                "UPDATE conflict_resolution_events SET event_hash = ?, payload_json = ? WHERE event_id = ?",
                (digest, canonical_json(payload), row["event_id"]),
            )
        connection.execute(
            "UPDATE metadata SET value = '3' WHERE key IN ('schema_version', 'migration_version')"
        )
        connection.commit()
    finally:
        connection.close()
    return {
        **_verify_v3(target),
        "fixture_tree_sha256": _tree_manifest(target)["tree_sha256"],
    }


def create_v2_compatibility_fixture(v3_root: Path, v2_root: Path) -> dict[str, Any]:
    """Project a verified v3 memory into a structural v2 migration fixture."""
    source = FactMemory.open(v3_root)
    source.verify()
    target = v2_root.resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError("schema-v2 fixture target must be empty")
    shutil.copytree(v3_root.resolve(), target, dirs_exist_ok=True)
    connection = sqlite3.connect(target / "fact_memory.sqlite3")
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DROP TABLE IF EXISTS resolution_evidence_links")
        connection.execute("DROP INDEX IF EXISTS idx_claim_record_hash")
        connection.execute(
            """CREATE TABLE claims_v2 (
                claim_id TEXT PRIMARY KEY,
                subject_entity_id TEXT NOT NULL REFERENCES entities(entity_id),
                predicate_id TEXT NOT NULL REFERENCES predicate_definitions(predicate_id),
                object_hash TEXT NOT NULL,
                qualifier_hash TEXT NOT NULL,
                valid_from_key TEXT NOT NULL,
                valid_to_key TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                base_status TEXT NOT NULL,
                canonical_claim_hash TEXT NOT NULL UNIQUE,
                proposal_hash TEXT NOT NULL,
                approval_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL
            ) STRICT"""
        )
        for row in tuple(connection.execute("SELECT * FROM claims")):
            payload = json.loads(row["payload_json"])
            payload.pop("claim_record_hash", None)
            payload["schema_version"] = 2
            connection.execute(
                "INSERT INTO claims_v2 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["claim_id"],
                    row["subject_entity_id"],
                    row["predicate_id"],
                    row["object_hash"],
                    row["qualifier_hash"],
                    row["valid_from_key"],
                    row["valid_to_key"],
                    row["recorded_at"],
                    row["base_status"],
                    row["canonical_claim_hash"],
                    row["proposal_hash"],
                    row["approval_hash"],
                    canonical_json(payload),
                ),
            )
        connection.execute("DROP TABLE claims")
        connection.execute("ALTER TABLE claims_v2 RENAME TO claims")
        connection.execute(
            "CREATE INDEX idx_claim_exact ON claims(subject_entity_id, predicate_id, recorded_at)"
        )
        connection.execute(
            "CREATE INDEX idx_claim_valid ON claims(subject_entity_id, predicate_id, valid_from_key, valid_to_key)"
        )
        connection.execute(
            "UPDATE metadata SET value = '2' WHERE key IN ('schema_version', 'migration_version')"
        )
        connection.commit()
    finally:
        connection.close()
    verification = _verify_v2(target)
    return {
        **verification,
        "fixture_tree_sha256": _tree_manifest(target)["tree_sha256"],
    }


def create_v1_compatibility_fixture(v2_root: Path, v1_root: Path) -> dict[str, Any]:
    """Freeze a deterministic structural schema-v1 fixture from trusted v2 rows."""
    source = FactMemory.open(v2_root)
    source.verify()
    target = v1_root.resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError("schema-v1 fixture target must be empty")
    target.mkdir(parents=True, exist_ok=True)
    target_db = target / "fact_memory.sqlite3"
    source_connection = source.database.connect()
    destination = sqlite3.connect(target_db)
    destination.row_factory = sqlite3.Row
    try:
        destination.executescript(_legacy_schema_sql())
        tables = tuple(
            row[0]
            for row in source_connection.execute(
                """SELECT name FROM sqlite_master
                   WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                     AND name NOT IN ('conflict_resolution_events', 'migration_record_hashes')
                   ORDER BY name"""
            )
        )
        for table in tables:
            source_columns = {
                row[1]
                for row in source_connection.execute(f"PRAGMA table_info({table})")
            }
            target_columns = tuple(
                row[1] for row in destination.execute(f"PRAGMA table_info({table})")
            )
            columns = tuple(item for item in target_columns if item in source_columns)
            if not columns:
                continue
            names = ", ".join(columns)
            placeholders = ", ".join("?" for _ in columns)
            rows = source_connection.execute(f"SELECT {names} FROM {table}")
            destination.executemany(
                f"INSERT INTO {table} ({names}) VALUES ({placeholders})",
                (tuple(row) for row in rows),
            )
        _rewrite_projected_v1_transaction_hashes(destination)
        for row in tuple(
            destination.execute("SELECT claim_id, payload_json FROM claims")
        ):
            payload = json.loads(row[1])
            payload.pop("claim_record_hash", None)
            payload["schema_version"] = 1
            destination.execute(
                "UPDATE claims SET payload_json = ? WHERE claim_id = ?",
                (canonical_json(payload), row[0]),
            )
        destination.execute(
            "UPDATE metadata SET value = '1' WHERE key IN ('schema_version', 'migration_version')"
        )
        destination.execute(f"PRAGMA application_id = {FACT_MEMORY_APPLICATION_ID}")
        destination.commit()
    finally:
        destination.close()
        source_connection.close()
    if source.database.blobs.root.exists():
        shutil.copytree(source.database.blobs.root, target / "blobs")
    verification = _verify_v1(target)
    return {
        **verification,
        "fixture_tree_sha256": _tree_manifest(target)["tree_sha256"],
    }


def migrate_v1_to_v2(source_root: Path, target_root: Path) -> dict[str, Any]:
    """Create a verified v2 target without modifying the v1 source tree."""
    source = source_root.resolve()
    target = target_root.resolve()
    if source == target or source in target.parents or target in source.parents:
        raise FactMemoryMigrationError("migration source and target must be separate")
    if not source.is_dir():
        raise FactMemoryMigrationError("schema-v1 source directory is missing")
    if target.exists() and any(target.iterdir()):
        raise FactMemoryMigrationError("migration target must be new or empty")

    source_before = _tree_manifest(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="fact-v2-migration-", dir=target.parent))
    source_snapshot = staging / "source-v1"
    work = staging / "target-v2"
    started = time.perf_counter()
    try:
        shutil.copytree(source, source_snapshot)
        verification = _verify_v1(source_snapshot)
        shutil.copytree(source_snapshot, work)
        _upgrade_schema(work)
        database = FactDatabase(work)
        with database.write() as connection:
            migration_hash_count = _record_v2_interpretation_hashes(connection)
            conflict_event_count = _seed_conflict_history(connection)
            database.append_audit(
                connection,
                "FACT_MEMORY_MIGRATED_V1_TO_V2",
                {
                    "source_snapshot_hash": source_before["tree_sha256"],
                    "source_memory_snapshot_hash": verification["snapshot_hash"],
                    "migration_record_hash_count": migration_hash_count,
                    "initial_conflict_event_count": conflict_event_count,
                },
            )
        _upgrade_v2_to_v3(work)
        memory = FactMemory.open(work)
        integrity = memory.verify()
        with database.connect() as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        source_after = _tree_manifest(source)
        if source_after != source_before:
            raise FactMemoryMigrationError("schema-v1 source changed during migration")
        counts = _table_counts(database)
        polarity = _polarity_counts(database)
        manifest_body = {
            "migration": "FACT_MEMORY_V1_TO_V3",
            "source_schema_version": 1,
            "target_schema_version": FACT_MEMORY_SCHEMA_VERSION,
            "target_migration_version": FACT_MEMORY_MIGRATION_VERSION,
            "source_root_hash": source_before["tree_sha256"],
            "source_database_sha256": source_before["files"].get("fact_memory.sqlite3"),
            "target_database_sha256": bytes_hash(database.db_path.read_bytes()),
            "source_snapshot_hash": verification["snapshot_hash"],
            "target_snapshot_hash": database.snapshot_hash(),
            "record_counts": counts,
            "evidence_polarity_counts": polarity,
            "migration_record_hash_count": migration_hash_count,
            "initial_conflict_resolution_event_count": conflict_event_count,
            "source_blobs": database.blobs.manifest(),
            "source_unchanged": True,
            "integrity": integrity,
            "duration_seconds": format(time.perf_counter() - started, ".6f"),
            "created_at": utc_now(),
        }
        manifest = {
            **manifest_body,
            "migration_manifest_sha256": content_hash(manifest_body),
        }
        (work / "migration_manifest.json").write_text(
            canonical_json(manifest) + "\n",
            encoding="utf-8",
        )
        if target.exists():
            target.rmdir()
        work.replace(target)
        shutil.rmtree(staging, ignore_errors=True)
        FactMemory.open(target).verify()
        return manifest
    except BaseException as error:
        shutil.rmtree(staging, ignore_errors=True)
        if target.exists() and not any(target.iterdir()):
            target.rmdir()
        if _tree_manifest(source) != source_before:
            raise FactMemoryMigrationError(
                "migration failed and source-byte preservation could not be proven"
            ) from error
        if isinstance(error, FactMemoryMigrationError):
            raise
        raise FactMemoryMigrationError(
            "schema-v1 migration failed; source was left untouched"
        ) from error


def migrate_v2_to_v3(source_root: Path, target_root: Path) -> dict[str, Any]:
    """Create a verified schema-v3 copy while preserving schema-v2 bytes."""
    source = source_root.resolve()
    target = target_root.resolve()
    if source == target or source in target.parents or target in source.parents:
        raise FactMemoryMigrationError("migration source and target must be separate")
    if not source.is_dir():
        raise FactMemoryMigrationError("schema-v2 source directory is missing")
    if target.exists() and any(target.iterdir()):
        raise FactMemoryMigrationError("migration target must be new or empty")

    source_before = _tree_manifest(source)
    verification = _verify_v2(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="fact-v3-migration-", dir=target.parent))
    work = staging / "target-v3"
    started = time.perf_counter()
    try:
        shutil.copytree(source, work)
        claim_count = _upgrade_v2_to_v3(work)
        _upgrade_conflict_policy_v4(work)
        database = FactDatabase(work)
        with database.write() as connection:
            database.append_audit(
                connection,
                "FACT_MEMORY_MIGRATED_V2_TO_V3",
                {
                    "source_root_hash": source_before["tree_sha256"],
                    "source_snapshot_hash": verification["snapshot_hash"],
                    "claim_record_hash_count": claim_count,
                },
            )
        integrity = FactMemory.open(work).verify()
        with database.connect() as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        if _tree_manifest(source) != source_before:
            raise FactMemoryMigrationError("schema-v2 source changed during migration")
        manifest_body = {
            "migration": "FACT_MEMORY_V2_TO_V3",
            "source_schema_version": 2,
            "target_schema_version": FACT_MEMORY_SCHEMA_VERSION,
            "target_migration_version": FACT_MEMORY_MIGRATION_VERSION,
            "source_root_hash": source_before["tree_sha256"],
            "source_database_sha256": source_before["files"].get("fact_memory.sqlite3"),
            "target_database_sha256": bytes_hash(database.db_path.read_bytes()),
            "source_snapshot_hash": verification["snapshot_hash"],
            "target_snapshot_hash": database.snapshot_hash(),
            "record_counts": _table_counts(database),
            "claim_record_hash_count": claim_count,
            "evidence_polarity_counts": _polarity_counts(database),
            "source_unchanged": True,
            "integrity": integrity,
            "duration_seconds": format(time.perf_counter() - started, ".6f"),
            "created_at": utc_now(),
        }
        manifest = {
            **manifest_body,
            "migration_manifest_sha256": content_hash(manifest_body),
        }
        (work / "migration_manifest.json").write_text(
            canonical_json(manifest) + "\n", encoding="utf-8"
        )
        if target.exists():
            target.rmdir()
        work.replace(target)
        shutil.rmtree(staging, ignore_errors=True)
        FactMemory.open(target).verify()
        return manifest
    except BaseException as error:
        shutil.rmtree(staging, ignore_errors=True)
        if target.exists() and not any(target.iterdir()):
            target.rmdir()
        if _tree_manifest(source) != source_before:
            raise FactMemoryMigrationError(
                "migration failed and source-byte preservation could not be proven"
            ) from error
        if isinstance(error, FactMemoryMigrationError):
            raise
        raise FactMemoryMigrationError(
            "schema-v2 migration failed; source was left untouched"
        ) from error


def migrate_v3_to_v4(source_root: Path, target_root: Path) -> dict[str, Any]:
    """Create a verified schema-v4 copy while preserving schema-v3 bytes."""
    source = source_root.resolve()
    target = target_root.resolve()
    if source == target or source in target.parents or target in source.parents:
        raise FactMemoryMigrationError("migration source and target must be separate")
    if not source.is_dir():
        raise FactMemoryMigrationError("schema-v3 source directory is missing")
    if target.exists() and any(target.iterdir()):
        raise FactMemoryMigrationError("migration target must be new or empty")
    source_before = _tree_manifest(source)
    verification = _verify_v3(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="fact-v4-migration-", dir=target.parent))
    work = staging / "target-v4"
    started = time.perf_counter()
    try:
        shutil.copytree(source, work)
        counts = _upgrade_conflict_policy_v4(work)
        database = FactDatabase(work)
        with database.write() as connection:
            database.append_audit(
                connection,
                "FACT_MEMORY_MIGRATED_V3_TO_V4",
                {
                    "source_root_hash": source_before["tree_sha256"],
                    "source_snapshot_hash": verification["snapshot_hash"],
                    **counts,
                },
            )
        integrity = FactMemory.open(work).verify()
        with database.connect() as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        if _tree_manifest(source) != source_before:
            raise FactMemoryMigrationError("schema-v3 source changed during migration")
        manifest_body = {
            "migration": "FACT_MEMORY_V3_TO_V4",
            "source_schema_version": 3,
            "target_schema_version": FACT_MEMORY_SCHEMA_VERSION,
            "target_migration_version": FACT_MEMORY_MIGRATION_VERSION,
            "source_root_hash": source_before["tree_sha256"],
            "source_database_sha256": source_before["files"].get("fact_memory.sqlite3"),
            "target_database_sha256": bytes_hash(database.db_path.read_bytes()),
            "source_snapshot_hash": verification["snapshot_hash"],
            "target_snapshot_hash": database.snapshot_hash(),
            **counts,
            "record_counts": _table_counts(database),
            "source_unchanged": True,
            "integrity": integrity,
            "duration_seconds": format(time.perf_counter() - started, ".6f"),
            "created_at": utc_now(),
        }
        manifest = {
            **manifest_body,
            "migration_manifest_sha256": content_hash(manifest_body),
        }
        (work / "migration_manifest.json").write_text(
            canonical_json(manifest) + "\n", encoding="utf-8"
        )
        if target.exists():
            target.rmdir()
        work.replace(target)
        shutil.rmtree(staging, ignore_errors=True)
        FactMemory.open(target).verify()
        return manifest
    except BaseException as error:
        shutil.rmtree(staging, ignore_errors=True)
        if target.exists() and not any(target.iterdir()):
            target.rmdir()
        if _tree_manifest(source) != source_before:
            raise FactMemoryMigrationError(
                "migration failed and source-byte preservation could not be proven"
            ) from error
        if isinstance(error, FactMemoryMigrationError):
            raise
        raise FactMemoryMigrationError(
            "schema-v3 migration failed; source was left untouched"
        ) from error


def _verify_v3(root: Path) -> dict[str, Any]:
    db_path = root / "fact_memory.sqlite3"
    if not db_path.is_file():
        raise FactMemoryMigrationError("schema-v3 database is missing")
    connection = sqlite3.connect(
        f"file:{db_path.as_posix()}?mode=ro&immutable=1", uri=True
    )
    connection.row_factory = sqlite3.Row
    try:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        if (
            metadata.get("schema_version") != "3"
            or metadata.get("migration_version") != "3"
        ):
            raise FactMemoryMigrationError(
                "migration requires explicit schema-v3 source"
            )
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise FactMemoryMigrationError("schema-v3 SQLite integrity failed")
        _verify_audit_chain(connection, schema="v3")
        snapshot = metadata.get("snapshot_hash")
        if (
            not isinstance(snapshot, str)
            or re.fullmatch(r"[0-9a-f]{64}", snapshot) is None
        ):
            raise FactMemoryMigrationError("schema-v3 snapshot hash is invalid")
        return {"status": "VALID", "snapshot_hash": snapshot}
    finally:
        connection.close()


def _upgrade_conflict_policy_v4(root: Path) -> dict[str, int]:
    connection = sqlite3.connect(root / "fact_memory.sqlite3")
    connection.row_factory = sqlite3.Row
    safe_count = 0
    review_count = 0
    try:
        for row in tuple(
            connection.execute("SELECT * FROM conflict_resolution_events")
        ):
            payload = json.loads(row["payload_json"])
            old_hash = str(payload["event_hash"])
            group_claims = {
                str(item[0])
                for item in connection.execute(
                    "SELECT claim_id FROM conflict_group_claims WHERE conflict_group_id = ?",
                    (row["conflict_group_id"],),
                )
            }
            selected = set(payload.get("selected_claim_ids", ()))
            remaining = set(payload.get("remaining_claim_ids", ()))
            links = payload.get("evidence_links", ())
            supported = {
                str(item["claim_id"])
                for item in links
                if item.get("role") == "SUPPORTS_REMAINING"
            }
            contradicted = {
                str(item["claim_id"])
                for item in links
                if item.get("role") == "CONTRADICTS_REMOVED"
            }
            kind = str(payload["resolution_kind"])
            safe = selected <= group_claims and remaining <= group_claims
            recorded_at = str(payload["recorded_at"])
            for link in links:
                timing = connection.execute(
                    """SELECT e.created_at, ce.attached_at
                       FROM evidence e JOIN claim_evidence ce USING(evidence_id)
                       WHERE e.evidence_id = ? AND ce.claim_id = ?""",
                    (str(link["evidence_id"]), str(link["claim_id"])),
                ).fetchone()
                if timing is None or any(
                    temporal_key(str(value)) > temporal_key(recorded_at)
                    for value in timing
                ):
                    safe = False
            if kind == str(ConflictResolutionKind.MANUAL_RESOLUTION):
                safe = (
                    safe
                    and bool(remaining)
                    and selected == remaining
                    and supported == remaining
                    and contradicted == group_claims - remaining
                )
            if kind == str(ConflictResolutionKind.DISMISSED_AS_NOT_CONFLICTING):
                dismissal_supported = {
                    str(item["claim_id"])
                    for item in links
                    if item.get("role") == "SUPPORTS_DISMISSAL"
                }
                safe = (
                    safe
                    and selected == group_claims
                    and remaining == group_claims
                    and dismissal_supported == group_claims
                )
            if kind in {
                str(ConflictResolutionKind.CLAIM_SUPERSEDED),
                str(ConflictResolutionKind.CLAIM_RETRACTED),
            }:
                safe = safe and selected <= group_claims
            payload.pop("event_hash", None)
            payload["policy_version"] = FACT_CONFLICT_POLICY_VERSION if safe else "3.0"
            payload["integrity_status"] = (
                ConflictResolutionIntegrityStatus.VERIFIED_V4
                if safe
                else ConflictResolutionIntegrityStatus.LEGACY_RESOLUTION_REVIEW_REQUIRED
            )
            payload["legacy_event_hash"] = None if safe else old_hash
            if not safe:
                payload["new_status"] = ConflictResolutionStatus.UNRESOLVED
                payload["selected_claim_ids"] = ()
                payload["remaining_claim_ids"] = tuple(sorted(group_claims))
                review_count += 1
            else:
                safe_count += 1
            digest = content_hash(payload)
            payload["event_hash"] = digest
            connection.execute(
                "UPDATE conflict_resolution_events SET new_status = ?, event_hash = ?, payload_json = ? WHERE event_id = ?",
                (
                    payload["new_status"],
                    digest,
                    canonical_json(payload),
                    row["event_id"],
                ),
            )
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'schema_version'",
            (str(FACT_MEMORY_SCHEMA_VERSION),),
        )
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'migration_version'",
            (str(FACT_MEMORY_MIGRATION_VERSION),),
        )
        connection.commit()
    finally:
        connection.close()
    return {
        "verified_v4_resolution_count": safe_count,
        "legacy_resolution_review_required_count": review_count,
    }


def _verify_v2(root: Path) -> dict[str, Any]:
    db_path = root / "fact_memory.sqlite3"
    if not db_path.is_file():
        raise FactMemoryMigrationError("schema-v2 database is missing")
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        if (
            metadata.get("schema_version") != "2"
            or metadata.get("migration_version") != "2"
        ):
            raise FactMemoryMigrationError(
                "migration requires an explicit schema-v2 source"
            )
        if int(metadata.get("application_id", "0")) != FACT_MEMORY_APPLICATION_ID:
            raise FactMemoryMigrationError("schema-v2 application ID mismatch")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise FactMemoryMigrationError("schema-v2 SQLite integrity failed")
        _verify_audit_chain(connection, schema="v2")
        _verify_v2_records(connection)
        snapshots = tuple(
            row[0]
            for row in connection.execute("SELECT DISTINCT snapshot_hash FROM sources")
        )
    finally:
        connection.close()
    blobs = ContentAddressedSourceStore(root / "blobs")
    for snapshot_hash in snapshots:
        blobs.verify(snapshot_hash)
    return {
        "status": "VALID_V2",
        "snapshot_hash": metadata["snapshot_hash"],
        "blob_count": len(snapshots),
    }


def _verify_audit_chain(connection: sqlite3.Connection, *, schema: str) -> None:
    previous = "0" * 64
    for row in connection.execute("SELECT * FROM audit_events ORDER BY sequence"):
        if row["previous_hash"] != previous:
            raise FactMemoryMigrationError(f"schema-{schema} audit chain is broken")
        if bytes_hash(row["payload_json"].encode("utf-8")) != row["payload_hash"]:
            raise FactMemoryMigrationError(f"schema-{schema} audit payload changed")
        expected = content_hash(
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "object_id": row["object_id"],
                "recorded_at": row["recorded_at"],
                "payload_hash": row["payload_hash"],
                "previous_hash": row["previous_hash"],
            }
        )
        if expected != row["event_hash"]:
            raise FactMemoryMigrationError(f"schema-{schema} audit hash mismatch")
        previous = row["event_hash"]


def _verify_v2_records(connection: sqlite3.Connection) -> None:
    for table, hash_column, hash_field in (
        ("entities", "content_hash", "content_hash"),
        ("predicate_definitions", "content_hash", "content_hash"),
        ("sources", "record_hash", "record_hash"),
        ("evidence", "evidence_hash", "evidence_hash"),
        ("proposals", "proposal_hash", "proposal_hash"),
        ("approvals", "approval_hash", "approval_hash"),
        ("conflict_groups", "group_hash", "group_hash"),
        ("conflict_resolution_events", "event_hash", "event_hash"),
    ):
        for row in connection.execute(
            f"SELECT {hash_column}, payload_json FROM {table}"
        ):
            payload = json.loads(row[1])
            stored = payload.pop(hash_field, None)
            if stored != row[0] or content_hash(payload) != row[0]:
                raise FactMemoryMigrationError(f"schema-v2 {table} row hash mismatch")
    for row in connection.execute(
        "SELECT canonical_claim_hash, payload_json FROM claims"
    ):
        payload = json.loads(row[1])
        identity = {
            key: payload[key]
            for key in (
                "subject_entity_id",
                "predicate_id",
                "object_value",
                "qualifiers",
                "valid_from",
                "valid_to",
            )
        }
        if (
            payload.get("canonical_claim_hash") != row[0]
            or content_hash(identity) != row[0]
        ):
            raise FactMemoryMigrationError("schema-v2 claims row hash mismatch")
    for row in connection.execute(
        """SELECT ce.relation AS attached_relation, e.payload_json
           FROM claim_evidence ce JOIN evidence e USING(evidence_id)"""
    ):
        if row["attached_relation"] != json.loads(row["payload_json"])["relation"]:
            raise FactMemoryMigrationError("schema-v2 evidence polarity mismatch")


def _upgrade_v2_to_v3(root: Path) -> int:
    connection = sqlite3.connect(root / "fact_memory.sqlite3")
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(claims)")}
        if "claim_record_hash" in columns:
            raise FactMemoryMigrationError("schema-v2 claims already contain v3 hash")
        connection.execute(
            "ALTER TABLE claims ADD COLUMN claim_record_hash TEXT NOT NULL DEFAULT ''"
        )
        claim_count = 0
        for row in tuple(
            connection.execute("SELECT claim_id, payload_json FROM claims")
        ):
            payload = json.loads(row["payload_json"])
            payload.pop("claim_record_hash", None)
            payload["schema_version"] = FACT_MEMORY_SCHEMA_VERSION
            record_hash = content_hash(payload)
            payload["claim_record_hash"] = record_hash
            connection.execute(
                """UPDATE claims SET claim_record_hash = ?, payload_json = ?
                   WHERE claim_id = ?""",
                (record_hash, canonical_json(payload), row["claim_id"]),
            )
            claim_count += 1
        connection.execute(
            "CREATE UNIQUE INDEX idx_claim_record_hash ON claims(claim_record_hash)"
        )
        connection.executescript(_SCHEMA)
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'schema_version'",
            (str(FACT_MEMORY_SCHEMA_VERSION),),
        )
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'migration_version'",
            (str(FACT_MEMORY_MIGRATION_VERSION),),
        )
        connection.commit()
        return claim_count
    finally:
        connection.close()


def _verify_v1(root: Path) -> dict[str, Any]:
    db_path = root / "fact_memory.sqlite3"
    if not db_path.is_file():
        raise FactMemoryMigrationError("schema-v1 database is missing")
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        if (
            metadata.get("schema_version") != "1"
            or metadata.get("migration_version") != "1"
        ):
            raise FactMemoryMigrationError(
                "migration requires an explicit schema-v1 source"
            )
        if int(metadata.get("application_id", "0")) != FACT_MEMORY_APPLICATION_ID:
            raise FactMemoryMigrationError("schema-v1 application ID mismatch")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise FactMemoryMigrationError("schema-v1 SQLite integrity failed")
        previous = "0" * 64
        for row in connection.execute("SELECT * FROM audit_events ORDER BY sequence"):
            if row["previous_hash"] != previous:
                raise FactMemoryMigrationError("schema-v1 audit chain is broken")
            if bytes_hash(row["payload_json"].encode("utf-8")) != row["payload_hash"]:
                raise FactMemoryMigrationError("schema-v1 audit payload changed")
            expected = content_hash(
                {
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "object_id": row["object_id"],
                    "recorded_at": row["recorded_at"],
                    "payload_hash": row["payload_hash"],
                    "previous_hash": row["previous_hash"],
                }
            )
            if expected != row["event_hash"]:
                raise FactMemoryMigrationError("schema-v1 audit event hash mismatch")
            previous = row["event_hash"]
        _verify_v1_record_hashes(connection)
        snapshots = tuple(
            row[0]
            for row in connection.execute("SELECT DISTINCT snapshot_hash FROM sources")
        )
    finally:
        connection.close()
    blobs = ContentAddressedSourceStore(root / "blobs")
    for snapshot_hash in snapshots:
        blobs.verify(snapshot_hash)
    return {
        "status": "VALID_V1",
        "snapshot_hash": metadata["snapshot_hash"],
        "blob_count": len(snapshots),
    }


def _verify_v1_record_hashes(connection: sqlite3.Connection) -> None:
    payload_tables = (
        ("entities", "content_hash", "content_hash"),
        ("predicate_definitions", "content_hash", "content_hash"),
        ("sources", "record_hash", "record_hash"),
        ("evidence", "evidence_hash", "evidence_hash"),
        ("proposals", "proposal_hash", "proposal_hash"),
        ("approvals", "approval_hash", "approval_hash"),
        ("conflict_groups", "group_hash", "group_hash"),
        ("fact_answers", "answer_hash", "answer_hash"),
    )
    for table, column, payload_field in payload_tables:
        for row in connection.execute(f"SELECT {column}, payload_json FROM {table}"):
            payload = json.loads(row[1])
            stored = payload.pop(payload_field, None)
            if stored != row[0] or content_hash(payload) != row[0]:
                raise FactMemoryMigrationError(f"schema-v1 {table} row hash mismatch")

    for row in connection.execute(
        "SELECT canonical_claim_hash, payload_json FROM claims"
    ):
        payload = json.loads(row[1])
        identity = {
            key: payload[key]
            for key in (
                "subject_entity_id",
                "predicate_id",
                "object_value",
                "qualifiers",
                "valid_from",
                "valid_to",
            )
        }
        if (
            payload.get("canonical_claim_hash") != row[0]
            or content_hash(identity) != row[0]
        ):
            raise FactMemoryMigrationError("schema-v1 claims row hash mismatch")

    for row in connection.execute("SELECT query_hash, payload_json FROM fact_queries"):
        payload = json.loads(row[1])
        stored = payload.pop("query_hash", None)
        payload.pop("query_id", None)
        payload.pop("created_at", None)
        if stored != row[0] or content_hash(payload) != row[0]:
            raise FactMemoryMigrationError("schema-v1 fact query hash mismatch")

    for table, hash_column, fields in (
        (
            "claim_evidence",
            "transaction_hash",
            ("claim_id", "evidence_id", "relation", "attached_at"),
        ),
        (
            "claim_relations",
            "relation_hash",
            (
                "relation_id",
                "source_claim_id",
                "target_claim_id",
                "relation_type",
                "actor",
                "reason",
                "recorded_at",
            ),
        ),
        (
            "claim_status_events",
            "event_hash",
            ("event_id", "claim_id", "status", "actor", "reason", "recorded_at"),
        ),
        (
            "source_status_events",
            "event_hash",
            ("event_id", "source_id", "status", "actor", "reason", "recorded_at"),
        ),
    ):
        for row in connection.execute(f"SELECT * FROM {table}"):
            payload = {field: row[field] for field in fields}
            if content_hash(payload) != row[hash_column]:
                raise FactMemoryMigrationError(f"schema-v1 {table} row hash mismatch")


def _rewrite_projected_v1_transaction_hashes(
    connection: sqlite3.Connection,
) -> None:
    specs = (
        (
            "claim_relations",
            "relation_id",
            "relation_hash",
            (
                "relation_id",
                "source_claim_id",
                "target_claim_id",
                "relation_type",
                "actor",
                "reason",
                "recorded_at",
            ),
        ),
        (
            "claim_status_events",
            "event_id",
            "event_hash",
            ("event_id", "claim_id", "status", "actor", "reason", "recorded_at"),
        ),
        (
            "source_status_events",
            "event_id",
            "event_hash",
            ("event_id", "source_id", "status", "actor", "reason", "recorded_at"),
        ),
    )
    for table, id_column, hash_column, fields in specs:
        rows = tuple(connection.execute(f"SELECT * FROM {table}"))
        for row in rows:
            digest = content_hash({field: row[field] for field in fields})
            connection.execute(
                f"UPDATE {table} SET {hash_column} = ? WHERE {id_column} = ?",
                (digest, row[id_column]),
            )


def _upgrade_schema(root: Path) -> None:
    connection = sqlite3.connect(root / "fact_memory.sqlite3")
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        for table in (
            "source_status_events",
            "claim_relations",
            "claim_status_events",
        ):
            connection.execute(
                f"""ALTER TABLE {table} ADD COLUMN actor_identity_type TEXT
                    NOT NULL DEFAULT 'TRUSTED_PROCESS'
                    CHECK(actor_identity_type IN ('HUMAN', 'TRUSTED_PROCESS', 'MODEL'))"""
            )
        connection.executescript(_SCHEMA)
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'schema_version'",
            (str(FACT_MEMORY_SCHEMA_VERSION),),
        )
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'migration_version'",
            (str(FACT_MEMORY_MIGRATION_VERSION),),
        )
        connection.commit()
    finally:
        connection.close()


def _record_v2_interpretation_hashes(connection: sqlite3.Connection) -> int:
    specs = (
        ("entities", "entity_id", "content_hash", "payload_json"),
        ("predicate_definitions", "predicate_id", "content_hash", "payload_json"),
        ("sources", "source_id", "record_hash", "payload_json"),
        ("evidence", "evidence_id", "evidence_hash", "payload_json"),
        ("approvals", "approval_id", "approval_hash", "payload_json"),
        ("claims", "claim_id", "canonical_claim_hash", "payload_json"),
        ("conflict_groups", "conflict_group_id", "group_hash", "payload_json"),
        ("fact_queries", "query_id", "query_hash", "payload_json"),
        ("fact_answers", "answer_hash", "answer_hash", "payload_json"),
    )
    rows_to_insert: list[tuple[str, str, str, str]] = []
    for table, id_column, hash_column, payload_column in specs:
        for row in connection.execute(
            f"SELECT {id_column}, {hash_column}, {payload_column} FROM {table}"
        ):
            interpreted_hash = content_hash(
                {
                    "schema_version": 2,
                    "table": table,
                    "payload": json.loads(row[2]),
                }
            )
            if table == "evidence":
                interpreted = asdict(_evidence_from_json(row[2]))
                interpreted.pop("evidence_hash")
                interpreted_hash = content_hash(interpreted)
            rows_to_insert.append(
                (
                    table,
                    str(row[0]),
                    str(row[1]),
                    interpreted_hash,
                )
            )
    for table, fields, hash_column in (
        (
            "claim_evidence",
            ("claim_id", "evidence_id", "relation", "attached_at"),
            "transaction_hash",
        ),
        (
            "claim_relations",
            (
                "relation_id",
                "source_claim_id",
                "target_claim_id",
                "relation_type",
                "actor",
                "actor_identity_type",
                "reason",
                "recorded_at",
            ),
            "relation_hash",
        ),
        (
            "claim_status_events",
            (
                "event_id",
                "claim_id",
                "status",
                "actor",
                "actor_identity_type",
                "reason",
                "recorded_at",
            ),
            "event_hash",
        ),
        (
            "source_status_events",
            (
                "event_id",
                "source_id",
                "status",
                "actor",
                "actor_identity_type",
                "reason",
                "recorded_at",
            ),
            "event_hash",
        ),
    ):
        for row in connection.execute(f"SELECT * FROM {table}"):
            record_id = (
                f"{row['claim_id']}:{row['evidence_id']}"
                if table == "claim_evidence"
                else str(row[fields[0]])
            )
            interpreted = content_hash({field: row[field] for field in fields})
            rows_to_insert.append(
                (table, record_id, str(row[hash_column]), interpreted)
            )
    connection.executemany(
        "INSERT INTO migration_record_hashes VALUES (?, ?, ?, ?)",
        rows_to_insert,
    )
    return len(rows_to_insert)


def _seed_conflict_history(connection: sqlite3.Connection) -> int:
    count = 0
    for row in connection.execute(
        "SELECT payload_json FROM conflict_groups ORDER BY conflict_group_id"
    ):
        group = json.loads(row[0])
        payload = {
            "event_id": f"conflict_resolution_migration_{uuid4().hex}",
            "conflict_group_id": group["conflict_group_id"],
            "prior_status": ConflictResolutionStatus.UNRESOLVED,
            "new_status": ConflictResolutionStatus.UNRESOLVED,
            "resolution_kind": ConflictResolutionKind.INITIAL_STATE,
            "selected_claim_ids": (),
            "remaining_claim_ids": tuple(group["claim_ids"]),
            "evidence_ids": (),
            "evidence_links": (),
            "actor_identity": "M26_V1_TO_V2_MIGRATION",
            "actor_identity_type": ActorIdentityType.TRUSTED_PROCESS,
            "reason": "initial state derived from immutable schema-v1 conflict group",
            "recorded_at": group["created_at"],
            "policy_version": FACT_CONFLICT_POLICY_VERSION,
            "integrity_status": ConflictResolutionIntegrityStatus.VERIFIED_V4,
            "legacy_event_hash": None,
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
        count += 1
    return count


def _polarity_counts(database: FactDatabase) -> dict[str, int]:
    with database.connect() as connection:
        counts = {
            EvidenceRelation(row[0]).value: int(row[1])
            for row in connection.execute(
                "SELECT relation, COUNT(*) FROM claim_evidence GROUP BY relation"
            )
        }
    return {item.value: counts.get(item.value, 0) for item in EvidenceRelation}


def _table_counts(database: FactDatabase) -> dict[str, int]:
    tables = (
        "entities",
        "predicate_definitions",
        "sources",
        "evidence",
        "proposals",
        "approvals",
        "claims",
        "claim_evidence",
        "claim_relations",
        "claim_status_events",
        "source_status_events",
        "conflict_groups",
        "conflict_resolution_events",
        "fact_queries",
        "fact_answers",
        "audit_events",
    )
    with database.connect() as connection:
        return {
            table: int(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            )
            for table in tables
        }


def _tree_manifest(root: Path) -> dict[str, Any]:
    files = {
        item.relative_to(root).as_posix(): bytes_hash(item.read_bytes())
        for item in sorted(root.rglob("*"))
        if item.is_file()
    }
    return {"files": files, "tree_sha256": content_hash(files)}


def _legacy_schema_sql() -> str:
    schema = re.sub(
        r"\n    actor_identity_type TEXT NOT NULL\n"
        r"        CHECK\(actor_identity_type IN \('HUMAN', 'TRUSTED_PROCESS', 'MODEL'\)\),",
        "",
        _SCHEMA,
    )
    schema = re.sub(
        r"    claim_record_hash TEXT NOT NULL UNIQUE,\n",
        "",
        schema,
    )
    schema = re.sub(
        r"CREATE TABLE IF NOT EXISTS resolution_evidence_links \(.*?\) STRICT;\n",
        "",
        schema,
        flags=re.DOTALL,
    )
    schema = re.sub(
        r"CREATE TABLE IF NOT EXISTS conflict_resolution_events \(.*?"
        r"CREATE INDEX IF NOT EXISTS idx_conflict_resolution_time\n"
        r"    ON conflict_resolution_events\(conflict_group_id, recorded_at\);\n",
        "",
        schema,
        flags=re.DOTALL,
    )
    schema = re.sub(
        r"CREATE TABLE IF NOT EXISTS migration_record_hashes \(.*?\) STRICT;\n",
        "",
        schema,
        flags=re.DOTALL,
    )
    schema = re.sub(
        r"CREATE INDEX IF NOT EXISTS idx_evidence_relation_source\n"
        r"    ON evidence\(relation, source_id, created_at\);\n",
        "",
        schema,
    )
    schema = re.sub(
        r"CREATE INDEX IF NOT EXISTS idx_claim_evidence_polarity_time\n"
        r"    ON claim_evidence\(claim_id, relation, attached_at\);\n",
        "",
        schema,
    )
    return schema
