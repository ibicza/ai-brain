"""Durable cross-store tutor operation journal and recovery audit."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path

from ai_brain.stage2.facts.canonical import (
    bytes_hash,
    canonical_json,
    content_hash,
    utc_now,
)


class TutorOperationStatus(StrEnum):
    PREPARED = "PREPARED"
    EDUCATION_APPLIED = "EDUCATION_APPLIED"
    PROGRESS_APPLIED = "PROGRESS_APPLIED"
    CONVERSATION_COMMITTED = "CONVERSATION_COMMITTED"
    COMPLETED = "COMPLETED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class TutorOperation:
    operation_id: str
    idempotency_key: str
    learner_id: str
    conversation_id: str
    intent: str
    input_hash: str
    expected_educational_side_effects: tuple[str, ...]
    expected_progress_side_effects: tuple[str, ...]
    expected_conversation_result: str
    status: TutorOperationStatus
    step_receipts: tuple[tuple[str, str], ...]
    created_at: str
    updated_at: str
    operation_hash: str


@dataclass(frozen=True)
class StoreStageReceipt:
    operation_id: str
    stage: TutorOperationStatus
    store_id: str
    committed_record_hashes: tuple[str, ...]
    committed_at: str
    receipt_hash: str


_NEXT = {
    TutorOperationStatus.PREPARED: TutorOperationStatus.EDUCATION_APPLIED,
    TutorOperationStatus.EDUCATION_APPLIED: TutorOperationStatus.PROGRESS_APPLIED,
    TutorOperationStatus.PROGRESS_APPLIED: TutorOperationStatus.CONVERSATION_COMMITTED,
    TutorOperationStatus.CONVERSATION_COMMITTED: TutorOperationStatus.COMPLETED,
}


class TutorOperationJournal:
    def __init__(
        self,
        root: Path,
        *,
        crash_injector: Callable[[str, TutorOperation], None] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.database_path = self.root / "tutor_operations.sqlite3"
        self.crash_injector = crash_injector

    @classmethod
    def open_or_initialize(cls, root: Path) -> TutorOperationJournal:
        value = cls(root)
        value.root.mkdir(parents=True, exist_ok=True)
        if not value.database_path.exists():
            with value._connection() as c:
                c.executescript(
                    """CREATE TABLE operations(operation_id TEXT PRIMARY KEY,idempotency_key TEXT UNIQUE NOT NULL,payload TEXT NOT NULL,payload_hash TEXT NOT NULL,status TEXT NOT NULL); CREATE TABLE audit(sequence INTEGER PRIMARY KEY AUTOINCREMENT,operation_id TEXT NOT NULL,status TEXT NOT NULL,receipt_hash TEXT NOT NULL,created_at TEXT NOT NULL); CREATE TABLE stage_receipts(receipt_hash TEXT PRIMARY KEY,operation_id TEXT NOT NULL,stage TEXT NOT NULL,store_id TEXT NOT NULL,payload TEXT NOT NULL,payload_hash TEXT NOT NULL,UNIQUE(operation_id,stage));"""
                )
        else:
            with value._connection() as c:
                c.execute(
                    """CREATE TABLE IF NOT EXISTS stage_receipts(receipt_hash TEXT PRIMARY KEY,operation_id TEXT NOT NULL,stage TEXT NOT NULL,store_id TEXT NOT NULL,payload TEXT NOT NULL,payload_hash TEXT NOT NULL,UNIQUE(operation_id,stage))"""
                )
        value.verify()
        return value

    def prepare(
        self,
        *,
        learner_id: str,
        conversation_id: str,
        intent: str,
        input_hash: str,
        expected_educational_side_effects: tuple[str, ...] = (),
        expected_progress_side_effects: tuple[str, ...] = (),
        expected_conversation_result: str = "TURN",
        created_at: str | None = None,
    ) -> TutorOperation:
        key = content_hash(
            {
                "learner_id": learner_id,
                "conversation_id": conversation_id,
                "intent": intent,
                "input_hash": input_hash,
            }
        )
        with self._connection() as c:
            row = c.execute(
                "SELECT payload FROM operations WHERE idempotency_key=?", (key,)
            ).fetchone()
        if row is not None:
            return _load(row[0])
        stamp = created_at or utc_now()
        body = {
            "operation_id": f"tutor.operation.{key[:24]}",
            "idempotency_key": key,
            "learner_id": learner_id,
            "conversation_id": conversation_id,
            "intent": intent,
            "input_hash": input_hash,
            "expected_educational_side_effects": expected_educational_side_effects,
            "expected_progress_side_effects": expected_progress_side_effects,
            "expected_conversation_result": expected_conversation_result,
            "status": TutorOperationStatus.PREPARED,
            "step_receipts": (),
            "created_at": stamp,
            "updated_at": stamp,
        }
        value = TutorOperation(**body, operation_hash=content_hash(body))
        self._insert(value)
        self._crash(value)
        return value

    def advance(
        self,
        old: TutorOperation,
        status: TutorOperationStatus,
        receipt_hash: str,
        *,
        updated_at: str | None = None,
    ) -> TutorOperation:
        verify_operation(old)
        if _NEXT.get(old.status) is not status:
            raise ValueError("operation stage cannot be skipped")
        if not receipt_hash:
            raise ValueError("operation stage requires an exact receipt")
        provisional = replace(
            old,
            status=status,
            step_receipts=(*old.step_receipts, (status.value, receipt_hash)),
            updated_at=updated_at or utc_now(),
            operation_hash="",
        )
        body = asdict(provisional)
        body.pop("operation_hash")
        new = replace(provisional, operation_hash=content_hash(body))
        self._replace(old, new)
        self._crash(new)
        return new

    def recovery_required(
        self, old: TutorOperation, receipt_hash: str
    ) -> TutorOperation:
        return self._terminal(old, TutorOperationStatus.RECOVERY_REQUIRED, receipt_hash)

    def failed(self, old: TutorOperation, receipt_hash: str) -> TutorOperation:
        return self._terminal(old, TutorOperationStatus.FAILED, receipt_hash)

    def get(self, operation_id: str) -> TutorOperation:
        with self._connection() as c:
            row = c.execute(
                "SELECT payload,payload_hash FROM operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
        if row is None or bytes_hash(row[0].encode()) != row[1]:
            raise KeyError("unknown or corrupt tutor operation")
        return _load(row[0])

    def pending_recovery(self) -> tuple[TutorOperation, ...]:
        with self._connection() as c:
            rows = c.execute(
                "SELECT payload FROM operations WHERE status NOT IN ('COMPLETED','FAILED') ORDER BY operation_id"
            ).fetchall()
        return tuple(_load(x[0]) for x in rows)

    def record_stage_receipt(self, value: StoreStageReceipt) -> None:
        body = asdict(value)
        digest = body.pop("receipt_hash")
        if content_hash(body) != digest:
            raise ValueError("store stage receipt hash mismatch")
        payload = canonical_json(asdict(value))
        with self._connection() as c:
            row = c.execute(
                "SELECT payload,payload_hash FROM stage_receipts WHERE operation_id=? AND stage=?",
                (value.operation_id, value.stage.value),
            ).fetchone()
            expected = (payload, bytes_hash(payload.encode("utf-8")))
            if row is not None:
                if row != expected:
                    raise ValueError("immutable store stage receipt collision")
                return
            c.execute(
                "INSERT INTO stage_receipts VALUES(?,?,?,?,?,?)",
                (
                    value.receipt_hash,
                    value.operation_id,
                    value.stage.value,
                    value.store_id,
                    payload,
                    expected[1],
                ),
            )

    def stage_receipt(
        self, operation_id: str, stage: TutorOperationStatus
    ) -> StoreStageReceipt | None:
        with self._connection() as c:
            row = c.execute(
                "SELECT payload,payload_hash FROM stage_receipts WHERE operation_id=? AND stage=?",
                (operation_id, stage.value),
            ).fetchone()
        if row is None:
            return None
        if bytes_hash(row[0].encode("utf-8")) != row[1]:
            raise ValueError("store stage receipt checksum mismatch")
        payload = json.loads(row[0])
        payload["stage"] = TutorOperationStatus(payload["stage"])
        payload["committed_record_hashes"] = tuple(payload["committed_record_hashes"])
        value = StoreStageReceipt(**payload)
        body = asdict(value)
        digest = body.pop("receipt_hash")
        if content_hash(body) != digest:
            raise ValueError("stored stage receipt hash mismatch")
        return value

    def recover(
        self,
        operation_id: str,
        verified_receipts: dict[TutorOperationStatus, str],
    ) -> TutorOperation:
        """Complete a saga only from externally verified immutable step receipts."""
        current = self.get(operation_id)
        if current.status is not TutorOperationStatus.RECOVERY_REQUIRED:
            raise ValueError("operation is not awaiting recovery")
        completed = [
            TutorOperationStatus(stage)
            for stage, _ in current.step_receipts
            if stage in {item.value for item in _NEXT.values()}
        ]
        stage = completed[-1] if completed else TutorOperationStatus.PREPARED
        working = current
        if completed:
            provisional = replace(
                current,
                status=stage,
                updated_at=utc_now(),
                operation_hash="",
            )
            body = asdict(provisional)
            body.pop("operation_hash")
            working = replace(provisional, operation_hash=content_hash(body))
            self._replace(current, working)
        while stage is not TutorOperationStatus.COMPLETED:
            next_stage = _NEXT[stage]
            receipt = verified_receipts.get(next_stage)
            if not receipt:
                if next_stage is TutorOperationStatus.COMPLETED:
                    break
                raise ValueError("recovery lacks a verified stage receipt")
            provisional = replace(
                working,
                status=next_stage,
                step_receipts=(*working.step_receipts, (next_stage.value, receipt)),
                updated_at=utc_now(),
                operation_hash="",
            )
            body = asdict(provisional)
            body.pop("operation_hash")
            recovered = replace(provisional, operation_hash=content_hash(body))
            self._replace(working, recovered)
            working = recovered
            stage = next_stage
        return working

    def verify(self) -> dict[str, object]:
        if not self.database_path.exists():
            return {"status": "VERIFIED", "operation_count": 0, "recovery_required": 0}
        with self._connection() as c:
            if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("operation journal SQLite integrity failed")
            rows = c.execute(
                "SELECT payload,payload_hash,status FROM operations"
            ).fetchall()
            receipt_rows = c.execute(
                "SELECT operation_id,stage,payload,payload_hash FROM stage_receipts"
            ).fetchall()
        for payload, digest, status in rows:
            if bytes_hash(payload.encode()) != digest:
                raise ValueError("operation journal checksum mismatch")
            value = _load(payload)
            if value.status.value != status:
                raise ValueError("operation journal status index mismatch")
            for stage, receipt_hash in value.step_receipts:
                if stage in {
                    item.value
                    for item in _NEXT.values()
                    if item is not TutorOperationStatus.COMPLETED
                } and (
                    value.intent == "GENERIC_CONTROLLED_TURN"
                    or any(item[0] == value.operation_id for item in receipt_rows)
                ):
                    receipt = self.stage_receipt(
                        value.operation_id, TutorOperationStatus(stage)
                    )
                    if receipt is None or receipt.receipt_hash != receipt_hash:
                        raise ValueError("operation journal stage receipt is missing")
        for operation_id, stage, payload, digest in receipt_rows:
            if bytes_hash(payload.encode("utf-8")) != digest:
                raise ValueError("stage receipt payload checksum mismatch")
            receipt = self.stage_receipt(operation_id, TutorOperationStatus(stage))
            if receipt is None:
                raise ValueError("stage receipt cannot be loaded")
        return {
            "status": "VERIFIED",
            "operation_count": len(rows),
            "recovery_required": sum(
                x[2] == TutorOperationStatus.RECOVERY_REQUIRED.value for x in rows
            ),
            "stage_receipt_count": len(receipt_rows),
        }

    def _terminal(self, old, status, receipt_hash):
        verify_operation(old)
        provisional = replace(
            old,
            status=status,
            step_receipts=(*old.step_receipts, (status.value, receipt_hash)),
            updated_at=utc_now(),
            operation_hash="",
        )
        body = asdict(provisional)
        body.pop("operation_hash")
        new = replace(provisional, operation_hash=content_hash(body))
        self._replace(old, new)
        self._crash(new)
        return new

    def _insert(self, value):
        payload = canonical_json(asdict(value))
        with self._connection() as c:
            c.execute(
                "INSERT INTO operations VALUES(?,?,?,?,?)",
                (
                    value.operation_id,
                    value.idempotency_key,
                    payload,
                    bytes_hash(payload.encode()),
                    value.status.value,
                ),
            )
            c.execute(
                "INSERT INTO audit(operation_id,status,receipt_hash,created_at) VALUES(?,?,?,?)",
                (
                    value.operation_id,
                    value.status.value,
                    value.operation_hash,
                    value.updated_at,
                ),
            )

    def _replace(self, old, new):
        payload = canonical_json(asdict(new))
        with self._connection() as c:
            changed = c.execute(
                "UPDATE operations SET payload=?,payload_hash=?,status=? WHERE operation_id=? AND payload_hash=?",
                (
                    payload,
                    bytes_hash(payload.encode()),
                    new.status.value,
                    old.operation_id,
                    bytes_hash(canonical_json(asdict(old)).encode()),
                ),
            )
            if changed.rowcount != 1:
                raise ValueError("stale tutor operation transition")
            c.execute(
                "INSERT INTO audit(operation_id,status,receipt_hash,created_at) VALUES(?,?,?,?)",
                (
                    new.operation_id,
                    new.status.value,
                    new.step_receipts[-1][1],
                    new.updated_at,
                ),
            )

    def _crash(self, value):
        if self.crash_injector is not None:
            self.crash_injector(value.status.value, value)

    def inject(self, point: str, value: TutorOperation) -> None:
        """Expose exact before/after write and publication crash points."""
        if self.crash_injector is not None:
            self.crash_injector(point, value)

    @contextmanager
    def _connection(self):
        c = sqlite3.connect(self.database_path, timeout=5.0)
        try:
            c.execute("PRAGMA busy_timeout=5000")
            with c:
                yield c
        finally:
            c.close()


def verify_operation(value: TutorOperation) -> None:
    body = asdict(value)
    digest = body.pop("operation_hash")
    if content_hash(body) != digest:
        raise ValueError("tutor operation hash mismatch")


def _load(payload: str) -> TutorOperation:
    row = json.loads(payload)
    row["status"] = TutorOperationStatus(row["status"])
    row["expected_educational_side_effects"] = tuple(
        row["expected_educational_side_effects"]
    )
    row["expected_progress_side_effects"] = tuple(row["expected_progress_side_effects"])
    row["step_receipts"] = tuple(tuple(x) for x in row["step_receipts"])
    value = TutorOperation(**row)
    verify_operation(value)
    return value


class TutorSagaCoordinator:
    """Advance the journal only around verified idempotent real-store commits."""

    def __init__(self, journal: TutorOperationJournal) -> None:
        self.journal = journal

    def apply_store_stage(
        self,
        operation: TutorOperation,
        stage: TutorOperationStatus,
        *,
        store_id: str,
        write,
        inspect,
        committed_at: str | None = None,
    ) -> tuple[TutorOperation, StoreStageReceipt]:
        if _NEXT.get(operation.status) is not stage:
            raise ValueError("saga store stage is out of order")
        self.journal.inject(f"before_{stage.value.casefold()}_store_write", operation)
        hashes = tuple(inspect(operation.operation_id))
        if not hashes:
            write(operation.operation_id)
            hashes = tuple(inspect(operation.operation_id))
        if not hashes or len(set(hashes)) != len(hashes):
            raise ValueError("store commit lacks unique operation-bound records")
        stamp = committed_at or operation.created_at
        body = {
            "operation_id": operation.operation_id,
            "stage": stage,
            "store_id": store_id,
            "committed_record_hashes": hashes,
            "committed_at": stamp,
        }
        receipt = StoreStageReceipt(**body, receipt_hash=content_hash(body))
        self.journal.record_stage_receipt(receipt)
        self.journal.inject(f"after_{stage.value.casefold()}_store_write", operation)
        self.journal.inject(
            f"before_{stage.value.casefold()}_journal_advance", operation
        )
        advanced = self.journal.advance(
            operation, stage, receipt.receipt_hash, updated_at=stamp
        )
        self.journal.inject(f"after_{stage.value.casefold()}_journal_advance", advanced)
        return advanced, receipt

    def publish(self, operation: TutorOperation, response_hash: str, publish):
        if operation.status is not TutorOperationStatus.CONVERSATION_COMMITTED:
            raise ValueError("public response publication requires committed stores")
        self.journal.inject("before_final_public_response_publication", operation)
        result = publish()
        completed = self.journal.advance(
            operation, TutorOperationStatus.COMPLETED, response_hash
        )
        self.journal.inject("after_final_public_response_publication", completed)
        return completed, result

    def recover(
        self,
        operation_id: str,
        stages: tuple[tuple[TutorOperationStatus, str, object, object], ...],
    ) -> TutorOperation:
        operation = self.journal.get(operation_id)
        if operation.status is not TutorOperationStatus.RECOVERY_REQUIRED:
            raise ValueError("saga operation is not recovery-required")
        verified: dict[TutorOperationStatus, str] = {}
        for stage, store_id, write, inspect in stages:
            if any(recorded == stage.value for recorded, _ in operation.step_receipts):
                continue
            self.journal.inject(
                f"before_{stage.value.casefold()}_store_write", operation
            )
            hashes = tuple(inspect(operation.operation_id))
            if not hashes:
                write(operation.operation_id)
                hashes = tuple(inspect(operation.operation_id))
            if not hashes or len(set(hashes)) != len(hashes):
                raise ValueError("recovery store inspection is irreconcilable")
            receipt = self.journal.stage_receipt(operation.operation_id, stage)
            if receipt is None:
                body = {
                    "operation_id": operation.operation_id,
                    "stage": stage,
                    "store_id": store_id,
                    "committed_record_hashes": hashes,
                    "committed_at": operation.created_at,
                }
                receipt = StoreStageReceipt(**body, receipt_hash=content_hash(body))
                self.journal.record_stage_receipt(receipt)
            elif (
                receipt.store_id != store_id
                or receipt.committed_record_hashes != hashes
            ):
                raise ValueError("recovery stage receipt differs from store inspection")
            verified[stage] = receipt.receipt_hash
            self.journal.inject(
                f"after_{stage.value.casefold()}_store_write", operation
            )
        return self.journal.recover(operation_id, verified)


def _stage_index(value: TutorOperationStatus) -> int:
    order = (
        TutorOperationStatus.PREPARED,
        TutorOperationStatus.EDUCATION_APPLIED,
        TutorOperationStatus.PROGRESS_APPLIED,
        TutorOperationStatus.CONVERSATION_COMMITTED,
        TutorOperationStatus.COMPLETED,
    )
    return order.index(value) if value in order else -1
