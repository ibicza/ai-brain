"""Checksummed transactional persistence for unified routing artifacts."""

from __future__ import annotations

import json
import shutil
import sqlite3
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
    "response": "response_hash",
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
