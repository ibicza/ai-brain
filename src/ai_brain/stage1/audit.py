"""Append-only Stage-1 audit log with hash chaining."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_brain.stage1.models import content_hash, utc_now


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    timestamp: str
    event_type: str
    proposal_id: str | None
    payload: dict[str, Any]
    previous_hash: str
    event_hash: str


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(
        self, event_type: str, payload: dict[str, Any], proposal_id: str | None = None
    ) -> AuditEvent:
        events = self.replay()
        previous_hash = events[-1].event_hash if events else "0" * 64
        core = {
            "sequence": len(events) + 1,
            "timestamp": utc_now(),
            "event_type": event_type,
            "proposal_id": proposal_id,
            "payload": payload,
            "previous_hash": previous_hash,
        }
        event = AuditEvent(**core, event_hash=content_hash(core))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.__dict__, ensure_ascii=False, sort_keys=True) + "\n"
        descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, line.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return event

    def replay(self) -> list[AuditEvent]:
        if not self.path.exists():
            return []
        events: list[AuditEvent] = []
        previous_hash = "0" * 64
        for number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), 1
        ):
            try:
                row = json.loads(line)
                event = AuditEvent(**row)
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(f"Corrupt audit event at line {number}") from exc
            core = {key: value for key, value in row.items() if key != "event_hash"}
            if event.sequence != number or event.previous_hash != previous_hash:
                raise ValueError(f"Broken audit chain at line {number}")
            if content_hash(core) != event.event_hash:
                raise ValueError(f"Audit hash mismatch at line {number}")
            events.append(event)
            previous_hash = event.event_hash
        return events
