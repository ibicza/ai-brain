"""Checksummed transactional storage for educational artifacts and sessions."""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from ai_brain.stage2.education.serialization import event_from_dict, session_from_dict
from ai_brain.stage2.education.sessions import verify_session_hash
from ai_brain.stage2.education.version import SESSION_STORE_SCHEMA_VERSION
from ai_brain.stage2.facts.canonical import (
    bytes_hash,
    canonical_json,
    content_hash,
    utc_now,
)


class EducationalStoreIntegrityError(ValueError):
    pass


class EducationalSessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.database_path = self.root / "educational_sessions.sqlite3"

    @classmethod
    def initialize(cls, root: Path) -> EducationalSessionStore:
        store = cls(root)
        store.root.mkdir(parents=True, exist_ok=True)
        if store.database_path.exists():
            raise FileExistsError("educational session store already exists")
        with store._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE artifacts(
                    artifact_hash TEXT PRIMARY KEY,
                    artifact_kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE sessions(
                    session_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    session_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE events(
                    session_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    event_hash TEXT NOT NULL UNIQUE,
                    previous_event_hash TEXT,
                    payload TEXT NOT NULL,
                    PRIMARY KEY(session_id, sequence),
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );
                """
            )
            connection.execute(
                "INSERT INTO metadata(key,value) VALUES('schema_version',?)",
                (str(SESSION_STORE_SCHEMA_VERSION),),
            )
            connection.execute(
                "INSERT INTO metadata(key,value) VALUES('created_at',?)", (utc_now(),)
            )
        return store

    @classmethod
    def open(cls, root: Path) -> EducationalSessionStore:
        store = cls(root)
        if not store.database_path.is_file():
            raise FileNotFoundError("educational session database is missing")
        with store._connection() as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
        if row is None or row[0] != str(SESSION_STORE_SCHEMA_VERSION):
            raise EducationalStoreIntegrityError(
                "educational store requires an explicit rebuild"
            )
        return store

    @classmethod
    def open_or_initialize(cls, root: Path) -> EducationalSessionStore:
        path = root.resolve() / "educational_sessions.sqlite3"
        return cls.open(root) if path.exists() else cls.initialize(root)

    def save_artifact(self, kind: str, artifact_hash: str, value: Any) -> None:
        if not kind or not _is_hash(artifact_hash):
            raise ValueError("invalid educational artifact identity")
        payload = canonical_json(asdict(value) if is_dataclass(value) else value)
        digest = bytes_hash(payload.encode("utf-8"))
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT artifact_kind,payload,payload_hash FROM artifacts WHERE artifact_hash=?",
                (artifact_hash,),
            ).fetchone()
            if existing is not None:
                if existing != (kind, payload, digest):
                    raise EducationalStoreIntegrityError(
                        "immutable educational artifact collision"
                    )
                return
            connection.execute(
                "INSERT INTO artifacts VALUES(?,?,?,?,?)",
                (artifact_hash, kind, payload, digest, utc_now()),
            )

    def get_artifact(self, artifact_hash: str, *, expected_kind: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT artifact_kind,payload,payload_hash FROM artifacts WHERE artifact_hash=?",
                (artifact_hash,),
            ).fetchone()
        if row is None or row[0] != expected_kind:
            raise KeyError("educational artifact is missing or has the wrong kind")
        if bytes_hash(row[1].encode("utf-8")) != row[2]:
            raise EducationalStoreIntegrityError(
                "educational artifact checksum mismatch"
            )
        value = json.loads(row[1])
        if not isinstance(value, dict):
            raise EducationalStoreIntegrityError(
                "educational artifact payload is not an object"
            )
        return value

    def create_session(self, session: Any, presented_event: Any) -> None:
        session_payload = canonical_json(asdict(session))
        event_payload = canonical_json(asdict(presented_event))
        with self._connection() as connection:
            if connection.execute(
                "SELECT 1 FROM sessions WHERE session_id=?", (session.session_id,)
            ).fetchone():
                raise ValueError("tutor session already exists")
            connection.execute(
                "INSERT INTO sessions VALUES(?,?,?,?)",
                (
                    session.session_id,
                    session_payload,
                    session.session_hash,
                    session.updated_at,
                ),
            )
            connection.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?)",
                (
                    presented_event.session_id,
                    presented_event.sequence,
                    presented_event.event_id,
                    presented_event.event_hash,
                    presented_event.previous_event_hash,
                    event_payload,
                ),
            )

    def append_event(self, old_session: Any, new_session: Any, event: Any) -> None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT session_hash FROM sessions WHERE session_id=?",
                (old_session.session_id,),
            ).fetchone()
            if row is None or row[0] != old_session.session_hash:
                raise EducationalStoreIntegrityError("stale tutor session update")
            expected_sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE session_id=?",
                (old_session.session_id,),
            ).fetchone()[0]
            if event.sequence != expected_sequence:
                raise EducationalStoreIntegrityError("tutor event sequence mismatch")
            connection.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?)",
                (
                    event.session_id,
                    event.sequence,
                    event.event_id,
                    event.event_hash,
                    event.previous_event_hash,
                    canonical_json(asdict(event)),
                ),
            )
            updated = connection.execute(
                "UPDATE sessions SET payload=?,session_hash=?,updated_at=? WHERE session_id=? AND session_hash=?",
                (
                    canonical_json(asdict(new_session)),
                    new_session.session_hash,
                    new_session.updated_at,
                    new_session.session_id,
                    old_session.session_hash,
                ),
            )
            if updated.rowcount != 1:
                raise EducationalStoreIntegrityError(
                    "atomic tutor session update failed"
                )

    def get_session(self, session_id: str):
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload,session_hash FROM sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError("unknown tutor session")
        payload = json.loads(row[0])
        session = session_from_dict(payload)
        if session.session_hash != row[1]:
            raise EducationalStoreIntegrityError("stored tutor session hash mismatch")
        verify_session_hash(session)
        return session

    def events(self, session_id: str):
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM events WHERE session_id=? ORDER BY sequence",
                (session_id,),
            ).fetchall()
        return tuple(event_from_dict(json.loads(row[0])) for row in rows)

    def verify(self) -> dict[str, Any]:
        with self._connection() as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            artifacts = connection.execute(
                "SELECT artifact_hash,payload,payload_hash FROM artifacts"
            ).fetchall()
            sessions = connection.execute("SELECT session_id FROM sessions").fetchall()
        if integrity != "ok":
            raise EducationalStoreIntegrityError("SQLite integrity check failed")
        for _, payload, digest in artifacts:
            if bytes_hash(payload.encode("utf-8")) != digest:
                raise EducationalStoreIntegrityError("artifact checksum mismatch")
        event_count = 0
        for (session_id,) in sessions:
            session = self.get_session(session_id)
            events = self.events(session_id)
            previous = None
            for sequence, event in enumerate(events, start=1):
                body = asdict(event)
                digest = body.pop("event_hash")
                if (
                    event.sequence != sequence
                    or event.previous_event_hash != previous
                    or content_hash(body) != digest
                ):
                    raise EducationalStoreIntegrityError("tutor event chain is invalid")
                previous = event.event_hash
            if not events or previous != session.last_event_hash:
                raise EducationalStoreIntegrityError("session/event head mismatch")
            event_count += len(events)
        return {
            "status": "VERIFIED",
            "artifact_count": len(artifacts),
            "session_count": len(sessions),
            "event_count": event_count,
            "schema_version": SESSION_STORE_SCHEMA_VERSION,
        }

    def backup(self, target: Path) -> dict[str, Any]:
        resolved = target.resolve()
        if resolved.exists():
            raise FileExistsError("educational backup target must be absent")
        resolved.mkdir(parents=True)
        backup_db = resolved / self.database_path.name
        source = self._connect()
        destination = sqlite3.connect(backup_db)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        payload = backup_db.read_bytes()
        manifest = {
            "schema_version": SESSION_STORE_SCHEMA_VERSION,
            "database_file": backup_db.name,
            "database_sha256": bytes_hash(payload),
            "created_at": utc_now(),
        }
        (resolved / "backup_manifest.json").write_text(
            canonical_json(manifest) + "\n", encoding="utf-8"
        )
        return manifest

    @classmethod
    def restore(cls, backup: Path, target: Path) -> EducationalSessionStore:
        source = backup.resolve()
        destination = target.resolve()
        if destination.exists():
            raise FileExistsError("educational restore target must be absent")
        manifest = json.loads(
            (source / "backup_manifest.json").read_text(encoding="utf-8")
        )
        database = source / manifest["database_file"]
        if bytes_hash(database.read_bytes()) != manifest["database_sha256"]:
            raise EducationalStoreIntegrityError("educational backup checksum mismatch")
        destination.mkdir(parents=True)
        shutil.copy2(database, destination / "educational_sessions.sqlite3")
        restored = cls.open(destination)
        restored.verify()
        return restored

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()


def _is_hash(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
