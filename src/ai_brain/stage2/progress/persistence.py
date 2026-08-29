"""Separate transactional checksummed SQLite progress store."""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Callable
from contextlib import closing, contextmanager
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, utc_now
from ai_brain.stage2.progress.events import verify_progress_event
from ai_brain.stage2.progress.models import ProgressEvent, ProgressEventKind
from ai_brain.stage2.progress.projection import project_progress
from ai_brain.stage2.progress.version import LEARNER_PROGRESS_SCHEMA_VERSION


class LearnerProgressStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.database_path = self.root / "learner_progress.sqlite3"
        self.authority_check: Callable[[ProgressEvent], None] | None = None

    @classmethod
    def initialize(cls, root: Path) -> LearnerProgressStore:
        store = cls(root)
        store.root.mkdir(parents=True, exist_ok=True)
        if store.database_path.exists():
            raise FileExistsError("learner progress store already exists")
        with store._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE events(
                    learner_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                    event_id TEXT NOT NULL UNIQUE, event_hash TEXT NOT NULL UNIQUE,
                    previous_event_hash TEXT, payload TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    PRIMARY KEY(learner_id, sequence)
                );
                """
            )
            connection.executemany(
                "INSERT INTO metadata(key,value) VALUES(?,?)",
                (
                    ("schema_version", str(LEARNER_PROGRESS_SCHEMA_VERSION)),
                    ("created_at", utc_now()),
                ),
            )
        return store

    @classmethod
    def open(cls, root: Path) -> LearnerProgressStore:
        store = cls(root)
        if not store.database_path.is_file():
            raise FileNotFoundError("learner progress database is missing")
        with store._connection() as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
        if row is None or row[0] not in {"1", str(LEARNER_PROGRESS_SCHEMA_VERSION)}:
            raise ValueError("learner progress store requires an explicit rebuild")
        return store

    @classmethod
    def open_or_initialize(cls, root: Path) -> LearnerProgressStore:
        return (
            cls.open(root)
            if (root.resolve() / "learner_progress.sqlite3").exists()
            else cls.initialize(root)
        )

    def append(
        self,
        event: ProgressEvent,
        *,
        authority_check: Callable[[ProgressEvent], None] | None = None,
    ) -> None:
        verify_progress_event(event)
        with self._connection() as connection:
            schema = connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
        if schema is None or schema[0] != str(LEARNER_PROGRESS_SCHEMA_VERSION):
            raise ValueError("legacy progress history is read-only")
        if not event.trusted_current and event.event_kind in {
            ProgressEventKind.ANSWER_GRADED,
            ProgressEventKind.EXERCISE_SOLVED,
            ProgressEventKind.CONCEPT_DEMONSTRATED,
        }:
            raise ValueError("new progress cannot derive from stale authority")
        checker = authority_check or self.authority_check
        if checker is not None:
            checker(event)
        payload = canonical_json(asdict(event))
        with self._connection() as connection:
            row = connection.execute(
                "SELECT sequence,event_hash FROM events WHERE learner_id=? ORDER BY sequence DESC LIMIT 1",
                (event.learner_id,),
            ).fetchone()
            expected_sequence, previous = (
                (1, None) if row is None else (row[0] + 1, row[1])
            )
            if (
                event.sequence != expected_sequence
                or event.previous_event_hash != previous
            ):
                raise ValueError("progress event does not extend the learner chain")
            connection.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?,?)",
                (
                    event.learner_id,
                    event.sequence,
                    event.event_id,
                    event.event_hash,
                    event.previous_event_hash,
                    payload,
                    bytes_hash(payload.encode("utf-8")),
                ),
            )

    def events(self, learner_id: str) -> tuple[ProgressEvent, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload,payload_hash FROM events WHERE learner_id=? ORDER BY sequence",
                (learner_id,),
            ).fetchall()
        result = []
        for payload, checksum in rows:
            if bytes_hash(payload.encode("utf-8")) != checksum:
                raise ValueError("progress event checksum mismatch")
            row = json.loads(payload)
            row["concept_ids"] = tuple(row["concept_ids"])
            row["authority_hashes"] = tuple(row.get("authority_hashes", ()))
            row["operation_id"] = row.get("operation_id")
            row["event_kind"] = ProgressEventKind(row["event_kind"])
            result.append(ProgressEvent(**row))
        return tuple(result)

    def learner_ids(self) -> tuple[str, ...]:
        with self._connection() as connection:
            return tuple(
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT learner_id FROM events ORDER BY learner_id"
                )
            )

    def verify(
        self,
        *,
        authority_check: Callable[[ProgressEvent], None] | None = None,
        structural_only: bool = False,
    ) -> dict[str, object]:
        checker = None if structural_only else (authority_check or self.authority_check)
        count = 0
        for learner_id in self.learner_ids():
            events = self.events(learner_id)
            for event in events:
                if (
                    checker is not None
                    and event.event_kind is not ProgressEventKind.PROGRESS_RESET
                ):
                    checker(event)
            project_progress(learner_id, events)
            count += len(events)
        return {
            "status": "STRUCTURALLY_VERIFIED"
            if checker is None
            else "AUTHORITY_VERIFIED",
            "learner_count": len(self.learner_ids()),
            "event_count": count,
        }

    def export(self, learner_id: str) -> str:
        return (
            canonical_json(
                {
                    "schema_version": LEARNER_PROGRESS_SCHEMA_VERSION,
                    "learner_id": learner_id,
                    "events": [asdict(event) for event in self.events(learner_id)],
                }
            )
            + "\n"
        )

    def delete_learner(self, learner_id: str) -> int:
        if not learner_id:
            raise ValueError("explicit learner identity is required")
        with self._connection() as connection:
            deleted = connection.execute(
                "DELETE FROM events WHERE learner_id=?", (learner_id,)
            ).rowcount
        return deleted

    def backup(self, output: Path) -> dict[str, object]:
        verification = self.verify(structural_only=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as source, closing(sqlite3.connect(output)) as target:
            source.backup(target)
        digest = bytes_hash(output.read_bytes())
        return {
            **verification,
            "status": "BACKED_UP",
            "history_verification": verification["status"],
            "bytes_hash": digest,
            "event_count": sum(len(self.events(item)) for item in self.learner_ids()),
        }

    @classmethod
    def restore(cls, backup: Path, target_root: Path) -> LearnerProgressStore:
        target_root.mkdir(parents=True, exist_ok=True)
        target = target_root / "learner_progress.sqlite3"
        if target.exists():
            raise FileExistsError("progress restore target already exists")
        shutil.copyfile(backup, target)
        result = cls.open(target_root)
        result.verify(structural_only=True)
        return result

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            with connection:
                yield connection
        finally:
            connection.close()
