"""Append-only generic records inside the trusted Stage-2 SQLite stores."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, is_dataclass

from ai_brain.stage2.facts.canonical import (
    bytes_hash,
    canonical_json,
    content_hash,
    utc_now,
)

_TABLE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


class GenericPersistentLedger:
    def __init__(self, store, table: str) -> None:
        if not _TABLE.fullmatch(table):
            raise ValueError("unsafe generic ledger table")
        self.store = store
        self.database_path = store.database_path
        self.table = table
        with self._connection() as connection:
            connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {table}(
                record_id TEXT PRIMARY KEY,
                operation_id TEXT NOT NULL,
                record_kind TEXT NOT NULL,
                payload TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                record_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS {table}_operation ON {table}(operation_id)"
            )

    def put(self, record_id: str, operation_id: str, kind: str, payload) -> str:
        if not record_id or not operation_id or not kind:
            raise ValueError("generic persistent record identity is incomplete")
        if is_dataclass(payload):
            payload = asdict(payload)
        serialized = canonical_json(payload)
        body = {
            "record_id": record_id,
            "operation_id": operation_id,
            "record_kind": kind,
            "payload_hash": bytes_hash(serialized.encode("utf-8")),
        }
        record_hash = content_hash(body)
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT operation_id,record_kind,payload,payload_hash,record_hash FROM {self.table} WHERE record_id=?",
                (record_id,),
            ).fetchone()
            expected = (
                operation_id,
                kind,
                serialized,
                body["payload_hash"],
                record_hash,
            )
            if row is not None:
                if row != expected:
                    raise ValueError("immutable generic persistent record collision")
                return record_hash
            connection.execute(
                f"INSERT INTO {self.table} VALUES(?,?,?,?,?,?,?)",
                (
                    record_id,
                    operation_id,
                    kind,
                    serialized,
                    body["payload_hash"],
                    record_hash,
                    utc_now(),
                ),
            )
        return record_hash

    def get(self, record_id: str) -> tuple[str, str, dict, str]:
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT operation_id,record_kind,payload,payload_hash,record_hash FROM {self.table} WHERE record_id=?",
                (record_id,),
            ).fetchone()
        if row is None or bytes_hash(row[2].encode("utf-8")) != row[3]:
            raise KeyError("unknown or corrupt generic persistent record")
        return row[0], row[1], json.loads(row[2]), row[4]

    def records(
        self, *, kind: str | None = None
    ) -> tuple[tuple[str, str, dict, str], ...]:
        query = f"SELECT record_id,record_kind,payload,payload_hash,record_hash FROM {self.table}"
        parameters = ()
        if kind is not None:
            query += " WHERE record_kind=?"
            parameters = (kind,)
        query += " ORDER BY created_at,record_id"
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        result = []
        for record_id, record_kind, payload, digest, record_hash in rows:
            if bytes_hash(payload.encode("utf-8")) != digest:
                raise ValueError("generic persistent ledger checksum mismatch")
            result.append((record_id, record_kind, json.loads(payload), record_hash))
        return tuple(result)

    def inspect_operation(self, operation_id: str) -> tuple[str, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT record_hash FROM {self.table} WHERE operation_id=? ORDER BY record_id",
                (operation_id,),
            ).fetchall()
        return tuple(row[0] for row in rows)

    def verify(self) -> dict[str, object]:
        with self._connection() as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("generic persistent ledger SQLite integrity failed")
        rows = self.records()
        return {"status": "VERIFIED", "record_count": len(rows)}

    def _connection(self):
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        connection.execute("PRAGMA busy_timeout=5000")
        return connection
