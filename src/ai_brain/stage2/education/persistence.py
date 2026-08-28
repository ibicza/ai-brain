"""Checksummed transactional storage for educational artifacts and sessions."""

from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from ai_brain.stage2.education.artifact_registry import reconstruct_and_validate
from ai_brain.stage2.education.serialization import event_from_dict, session_from_dict
from ai_brain.stage2.education.sessions import (
    apply_event,
    verify_event_hash,
    verify_session_hash,
)
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
        typed = reconstruct_and_validate(kind, artifact_hash, value)
        payload = canonical_json(asdict(typed) if is_dataclass(typed) else typed)
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

    def get_artifact(self, artifact_hash: str, *, expected_kind: str) -> Any:
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
        try:
            return reconstruct_and_validate(expected_kind, artifact_hash, value)
        except (TypeError, ValueError) as error:
            raise EducationalStoreIntegrityError(str(error)) from error

    def create_session(self, session: Any, presented_event: Any) -> None:
        verify_session_hash(session)
        verify_event_hash(presented_event)
        if (
            presented_event.event_type != "SESSION_PRESENTED"
            or presented_event.sequence != 1
            or presented_event.previous_event_hash is not None
            or presented_event.event_hash != session.last_event_hash
        ):
            raise EducationalStoreIntegrityError("invalid session presentation event")
        self.get_artifact(
            session.exercise_hash, expected_kind="exercise_instance_internal"
        )
        self.get_artifact(session.graph_hash, expected_kind="derivation_graph")
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
        verify_session_hash(old_session)
        verify_session_hash(new_session)
        verify_event_hash(event)
        if apply_event(old_session, event) != new_session:
            raise EducationalStoreIntegrityError("event/session transition mismatch")
        self._verify_event_artifacts(old_session, event)
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

    def session_ids(self) -> tuple[str, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT session_id FROM sessions ORDER BY session_id"
            ).fetchall()
        return tuple(row[0] for row in rows)

    def artifacts(self, kind: str) -> tuple[Any, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT artifact_hash,payload,payload_hash FROM artifacts "
                "WHERE artifact_kind=? ORDER BY artifact_hash",
                (kind,),
            ).fetchall()
        values = []
        for artifact_hash, payload, payload_hash in rows:
            if bytes_hash(payload.encode("utf-8")) != payload_hash:
                raise EducationalStoreIntegrityError(
                    "educational artifact checksum mismatch"
                )
            values.append(
                reconstruct_and_validate(kind, artifact_hash, json.loads(payload))
            )
        return tuple(values)

    def verify(self) -> dict[str, Any]:
        with self._connection() as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            artifacts = connection.execute(
                "SELECT artifact_hash,artifact_kind,payload,payload_hash FROM artifacts"
            ).fetchall()
            sessions = connection.execute("SELECT session_id FROM sessions").fetchall()
        if integrity != "ok":
            raise EducationalStoreIntegrityError("SQLite integrity check failed")
        artifact_index: dict[tuple[str, str], Any] = {}
        for artifact_hash, kind, payload, digest in artifacts:
            if bytes_hash(payload.encode("utf-8")) != digest:
                raise EducationalStoreIntegrityError("artifact checksum mismatch")
            try:
                typed = reconstruct_and_validate(
                    kind, artifact_hash, json.loads(payload)
                )
            except (TypeError, ValueError) as error:
                raise EducationalStoreIntegrityError(str(error)) from error
            artifact_index[(artifact_hash, kind)] = typed
        self._verify_cross_artifact_relations(artifact_index)
        event_count = 0
        for (session_id,) in sessions:
            session = self.get_session(session_id)
            events = self.events(session_id)
            previous = None
            rebuilt = None
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
                if sequence == 1:
                    if (
                        event.event_type != "SESSION_PRESENTED"
                        or event.payload.get("exercise_id") != session.exercise_id
                        or event.payload.get("exercise_hash") != session.exercise_hash
                    ):
                        raise EducationalStoreIntegrityError(
                            "session does not start with presentation"
                        )
                    rebuilt = session_from_dict(
                        {
                            **asdict(session),
                            "attempt_hashes": [],
                            "grading_result_hashes": [],
                            "hint_hashes": [],
                            "status": "PRESENTED",
                            "updated_at": event.created_at,
                            "last_event_hash": event.event_hash,
                            "session_hash": "",
                        }
                    )
                    body = asdict(rebuilt)
                    body.pop("session_hash")
                    rebuilt = session_from_dict(
                        {**body, "session_hash": content_hash(body)}
                    )
                else:
                    assert rebuilt is not None
                    self._verify_event_artifacts(rebuilt, event)
                    rebuilt = apply_event(rebuilt, event)
            if not events or previous != session.last_event_hash:
                raise EducationalStoreIntegrityError("session/event head mismatch")
            if rebuilt != session:
                raise EducationalStoreIntegrityError("event/session replay mismatch")
            event_count += len(events)
        return {
            "status": "STRUCTURALLY_VERIFIED",
            "artifact_count": len(artifacts),
            "session_count": len(sessions),
            "event_count": event_count,
            "schema_version": SESSION_STORE_SCHEMA_VERSION,
        }

    def _verify_event_artifacts(self, session: Any, event: Any) -> None:
        if event.event_type == "ANSWER_SUBMITTED":
            self.get_artifact(
                event.payload.get("student_answer_hash", ""),
                expected_kind="student_answer",
            )
        elif event.event_type == "ANSWER_GRADED":
            grade = self.get_artifact(
                event.payload.get("grading_result_hash", ""),
                expected_kind="grading_result",
            )
            if grade.exercise_id != session.exercise_id or not session.attempt_hashes:
                raise EducationalStoreIntegrityError(
                    "grading event references another attempt/exercise"
                )
            if grade.student_answer_hash != session.attempt_hashes[-1]:
                raise EducationalStoreIntegrityError(
                    "grading event references another student answer"
                )
            check = self.get_artifact(
                event.payload.get("check_explanation_hash", ""),
                expected_kind="explanation",
            )
            if check.grading_result_hash != grade.result_hash:
                raise EducationalStoreIntegrityError(
                    "grading event references another check explanation"
                )
        elif event.event_type == "HINT_ISSUED":
            hint = self.get_artifact(
                event.payload.get("hint_hash", ""), expected_kind="hint"
            )
            if (
                hint.exercise_id != session.exercise_id
                or hint.graph_hash != session.graph_hash
            ):
                raise EducationalStoreIntegrityError(
                    "hint event references another exercise/graph"
                )
        elif event.event_type == "SOLUTION_REVEALED":
            explanation = self.get_artifact(
                event.payload.get("explanation_hash", ""),
                expected_kind="explanation",
            )
            if explanation.graph_hash != session.graph_hash:
                raise EducationalStoreIntegrityError(
                    "solution event references another graph"
                )

    def _verify_cross_artifact_relations(
        self, artifacts: dict[tuple[str, str], Any]
    ) -> None:
        from ai_brain.stage2.education.exercise_generation import (
            verify_exercise_instance,
            verify_presented_exercise,
            verify_presented_exercise_binding,
        )
        from ai_brain.stage2.education.explanations import (
            verify_explanation,
            verify_explanation_plan,
        )
        from ai_brain.stage2.education.hints import render_hint

        internal_instances = {
            value.instance_id: value
            for (digest, kind), value in artifacts.items()
            if kind == "exercise_instance_internal"
        }
        graphs = {
            digest: value
            for (digest, kind), value in artifacts.items()
            if kind == "derivation_graph"
        }
        for instance in internal_instances.values():
            try:
                spec = artifacts[(instance.exercise_spec_hash, "exercise_spec")]
                graph = graphs[instance.hidden_answer_graph_hash]
                receipt = artifacts[
                    (instance.compilation_receipt_hash, "compilation_receipt")
                ]
                source = artifacts[(graph.source_result_hash, "source_result")]
            except KeyError as error:
                raise EducationalStoreIntegrityError(
                    "orphaned internal exercise artifact reference"
                ) from error
            verify_exercise_instance(instance, spec, graph)
            if (
                receipt.educational_graph_hash != graph.graph_hash
                or receipt.exact_result_hash != graph.source_result_hash
                or canonical_json(source)
                != canonical_json(graph.source_result_artifact)
            ):
                raise EducationalStoreIntegrityError(
                    "exercise compilation/source relation mismatch"
                )
        for (_, kind), value in artifacts.items():
            if kind == "presented_exercise":
                verify_presented_exercise(value)
                instance = internal_instances.get(value.exercise_id)
                if instance is None:
                    raise EducationalStoreIntegrityError(
                        "presented exercise references no internal exercise"
                    )
                try:
                    spec = artifacts[(instance.exercise_spec_hash, "exercise_spec")]
                    verify_presented_exercise_binding(
                        value, instance, spec, session_id=value.session_id
                    )
                except (KeyError, ValueError) as error:
                    raise EducationalStoreIntegrityError(
                        "presented exercise semantic binding mismatch"
                    ) from error
            elif kind == "explanation_plan":
                try:
                    verify_explanation_plan(value, graphs[value.graph_hash])
                except KeyError as error:
                    raise EducationalStoreIntegrityError(
                        "explanation plan references a missing graph"
                    ) from error
            elif kind == "explanation":
                graph = graphs.get(value.graph_hash)
                if graph is None:
                    raise EducationalStoreIntegrityError(
                        "explanation references a missing graph"
                    )
                if value.mode.value == "CHECK_ONLY":
                    grading = artifacts.get(
                        (value.grading_result_hash, "grading_result")
                    )
                    if grading is None:
                        raise EducationalStoreIntegrityError(
                            "CHECK_ONLY explanation references a missing grade"
                        )
                    verify_explanation(value, graph, grading=grading)
                elif value.mode.value != "HINT_ONLY":
                    plan = artifacts.get((value.plan_hash, "explanation_plan"))
                    if plan is None:
                        raise EducationalStoreIntegrityError(
                            "explanation references a missing plan"
                        )
                    verify_explanation(
                        value,
                        graph,
                        plan=plan,
                        session_id=value.session_id,
                        session_state_hash=value.session_state_hash,
                    )
            elif kind == "grading_result":
                instance = internal_instances.get(value.exercise_id)
                if (
                    instance is None
                    or value.exercise_hash != instance.instance_hash
                    or (value.student_answer_hash, "student_answer") not in artifacts
                    or value.answer_graph_hash != instance.hidden_answer_graph_hash
                ):
                    raise EducationalStoreIntegrityError(
                        "grading result cross-artifact relation mismatch"
                    )
            elif kind == "hint":
                instance = internal_instances.get(value.exercise_id)
                if (
                    instance is None
                    or value.graph_hash != instance.hidden_answer_graph_hash
                ):
                    raise EducationalStoreIntegrityError(
                        "hint cross-artifact relation mismatch"
                    )
                plan = artifacts.get((value.plan_hash, "hint_plan"))
                grading = (
                    artifacts.get((value.grading_result_hash, "grading_result"))
                    if value.grading_result_hash
                    else None
                )
                if plan is None or render_hint(
                    plan,
                    graphs[value.graph_hash],
                    value.level,
                    language=value.language,
                    grading=grading,
                ) != value:
                    raise EducationalStoreIntegrityError(
                        "hint semantic binding mismatch"
                    )

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
