"""Checksummed transactional persistence for unified routing artifacts."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_brain.stage2.facts.canonical import (
    bytes_hash,
    canonical_json,
    content_hash,
    utc_now,
)
from ai_brain.stage2.router.version import ROUTER_STORE_SCHEMA_VERSION

_SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_type TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    artifact_hash TEXT NOT NULL UNIQUE,
    request_id TEXT,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (artifact_type, artifact_id)
) STRICT;
CREATE INDEX IF NOT EXISTS idx_router_artifact_request
    ON artifacts(request_id, artifact_type);
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
"""

_ARTIFACT_HASH_FIELDS = {
    "request": "request_hash",
    "route_decision": "route_decision_hash",
    "route_receipt": "receipt_hash",
    "clarification": "clarification_hash",
    "tool_proposal": "proposal_hash",
    "tool_confirmation": "confirmation_hash",
    "tool_result": "result_hash",
    "tool_manifest": "manifest_hash",
    "response": "response_hash",
    "failure": "failure_hash",
    "replay_report": "report_hash",
}


class RouterStoreIntegrityError(RuntimeError):
    pass


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


class RouterStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.path = self.root / "unified_router.sqlite3"
        self.verify_schema()

    @classmethod
    def initialize(cls, root: Path) -> RouterStore:
        root = root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        path = root / "unified_router.sqlite3"
        connection = sqlite3.connect(path)
        try:
            connection.executescript(_SCHEMA)
            connection.executemany(
                "INSERT OR IGNORE INTO metadata VALUES (?, ?)",
                (
                    ("schema_version", str(ROUTER_STORE_SCHEMA_VERSION)),
                    ("created_at", utc_now()),
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return cls(root)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def verify_schema(self) -> None:
        if not self.path.is_file():
            raise RouterStoreIntegrityError("router store is missing")
        with self.connect() as connection:
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        if metadata.get("schema_version") != str(ROUTER_STORE_SCHEMA_VERSION):
            raise RouterStoreIntegrityError("router store requires explicit migration")

    def save(
        self,
        artifact_type: str,
        artifact: Any,
        *,
        artifact_id: str,
        artifact_hash: str,
        request_id: str | None,
        event_type: str,
    ) -> None:
        if artifact_type not in _ARTIFACT_HASH_FIELDS:
            raise RouterStoreIntegrityError("unsupported router artifact type")
        payload = asdict(artifact) if is_dataclass(artifact) else artifact
        payload_json = canonical_json(payload)
        created_at = str(
            payload.get("created_at", payload.get("executed_at", utc_now()))
        )
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?)",
                (
                    artifact_type,
                    artifact_id,
                    artifact_hash,
                    request_id,
                    created_at,
                    payload_json,
                ),
            )
            self._append_audit(
                connection, event_type, {"artifact_hash": artifact_hash}, artifact_id
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, artifact_type: str, artifact_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM artifacts WHERE artifact_type = ? AND artifact_id = ?",
                (artifact_type, artifact_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown {artifact_type}: {artifact_id}")
        return json.loads(row[0])

    def find_hash(self, artifact_hash: str) -> tuple[str, dict[str, Any]]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT artifact_type, payload_json FROM artifacts WHERE artifact_hash = ?",
                (artifact_hash,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown router artifact hash: {artifact_hash}")
        return str(row[0]), json.loads(row[1])

    def append_audit(
        self, event_type: str, payload: dict[str, Any], object_id: str | None = None
    ) -> str:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            digest = self._append_audit(connection, event_type, payload, object_id)
            connection.commit()
            return digest
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def audit_replay(self, object_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM audit_events"
        parameters: tuple[Any, ...] = ()
        if object_id is not None:
            sql += " WHERE object_id = ?"
            parameters = (object_id,)
        sql += " ORDER BY sequence"
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(sql, parameters)]

    @staticmethod
    def _append_audit(
        connection: sqlite3.Connection,
        event_type: str,
        payload: dict[str, Any],
        object_id: str | None,
    ) -> str:
        payload_json = canonical_json(payload)
        payload_hash = bytes_hash(payload_json.encode("utf-8"))
        previous_row = connection.execute(
            "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous = previous_row[0] if previous_row else "0" * 64
        body = {
            "event_id": f"router_audit_{uuid4().hex}",
            "event_type": event_type,
            "object_id": object_id,
            "recorded_at": utc_now(),
            "payload_hash": payload_hash,
            "previous_hash": previous,
        }
        event_hash = content_hash(body)
        connection.execute(
            "INSERT INTO audit_events(event_id,event_type,object_id,recorded_at,payload_hash,previous_hash,event_hash,payload_json) VALUES (?,?,?,?,?,?,?,?)",
            (*body.values(), event_hash, payload_json),
        )
        return event_hash

    def verify(self) -> dict[str, Any]:
        self.verify_schema()
        with self.connect() as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RouterStoreIntegrityError("router SQLite integrity failed")
            previous = "0" * 64
            count = 0
            for row in connection.execute(
                "SELECT * FROM audit_events ORDER BY sequence"
            ):
                if row["previous_hash"] != previous:
                    raise RouterStoreIntegrityError("router audit chain is broken")
                if (
                    bytes_hash(row["payload_json"].encode("utf-8"))
                    != row["payload_hash"]
                ):
                    raise RouterStoreIntegrityError("router audit payload changed")
                body = {
                    key: row[key]
                    for key in (
                        "event_id",
                        "event_type",
                        "object_id",
                        "recorded_at",
                        "payload_hash",
                        "previous_hash",
                    )
                }
                if content_hash(body) != row["event_hash"]:
                    raise RouterStoreIntegrityError("router audit hash changed")
                previous = row["event_hash"]
                count += 1
            artifacts = int(
                connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
            )
            for row in connection.execute("SELECT * FROM artifacts"):
                try:
                    hash_field = _ARTIFACT_HASH_FIELDS[row["artifact_type"]]
                    payload = json.loads(row["payload_json"])
                except (KeyError, TypeError, json.JSONDecodeError) as error:
                    raise RouterStoreIntegrityError(
                        "router artifact type or payload is invalid"
                    ) from error
                if not isinstance(payload, dict):
                    raise RouterStoreIntegrityError(
                        "router artifact payload must be an object"
                    )
                _validate_artifact_payload(row["artifact_type"], payload)
                stored_hash = payload.pop(hash_field, None)
                if (
                    stored_hash != row["artifact_hash"]
                    or content_hash(payload) != row["artifact_hash"]
                ):
                    raise RouterStoreIntegrityError(
                        f"router artifact hash mismatch: {row['artifact_type']}"
                    )
                if (
                    row["request_id"] is not None
                    and payload.get("request_id") != row["request_id"]
                ):
                    raise RouterStoreIntegrityError(
                        "router artifact request binding changed"
                    )
        return {
            "status": "VALID",
            "artifact_count": artifacts,
            "audit_event_count": count,
        }

    def backup(self, output_dir: Path) -> dict[str, Any]:
        output = output_dir.resolve()
        if output == self.root or self.root in output.parents:
            raise ValueError("backup destination must be outside router store")
        output.mkdir(parents=True, exist_ok=True)
        target = output / self.path.name
        with (
            self.connect() as source,
            sqlite3.connect(target, factory=_ClosingConnection) as destination,
        ):
            source.backup(destination)
        manifest = {
            "schema_version": ROUTER_STORE_SCHEMA_VERSION,
            "database_sha256": bytes_hash(target.read_bytes()),
            "created_at": utc_now(),
        }
        (output / "backup_manifest.json").write_text(
            canonical_json(manifest) + "\n", encoding="utf-8"
        )
        return manifest

    @classmethod
    def restore(cls, backup_dir: Path, target_dir: Path) -> RouterStore:
        backup = backup_dir.resolve()
        target = target_dir.resolve()
        if target.exists() and any(target.iterdir()):
            raise RouterStoreIntegrityError("restore target must be empty")
        manifest = json.loads(
            (backup / "backup_manifest.json").read_text(encoding="utf-8")
        )
        source = backup / "unified_router.sqlite3"
        if bytes_hash(source.read_bytes()) != manifest.get("database_sha256"):
            raise RouterStoreIntegrityError("router backup hash mismatch")
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target / source.name)
        store = cls(target)
        store.verify()
        return store


def create_router_v1_compatibility_fixture(
    v2_root: Path, v1_root: Path
) -> dict[str, Any]:
    source = RouterStore(v2_root)
    source.verify()
    target = v1_root.resolve()
    if target.exists() and any(target.iterdir()):
        raise RouterStoreIntegrityError("router v1 fixture target must be empty")
    shutil.copytree(source.root, target, dirs_exist_ok=True)
    connection = sqlite3.connect(target / "unified_router.sqlite3")
    connection.row_factory = sqlite3.Row
    try:
        connection.execute(
            "UPDATE metadata SET value = '1' WHERE key = 'schema_version'"
        )
        for row in tuple(
            connection.execute(
                "SELECT artifact_id, payload_json FROM artifacts WHERE artifact_type = 'response'"
            )
        ):
            payload = json.loads(row["payload_json"])
            for name in (
                "response_stage",
                "dependency_snapshot_hash",
                "parent_prepared_response_hash",
                "confirmation_hash",
                "stage1_execution_hash",
                "failure_artifact_hash",
                "completed_at",
                "schema_version",
                "legacy_status",
            ):
                payload.pop(name, None)
            payload.pop("response_hash")
            digest = content_hash(payload)
            payload["response_hash"] = digest
            connection.execute(
                "UPDATE artifacts SET artifact_hash = ?, payload_json = ? "
                "WHERE artifact_type = 'response' AND artifact_id = ?",
                (digest, canonical_json(payload), row["artifact_id"]),
            )
        connection.commit()
    finally:
        connection.close()
    _verify_v1_store(target)
    return _tree_manifest(target)


def migrate_router_store_v1_to_v2(
    source_root: Path, target_root: Path
) -> dict[str, Any]:
    """Publish a verified v2 copy while preserving the v1 source bytes."""
    source = source_root.resolve()
    target = target_root.resolve()
    if source == target or source in target.parents or target in source.parents:
        raise RouterStoreIntegrityError("migration source and target must be separate")
    if target.exists() and any(target.iterdir()):
        raise RouterStoreIntegrityError("migration target must be new or empty")
    source_before = _tree_manifest(source)
    _verify_v1_store(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="router-v2-migration-", dir=target.parent))
    work = staging / "router-v2"
    started = time.perf_counter()
    try:
        shutil.copytree(source, work)
        path = work / "unified_router.sqlite3"
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute(
                "UPDATE metadata SET value = ? WHERE key = 'schema_version'",
                (str(ROUTER_STORE_SCHEMA_VERSION),),
            )
            legacy_responses = 0
            for row in tuple(
                connection.execute(
                    "SELECT artifact_id, payload_json FROM artifacts WHERE artifact_type = 'response'"
                )
            ):
                payload = json.loads(row["payload_json"])
                payload["legacy_status"] = "LEGACY_INCOMPLETE_DEPENDENCY_BINDING"
                payload["schema_version"] = 1
                payload["response_stage"] = (
                    "PREPARED"
                    if payload.get("skill_selection_hash") is not None
                    or payload.get("tool_proposal_hash") is not None
                    else "COMPLETED"
                )
                payload["dependency_snapshot_hash"] = "0" * 64
                payload.setdefault("parent_prepared_response_hash", None)
                payload.setdefault("confirmation_hash", None)
                payload.setdefault("stage1_execution_hash", None)
                payload.setdefault("failure_artifact_hash", None)
                payload.setdefault("completed_at", None)
                payload["response_hash"] = ""
                body = dict(payload)
                body.pop("response_hash")
                digest = content_hash(body)
                payload["response_hash"] = digest
                connection.execute(
                    "UPDATE artifacts SET artifact_hash = ?, payload_json = ? "
                    "WHERE artifact_type = 'response' AND artifact_id = ?",
                    (digest, canonical_json(payload), row["artifact_id"]),
                )
                legacy_responses += 1
            connection.commit()
        finally:
            connection.close()
        store = RouterStore(work)
        store.append_audit(
            "ROUTER_STORE_MIGRATED_V1_TO_V2",
            {
                "source_tree_sha256": source_before["tree_sha256"],
                "legacy_incomplete_response_count": legacy_responses,
            },
        )
        integrity = store.verify()
        if _tree_manifest(source) != source_before:
            raise RouterStoreIntegrityError("router v1 source changed during migration")
        manifest_body = {
            "migration": "ROUTER_STORE_V1_TO_V2",
            "source_schema_version": 1,
            "target_schema_version": ROUTER_STORE_SCHEMA_VERSION,
            "source_tree_sha256": source_before["tree_sha256"],
            "source_database_sha256": source_before["files"].get(
                "unified_router.sqlite3"
            ),
            "target_database_sha256": bytes_hash(store.path.read_bytes()),
            "legacy_incomplete_response_count": legacy_responses,
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
        RouterStore(target).verify()
        return manifest
    except BaseException as error:
        shutil.rmtree(staging, ignore_errors=True)
        if target.exists() and not any(target.iterdir()):
            target.rmdir()
        if _tree_manifest(source) != source_before:
            raise RouterStoreIntegrityError(
                "migration failed and source preservation could not be proven"
            ) from error
        if isinstance(error, RouterStoreIntegrityError):
            raise
        raise RouterStoreIntegrityError(
            "router v1 migration failed; source was left untouched"
        ) from error


def _validate_artifact_payload(artifact_type: str, payload: dict[str, Any]) -> None:
    from dataclasses import fields

    from ai_brain.stage2.router.models import (
        ClarificationRequest,
        ReplayReport,
        RequestEnvelope,
        ResponseStage,
        RouteDecision,
        RouteReceipt,
        RouterFailureArtifact,
        ToolCallConfirmation,
        ToolCallProposal,
        ToolImplementationManifest,
        ToolResultBundle,
        UnifiedResponseEnvelope,
    )
    from ai_brain.stage2.router.version import (
        TOOL_CALL_SCHEMA_VERSION,
        UNIFIED_RESPONSE_SCHEMA_VERSION,
    )

    if artifact_type == "response":
        legacy = payload.get("legacy_status") == "LEGACY_INCOMPLETE_DEPENDENCY_BINDING"
        if legacy:
            if payload.get("schema_version") != 1:
                raise RouterStoreIntegrityError("legacy response schema is invalid")
            return
        if payload.get("schema_version") != UNIFIED_RESPONSE_SCHEMA_VERSION:
            raise RouterStoreIntegrityError("response schema is incompatible")
        try:
            ResponseStage(payload["response_stage"])
        except (KeyError, ValueError) as error:
            raise RouterStoreIntegrityError("response stage is invalid") from error
        if not _is_sha256(payload.get("dependency_snapshot_hash")):
            raise RouterStoreIntegrityError("response dependency hash is invalid")
    elif artifact_type in {"tool_proposal", "tool_confirmation", "tool_result"}:
        if payload.get("schema_version") != TOOL_CALL_SCHEMA_VERSION:
            raise RouterStoreIntegrityError("tool-call schema is incompatible")
        for name in (
            "dependency_snapshot_hash",
            "tool_implementation_manifest_hash",
        ):
            if not _is_sha256(payload.get(name)):
                raise RouterStoreIntegrityError(f"tool artifact {name} is invalid")
    classes = {
        "request": RequestEnvelope,
        "route_decision": RouteDecision,
        "route_receipt": RouteReceipt,
        "clarification": ClarificationRequest,
        "tool_proposal": ToolCallProposal,
        "tool_confirmation": ToolCallConfirmation,
        "tool_result": ToolResultBundle,
        "tool_manifest": ToolImplementationManifest,
        "response": UnifiedResponseEnvelope,
        "failure": RouterFailureArtifact,
        "replay_report": ReplayReport,
    }
    artifact_class = classes[artifact_type]
    current = (
        artifact_type in {"clarification", "tool_manifest", "failure", "replay_report"}
        or payload.get("schema_version")
        in {
            UNIFIED_RESPONSE_SCHEMA_VERSION,
            TOOL_CALL_SCHEMA_VERSION,
            2,
        }
        or (
            artifact_type == "route_decision"
            and payload.get("dependencies", {}).get("unified_router_schema_version")
            == 2
        )
    )
    if current:
        expected = {item.name for item in fields(artifact_class)}
        if set(payload) != expected:
            raise RouterStoreIntegrityError(
                f"{artifact_type} has an inexact trusted schema"
            )


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(item in "0123456789abcdef" for item in value)
    )


def _verify_v1_store(root: Path) -> None:
    path = root / "unified_router.sqlite3"
    if not path.is_file():
        raise RouterStoreIntegrityError("router v1 database is missing")
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        if metadata.get("schema_version") != "1":
            raise RouterStoreIntegrityError("migration requires router schema v1")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RouterStoreIntegrityError("router v1 SQLite integrity failed")
        previous = "0" * 64
        for row in connection.execute("SELECT * FROM audit_events ORDER BY sequence"):
            if row["previous_hash"] != previous:
                raise RouterStoreIntegrityError("router v1 audit chain is broken")
            if bytes_hash(row["payload_json"].encode("utf-8")) != row["payload_hash"]:
                raise RouterStoreIntegrityError("router v1 audit payload changed")
            body = {
                key: row[key]
                for key in (
                    "event_id",
                    "event_type",
                    "object_id",
                    "recorded_at",
                    "payload_hash",
                    "previous_hash",
                )
            }
            if content_hash(body) != row["event_hash"]:
                raise RouterStoreIntegrityError("router v1 audit hash changed")
            previous = row["event_hash"]
        for row in connection.execute("SELECT * FROM artifacts"):
            try:
                hash_field = _ARTIFACT_HASH_FIELDS[row["artifact_type"]]
                payload = json.loads(row["payload_json"])
            except (KeyError, TypeError, json.JSONDecodeError) as error:
                raise RouterStoreIntegrityError(
                    "router v1 artifact is invalid"
                ) from error
            stored = payload.pop(hash_field, None)
            if stored != row["artifact_hash"] or content_hash(payload) != stored:
                raise RouterStoreIntegrityError("router v1 artifact hash mismatch")
    finally:
        connection.close()


def _tree_manifest(root: Path) -> dict[str, Any]:
    files = {
        item.relative_to(root).as_posix(): bytes_hash(item.read_bytes())
        for item in sorted(root.rglob("*"))
        if item.is_file()
    }
    return {"files": files, "tree_sha256": content_hash(files)}
