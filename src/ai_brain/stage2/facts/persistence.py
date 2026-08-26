"""Transactional SQLite persistence, integrity, export and recovery."""

from __future__ import annotations

import contextlib
import json
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_brain.stage2.facts.canonical import (
    bytes_hash,
    canonical_json,
    content_hash,
    utc_now,
)
from ai_brain.stage2.facts.sources import ContentAddressedSourceStore
from ai_brain.stage2.facts.version import (
    DEFAULT_BUSY_TIMEOUT_MS,
    FACT_MEMORY_APPLICATION_ID,
    FACT_MEMORY_MIGRATION_VERSION,
    FACT_MEMORY_SCHEMA_VERSION,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS entity_aliases (
    normalized_alias TEXT NOT NULL,
    language TEXT NOT NULL,
    entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    original_alias TEXT NOT NULL,
    PRIMARY KEY (normalized_alias, language, entity_id)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_entity_alias_lookup
    ON entity_aliases(normalized_alias, language);
CREATE TABLE IF NOT EXISTS predicate_definitions (
    predicate_id TEXT PRIMARY KEY,
    subject_entity_type TEXT NOT NULL,
    object_kind TEXT NOT NULL,
    cardinality TEXT NOT NULL,
    temporal_mode TEXT NOT NULL,
    active INTEGER NOT NULL CHECK(active IN (0, 1)),
    deprecated INTEGER NOT NULL CHECK(deprecated IN (0, 1)),
    content_hash TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    source_family TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    trust_tier TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    record_hash TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS idx_sources_snapshot ON sources(snapshot_hash);
CREATE TABLE IF NOT EXISTS source_status_events (
    event_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    status TEXT NOT NULL,
    actor TEXT NOT NULL,
    actor_identity_type TEXT NOT NULL
        CHECK(actor_identity_type IN ('HUMAN', 'TRUSTED_PROCESS', 'MODEL')),
    reason TEXT,
    recorded_at TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE
) STRICT;
CREATE INDEX IF NOT EXISTS idx_source_status_time
    ON source_status_events(source_id, recorded_at);
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    relation TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    approval_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    evidence_hash TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source_id);
CREATE INDEX IF NOT EXISTS idx_evidence_relation_source
    ON evidence(relation, source_id, created_at);
CREATE TABLE IF NOT EXISTS proposals (
    proposal_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    status TEXT NOT NULL,
    proposal_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (proposal_id, revision)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_proposals_latest ON proposals(proposal_id, revision DESC);
CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    proposal_hash TEXT NOT NULL,
    decision TEXT NOT NULL,
    created_at TEXT NOT NULL,
    approval_hash TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS claims (
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
) STRICT;
CREATE INDEX IF NOT EXISTS idx_claim_exact
    ON claims(subject_entity_id, predicate_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_claim_valid
    ON claims(subject_entity_id, predicate_id, valid_from_key, valid_to_key);
CREATE TABLE IF NOT EXISTS claim_evidence (
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
    relation TEXT NOT NULL,
    attached_at TEXT NOT NULL,
    transaction_hash TEXT NOT NULL UNIQUE,
    PRIMARY KEY (claim_id, evidence_id)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_claim_evidence_polarity_time
    ON claim_evidence(claim_id, relation, attached_at);
CREATE TABLE IF NOT EXISTS claim_relations (
    relation_id TEXT PRIMARY KEY,
    source_claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    target_claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    relation_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    actor_identity_type TEXT NOT NULL
        CHECK(actor_identity_type IN ('HUMAN', 'TRUSTED_PROCESS', 'MODEL')),
    reason TEXT,
    recorded_at TEXT NOT NULL,
    relation_hash TEXT NOT NULL UNIQUE
) STRICT;
CREATE INDEX IF NOT EXISTS idx_claim_rel_source
    ON claim_relations(source_claim_id, relation_type, recorded_at);
CREATE INDEX IF NOT EXISTS idx_claim_rel_target
    ON claim_relations(target_claim_id, relation_type, recorded_at);
CREATE TABLE IF NOT EXISTS claim_status_events (
    event_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    status TEXT NOT NULL,
    actor TEXT NOT NULL,
    actor_identity_type TEXT NOT NULL
        CHECK(actor_identity_type IN ('HUMAN', 'TRUSTED_PROCESS', 'MODEL')),
    reason TEXT,
    recorded_at TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE
) STRICT;
CREATE INDEX IF NOT EXISTS idx_claim_status_time
    ON claim_status_events(claim_id, recorded_at);
CREATE TABLE IF NOT EXISTS conflict_groups (
    conflict_group_id TEXT PRIMARY KEY,
    subject_entity_id TEXT NOT NULL REFERENCES entities(entity_id),
    predicate_id TEXT NOT NULL REFERENCES predicate_definitions(predicate_id),
    resolution_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    group_hash TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS idx_conflict_lookup
    ON conflict_groups(subject_entity_id, predicate_id, resolution_status);
CREATE TABLE IF NOT EXISTS conflict_group_claims (
    conflict_group_id TEXT NOT NULL REFERENCES conflict_groups(conflict_group_id),
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    PRIMARY KEY (conflict_group_id, claim_id)
) STRICT;
CREATE TABLE IF NOT EXISTS conflict_resolution_events (
    event_id TEXT PRIMARY KEY,
    conflict_group_id TEXT NOT NULL REFERENCES conflict_groups(conflict_group_id),
    prior_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    resolution_kind TEXT NOT NULL,
    actor_identity TEXT NOT NULL,
    actor_identity_type TEXT NOT NULL
        CHECK(actor_identity_type IN ('HUMAN', 'TRUSTED_PROCESS', 'MODEL')),
    recorded_at TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS idx_conflict_resolution_time
    ON conflict_resolution_events(conflict_group_id, recorded_at);
CREATE TABLE IF NOT EXISTS fact_queries (
    query_id TEXT PRIMARY KEY,
    query_hash TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
) STRICT;
CREATE INDEX IF NOT EXISTS idx_fact_query_semantic ON fact_queries(query_hash);
CREATE TABLE IF NOT EXISTS fact_answers (
    answer_hash TEXT PRIMARY KEY,
    query_id TEXT NOT NULL REFERENCES fact_queries(query_id),
    query_hash TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS audit_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    object_id TEXT,
    recorded_at TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS migration_record_hashes (
    table_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    interpreted_v2_hash TEXT NOT NULL,
    PRIMARY KEY (table_name, record_id)
) STRICT;
"""


class FactMemoryIntegrityError(RuntimeError):
    pass


class FactMemoryRecoveryError(RuntimeError):
    pass


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


class FactDatabase:
    def __init__(
        self, root: Path, *, busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS
    ) -> None:
        self.root = root.resolve()
        self.db_path = self.root / "fact_memory.sqlite3"
        self.blobs = ContentAddressedSourceStore(self.root / "blobs")
        self.busy_timeout_ms = busy_timeout_ms

    @classmethod
    def initialize(cls, root: Path) -> FactDatabase:
        database = cls(root)
        database.root.mkdir(parents=True, exist_ok=True)
        with database.connect() as connection:
            connection.executescript(_SCHEMA)
            metadata = {
                "schema_version": str(FACT_MEMORY_SCHEMA_VERSION),
                "migration_version": str(FACT_MEMORY_MIGRATION_VERSION),
                "application_id": str(FACT_MEMORY_APPLICATION_ID),
                "snapshot_version": "0",
                "snapshot_hash": content_hash({"empty": True}),
                "recovery_status": "PRIMARY",
                "created_at": utc_now(),
            }
            connection.executemany(
                "INSERT OR IGNORE INTO metadata(key, value) VALUES (?, ?)",
                metadata.items(),
            )
            connection.commit()
        database.verify_schema()
        return database

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.db_path,
            timeout=self.busy_timeout_ms / 1000,
            factory=_ClosingConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(f"PRAGMA application_id = {FACT_MEMORY_APPLICATION_ID}")
        return connection

    @contextlib.contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def verify_schema(self) -> None:
        if not self.db_path.is_file():
            raise FactMemoryIntegrityError("FactMemory database is missing")
        with self.connect() as connection:
            rows = dict(
                connection.execute("SELECT key, value FROM metadata").fetchall()
            )
            expected = {
                "schema_version": str(FACT_MEMORY_SCHEMA_VERSION),
                "migration_version": str(FACT_MEMORY_MIGRATION_VERSION),
                "application_id": str(FACT_MEMORY_APPLICATION_ID),
            }
            if any(rows.get(key) != value for key, value in expected.items()):
                raise FactMemoryIntegrityError(
                    "FactMemory schema requires explicit migration"
                )
            application_id = connection.execute("PRAGMA application_id").fetchone()[0]
            if application_id != FACT_MEMORY_APPLICATION_ID:
                raise FactMemoryIntegrityError("FactMemory application ID mismatch")

    def append_audit(
        self,
        connection: sqlite3.Connection,
        event_type: str,
        payload: dict[str, Any],
        object_id: str | None = None,
        *,
        advance_snapshot: bool = True,
    ) -> str:
        payload_json = canonical_json(payload)
        payload_digest = bytes_hash(payload_json.encode("utf-8"))
        previous = connection.execute(
            "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous[0] if previous else "0" * 64
        event = {
            "event_id": f"audit_{uuid4().hex}",
            "event_type": event_type,
            "object_id": object_id,
            "recorded_at": utc_now(),
            "payload_hash": payload_digest,
            "previous_hash": previous_hash,
        }
        event_hash = content_hash(event)
        connection.execute(
            """INSERT INTO audit_events(
                event_id, event_type, object_id, recorded_at, payload_hash,
                previous_hash, event_hash, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event["event_id"],
                event_type,
                object_id,
                event["recorded_at"],
                payload_digest,
                previous_hash,
                event_hash,
                payload_json,
            ),
        )
        if advance_snapshot:
            version = int(self.metadata(connection, "snapshot_version")) + 1
            snapshot_hash = content_hash(
                {
                    "previous": self.metadata(connection, "snapshot_hash"),
                    "event": event_hash,
                }
            )
            self.set_metadata(connection, "snapshot_version", str(version))
            self.set_metadata(connection, "snapshot_hash", snapshot_hash)
        return event_hash

    def metadata(self, connection: sqlite3.Connection, key: str) -> str:
        row = connection.execute(
            "SELECT value FROM metadata WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            raise FactMemoryIntegrityError(f"missing metadata: {key}")
        return str(row[0])

    @staticmethod
    def set_metadata(connection: sqlite3.Connection, key: str, value: str) -> None:
        connection.execute("UPDATE metadata SET value = ? WHERE key = ?", (value, key))

    def snapshot_hash(self) -> str:
        with self.connect() as connection:
            return self.metadata(connection, "snapshot_hash")

    def integrity_check(self, *, verify_blobs: bool = True) -> dict[str, Any]:
        self.verify_schema()
        with self.connect() as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise FactMemoryIntegrityError(
                    f"SQLite integrity check failed: {result}"
                )
            previous = "0" * 64
            audit_count = 0
            for row in connection.execute(
                "SELECT * FROM audit_events ORDER BY sequence"
            ):
                if row["previous_hash"] != previous:
                    raise FactMemoryIntegrityError("audit hash chain is broken")
                if (
                    bytes_hash(row["payload_json"].encode("utf-8"))
                    != row["payload_hash"]
                ):
                    raise FactMemoryIntegrityError("audit payload was changed")
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
                    raise FactMemoryIntegrityError("audit event hash mismatch")
                previous = row["event_hash"]
                audit_count += 1
            blob_count = 0
            if verify_blobs:
                for row in connection.execute(
                    "SELECT DISTINCT snapshot_hash FROM sources"
                ):
                    self.blobs.verify(row[0])
                    blob_count += 1
        return {
            "status": "VALID",
            "audit_event_count": audit_count,
            "blob_count": blob_count,
        }

    def export(self, output_dir: Path) -> dict[str, Any]:
        output = output_dir.resolve()
        output.mkdir(parents=True, exist_ok=True)
        mapping = {
            "entities.jsonl": "SELECT payload_json FROM entities ORDER BY entity_id",
            "predicates.jsonl": "SELECT payload_json FROM predicate_definitions ORDER BY predicate_id",
            "sources.jsonl": "SELECT payload_json FROM sources ORDER BY source_id",
            "evidence.jsonl": "SELECT payload_json FROM evidence ORDER BY evidence_id",
            "proposals.jsonl": "SELECT payload_json FROM proposals ORDER BY proposal_id, revision",
            "approvals.jsonl": "SELECT payload_json FROM approvals ORDER BY approval_id",
            "claims.jsonl": "SELECT payload_json FROM claims ORDER BY claim_id",
            "claim_evidence.jsonl": "SELECT * FROM claim_evidence ORDER BY claim_id, evidence_id",
            "relations.jsonl": "SELECT * FROM claim_relations ORDER BY relation_id",
            "claim_status_events.jsonl": "SELECT * FROM claim_status_events ORDER BY recorded_at, event_id",
            "source_status_events.jsonl": "SELECT * FROM source_status_events ORDER BY recorded_at, event_id",
            "conflicts.jsonl": "SELECT payload_json FROM conflict_groups ORDER BY conflict_group_id",
            "conflict_resolution_events.jsonl": "SELECT payload_json FROM conflict_resolution_events ORDER BY recorded_at, event_id",
        }
        files: dict[str, dict[str, Any]] = {}
        with self.connect() as connection:
            for name, statement in mapping.items():
                lines = []
                for row in connection.execute(statement):
                    if tuple(row.keys()) == ("payload_json",):
                        lines.append(row[0])
                    else:
                        lines.append(canonical_json(dict(row)))
                content = (("\n".join(lines) + "\n") if lines else "").encode("utf-8")
                (output / name).write_bytes(content)
                files[name] = {"sha256": bytes_hash(content), "count": len(lines)}
            manifest = {
                "schema_version": FACT_MEMORY_SCHEMA_VERSION,
                "memory_snapshot_hash": self.metadata(connection, "snapshot_hash"),
                "files": files,
                "source_blobs": self.blobs.manifest(),
                "created_at": utc_now(),
            }
        manifest_bytes = (canonical_json(manifest) + "\n").encode("utf-8")
        (output / "manifest.json").write_bytes(manifest_bytes)
        return {**manifest, "manifest_sha256": bytes_hash(manifest_bytes)}

    def backup(self, output_dir: Path) -> dict[str, Any]:
        destination = output_dir.resolve()
        if destination == self.root or self.root in destination.parents:
            raise ValueError("backup destination must be outside FactMemory root")
        destination.mkdir(parents=True, exist_ok=True)
        backup_path = destination / "fact_memory.sqlite3"
        with (
            self.connect() as source,
            sqlite3.connect(backup_path, factory=_ClosingConnection) as target,
        ):
            source.backup(target)
        blob_dir = destination / "blobs"
        if blob_dir.exists():
            shutil.rmtree(blob_dir)
        if self.blobs.root.exists():
            shutil.copytree(self.blobs.root, blob_dir)
        database_hash = bytes_hash(backup_path.read_bytes())
        manifest = {
            "schema_version": FACT_MEMORY_SCHEMA_VERSION,
            "memory_snapshot_hash": self.snapshot_hash(),
            "database_sha256": database_hash,
            "source_blobs": ContentAddressedSourceStore(blob_dir).manifest(),
            "created_at": utc_now(),
        }
        manifest_bytes = (canonical_json(manifest) + "\n").encode("utf-8")
        (destination / "backup_manifest.json").write_bytes(manifest_bytes)
        return {**manifest, "manifest_sha256": bytes_hash(manifest_bytes)}

    @classmethod
    def restore(cls, backup_dir: Path, target_dir: Path) -> FactDatabase:
        source = backup_dir.resolve()
        target = target_dir.resolve()
        if target.exists() and any(target.iterdir()):
            raise FactMemoryRecoveryError(
                "restore target must be a new empty directory"
            )
        manifest_path = source / "backup_manifest.json"
        database_path = source / "fact_memory.sqlite3"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise FactMemoryRecoveryError(
                "backup manifest is missing or corrupt"
            ) from error
        if bytes_hash(database_path.read_bytes()) != manifest.get("database_sha256"):
            raise FactMemoryRecoveryError("backup database hash mismatch")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.rmdir()
        temporary = Path(tempfile.mkdtemp(prefix="fact-restore-", dir=target.parent))
        try:
            shutil.copy2(database_path, temporary / "fact_memory.sqlite3")
            if (source / "blobs").exists():
                shutil.copytree(source / "blobs", temporary / "blobs")
            restored = cls(temporary)
            restored.integrity_check()
            if restored.snapshot_hash() != manifest.get("memory_snapshot_hash"):
                raise FactMemoryRecoveryError("backup snapshot is stale or mismatched")
            target.mkdir()
            shutil.copy2(
                temporary / "fact_memory.sqlite3", target / "fact_memory.sqlite3"
            )
            if (temporary / "blobs").exists():
                shutil.copytree(temporary / "blobs", target / "blobs")
            cls(target).integrity_check()
            shutil.rmtree(temporary)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        result = cls(target)
        with result.write() as connection:
            result.set_metadata(
                connection, "recovery_status", f"RESTORED_FROM:{source}"
            )
            result.append_audit(
                connection, "FACT_MEMORY_RECOVERED", {"backup": str(source)}
            )
        return result

    def audit_replay(self, object_id: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as connection:
            if object_id is None:
                rows = connection.execute(
                    "SELECT * FROM audit_events ORDER BY sequence"
                )
            else:
                rows = connection.execute(
                    "SELECT * FROM audit_events WHERE object_id = ? ORDER BY sequence",
                    (object_id,),
                )
            return [
                {
                    "sequence": row["sequence"],
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "object_id": row["object_id"],
                    "recorded_at": row["recorded_at"],
                    "payload_hash": row["payload_hash"],
                    "event_hash": row["event_hash"],
                    "payload": json.loads(row["payload_json"]),
                }
                for row in rows
            ]
