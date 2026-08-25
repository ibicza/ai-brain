"""Append-only Stage-1 audit log with hash chaining."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_brain.rules.memory import RuleMemory
from ai_brain.stage1.models import InstalledRuleReceipt, content_hash, utc_now

_SHA256 = re.compile(r"[0-9a-f]{64}")
_EVENT_FIELDS = {
    "sequence",
    "timestamp",
    "event_type",
    "proposal_id",
    "payload",
    "previous_hash",
    "event_hash",
}


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    timestamp: str
    event_type: str
    proposal_id: str | None
    payload: dict[str, Any]
    previous_hash: str
    event_hash: str


@dataclass(frozen=True)
class AuditRevision:
    revision: int
    status: str
    valid: bool
    errors: tuple[str, ...]
    event_types: tuple[str, ...]


@dataclass(frozen=True)
class AuditReconstruction:
    proposal_id: str
    valid: bool
    errors: tuple[str, ...]
    event_types: tuple[str, ...]
    original_input_hash: str | None
    specification_hash: str | None
    proposal_hash: str | None
    candidate_hash: str | None
    evidence_hash: str | None
    verified_review_hash: str | None
    approval_hash: str | None
    installed_rule_id: str | None
    execution_hashes: tuple[str, ...]
    active_revision: int | None
    revisions: tuple[AuditRevision, ...]


_REVISION_EVENTS = {
    "PROPOSAL_RECEIVED",
    "PROPOSAL_PARSED",
    "CLARIFICATION_RESOLVED",
    "PROPOSAL_EDITED_VERIFICATION_INVALIDATED",
    "PROPOSAL_REVIEWED",
    "VERIFICATION_FAILED",
    "CANDIDATE_VERIFIED",
    "VERIFIED_REVIEWED",
    "APPROVAL_REJECTED",
    "PROPOSAL_APPROVED",
    "RULE_MEMORY_WRITE_FAILED",
    "RULE_INSTALLED",
    "EXECUTION_FAILED",
    "RULE_EXECUTED",
}
_EVENT_RANK = {
    "PROPOSAL_RECEIVED": 0,
    "PROPOSAL_PARSED": 1,
    "CLARIFICATION_RESOLVED": 1,
    "PROPOSAL_EDITED_VERIFICATION_INVALIDATED": 1,
    "PROPOSAL_REVIEWED": 2,
    "VERIFICATION_FAILED": 3,
    "CANDIDATE_VERIFIED": 3,
    "VERIFIED_REVIEWED": 4,
    "APPROVAL_REJECTED": 5,
    "PROPOSAL_APPROVED": 5,
    "RULE_MEMORY_WRITE_FAILED": 6,
    "RULE_INSTALLED": 6,
    "EXECUTION_FAILED": 7,
    "RULE_EXECUTED": 7,
}


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
                if not isinstance(row, dict) or set(row) != _EVENT_FIELDS:
                    raise TypeError("event schema mismatch")
                event = AuditEvent(**row)
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(f"Corrupt audit event at line {number}") from exc
            _validate_event_types(event, number)
            core = {key: value for key, value in row.items() if key != "event_hash"}
            if event.sequence != number or event.previous_hash != previous_hash:
                raise ValueError(f"Broken audit chain at line {number}")
            if content_hash(core) != event.event_hash:
                raise ValueError(f"Audit hash mismatch at line {number}")
            events.append(event)
            previous_hash = event.event_hash
        return events


def reconstruct_audit(
    audit: AuditLog,
    memory: RuleMemory,
    proposal_id: str,
    *,
    receipt: InstalledRuleReceipt | None = None,
    require_execution: bool = False,
) -> AuditReconstruction:
    """Reconstruct a proposal while preserving and validating every revision."""
    events = [item for item in audit.replay() if item.proposal_id == proposal_id]
    errors: list[str] = []
    grouped: dict[int, list[AuditEvent]] = {}
    latest_seen = 0
    for event in events:
        if event.event_type not in _REVISION_EVENTS:
            continue
        revision = event.payload.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            errors.append(f"{event.event_type}: missing or malformed revision")
            continue
        if revision < latest_seen:
            errors.append(
                f"stale revision {revision} event after revision {latest_seen}"
            )
        latest_seen = max(latest_seen, revision)
        grouped.setdefault(revision, []).append(event)
    active_revision = max(grouped, default=None)
    if active_revision is None:
        errors.append("proposal workflow events are missing")
    elif sorted(grouped) != list(range(1, active_revision + 1)):
        errors.append("proposal revision sequence has gaps")

    revision_rows: list[AuditRevision] = []
    for revision, revision_events in sorted(grouped.items()):
        revision_errors = _validate_revision(
            revision,
            revision_events,
            active=revision == active_revision,
            require_execution=require_execution,
        )
        errors.extend(f"revision {revision}: {item}" for item in revision_errors)
        revision_rows.append(
            AuditRevision(
                revision=revision,
                status="ACTIVE" if revision == active_revision else "SUPERSEDED",
                valid=not revision_errors,
                errors=tuple(revision_errors),
                event_types=tuple(item.event_type for item in revision_events),
            )
        )

    active_events = grouped.get(active_revision, [])
    selected = _successful_events(active_events)
    received = next(
        (item for item in events if item.event_type == "PROPOSAL_RECEIVED"), None
    )
    parsed = (
        selected.get("PROPOSAL_PARSED")
        or selected.get("PROPOSAL_EDITED_VERIFICATION_INVALIDATED")
        or selected.get("CLARIFICATION_RESOLVED")
    )
    reviewed = selected.get("PROPOSAL_REVIEWED")
    verified = selected.get("CANDIDATE_VERIFIED")
    verified_reviewed = selected.get("VERIFIED_REVIEWED")
    approved = selected.get("PROPOSAL_APPROVED")
    installed = selected.get("RULE_INSTALLED")
    original_hash = _payload_hash(received, "original_input_hash", errors)
    specification = _consistent_hash(
        (parsed, reviewed, verified, verified_reviewed, approved, installed),
        "specification_hash",
        errors,
    )
    proposal = _consistent_hash(
        (parsed, reviewed, verified, verified_reviewed, approved, installed),
        "proposal_hash",
        errors,
    )
    candidate = _consistent_hash(
        (verified, verified_reviewed, approved, installed), "candidate_hash", errors
    )
    evidence = _consistent_hash(
        (verified, verified_reviewed, approved, installed), "evidence_hash", errors
    )
    review_hash = _consistent_hash(
        (verified_reviewed, approved, installed), "verified_review_hash", errors
    )
    approval = _consistent_hash((approved, installed), "approval_hash", errors)
    rule_id = _payload_string(installed, "rule_id", errors)
    if rule_id is not None:
        record = memory.records.get(rule_id)
        if record is None:
            errors.append("installed rule is absent from RuleMemory")
        elif installed is not None and (
            installed.payload.get("rule_semantic_hash") != record.semantic_hash
        ):
            errors.append("installed rule semantic hash mismatch")
    execution_events = [
        item
        for item in active_events
        if item.event_type in {"RULE_EXECUTED", "EXECUTION_FAILED"}
    ]
    execution_hashes: list[str] = []
    for event in execution_events:
        if event.payload.get("rule_id") != rule_id:
            errors.append("execution against unrelated rule")
        value = event.payload.get("execution_hash")
        if value is not None:
            if not _valid_hash(value):
                errors.append("malformed execution hash")
            else:
                execution_hashes.append(value)

    if receipt is not None:
        receipt_values = {
            "proposal_id": receipt.proposal_id,
            "proposal_revision": receipt.proposal_revision,
            "proposal_hash": receipt.proposal_hash,
            "specification_hash": receipt.specification_hash,
            "candidate_hash": receipt.candidate_hash,
            "evidence_hash": receipt.evidence_hash,
            "verified_review_hash": receipt.verified_review_hash,
            "approval_hash": receipt.approval_hash,
            "installed_rule_id": receipt.installed_rule_id,
        }
        actual_values = {
            "proposal_id": proposal_id,
            "proposal_revision": active_revision,
            "proposal_hash": proposal,
            "specification_hash": specification,
            "candidate_hash": candidate,
            "evidence_hash": evidence,
            "verified_review_hash": review_hash,
            "approval_hash": approval,
            "installed_rule_id": rule_id,
        }
        for name, value in receipt_values.items():
            if actual_values[name] != value:
                errors.append(f"receipt {name} mismatch")
        if rule_id is not None and rule_id in memory.records:
            try:
                provenance = json.loads(memory.records[rule_id].provenance)
            except (TypeError, json.JSONDecodeError):
                errors.append("installed rule provenance is malformed")
            else:
                if (
                    not isinstance(provenance, dict)
                    or provenance.get("proposal_revision") != active_revision
                ):
                    errors.append("installed rule proposal_revision mismatch")
    return AuditReconstruction(
        proposal_id=proposal_id,
        valid=not errors,
        errors=tuple(errors),
        event_types=tuple(item.event_type for item in events),
        original_input_hash=original_hash,
        specification_hash=specification,
        proposal_hash=proposal,
        candidate_hash=candidate,
        evidence_hash=evidence,
        verified_review_hash=review_hash,
        approval_hash=approval,
        installed_rule_id=rule_id,
        execution_hashes=tuple(execution_hashes),
        active_revision=active_revision,
        revisions=tuple(revision_rows),
    )


def _validate_revision(
    revision: int,
    events: list[AuditEvent],
    *,
    active: bool,
    require_execution: bool,
) -> list[str]:
    errors: list[str] = []
    event_types = [item.event_type for item in events]
    starts = (
        ("PROPOSAL_RECEIVED", "PROPOSAL_PARSED")
        if revision == 1
        else (
            "PROPOSAL_EDITED_VERIFICATION_INVALIDATED",
            "CLARIFICATION_RESOLVED",
        )
    )
    if revision == 1:
        for event_type in starts:
            if event_types.count(event_type) != 1:
                errors.append(
                    f"{event_type}: expected exactly one event, got "
                    f"{event_types.count(event_type)}"
                )
    elif sum(event_types.count(item) for item in starts) != 1:
        errors.append("revision must start with exactly one edit or clarification")

    unique_success = (
        "PROPOSAL_REVIEWED",
        "CANDIDATE_VERIFIED",
        "VERIFIED_REVIEWED",
        "PROPOSAL_APPROVED",
        "RULE_INSTALLED",
    )
    for event_type in unique_success:
        count = event_types.count(event_type)
        if count > 1 or (active and count != 1):
            errors.append(f"{event_type}: expected exactly one event, got {count}")
    if (
        active
        and require_execution
        and not any(
            item in {"RULE_EXECUTED", "EXECUTION_FAILED"} for item in event_types
        )
    ):
        errors.append("execution event is missing")

    ranks = [_EVENT_RANK[item] for item in event_types]
    if ranks != sorted(ranks):
        errors.append("workflow events are reordered")
    _validate_revision_hashes(events, errors)
    return errors


def _successful_events(events: list[AuditEvent]) -> dict[str, AuditEvent | None]:
    return {
        event_type: next(
            (item for item in events if item.event_type == event_type), None
        )
        for event_type in _REVISION_EVENTS
    }


def _validate_revision_hashes(events: list[AuditEvent], errors: list[str]) -> None:
    selected = _successful_events(events)
    start = (
        selected.get("PROPOSAL_PARSED")
        or selected.get("PROPOSAL_EDITED_VERIFICATION_INVALIDATED")
        or selected.get("CLARIFICATION_RESOLVED")
    )
    chain = (
        start,
        selected.get("PROPOSAL_REVIEWED"),
        selected.get("CANDIDATE_VERIFIED"),
        selected.get("VERIFIED_REVIEWED"),
        selected.get("PROPOSAL_APPROVED"),
        selected.get("RULE_INSTALLED"),
    )
    _consistent_hash(chain, "proposal_hash", errors)
    _consistent_hash(chain, "specification_hash", errors)
    candidate_chain = (
        selected.get("CANDIDATE_VERIFIED"),
        selected.get("VERIFIED_REVIEWED"),
        selected.get("PROPOSAL_APPROVED"),
        selected.get("RULE_INSTALLED"),
    )
    _consistent_hash(candidate_chain, "candidate_hash", errors)
    _consistent_hash(candidate_chain, "evidence_hash", errors)
    _consistent_hash(
        (
            selected.get("VERIFIED_REVIEWED"),
            selected.get("PROPOSAL_APPROVED"),
            selected.get("RULE_INSTALLED"),
        ),
        "verified_review_hash",
        errors,
    )
    _consistent_hash(
        (selected.get("PROPOSAL_APPROVED"), selected.get("RULE_INSTALLED")),
        "approval_hash",
        errors,
    )


def _validate_event_types(event: AuditEvent, line: int) -> None:
    if isinstance(event.sequence, bool) or not isinstance(event.sequence, int):
        raise TypeError(f"Corrupt audit event at line {line}: invalid sequence")
    if not isinstance(event.event_type, str) or not isinstance(event.payload, dict):
        raise TypeError(f"Corrupt audit event at line {line}: invalid types")
    if event.proposal_id is not None and not isinstance(event.proposal_id, str):
        raise ValueError(f"Corrupt audit event at line {line}: invalid proposal_id")
    if not _valid_hash(event.previous_hash) or not _valid_hash(event.event_hash):
        raise ValueError(f"Corrupt audit event at line {line}: malformed hash")
    try:
        parsed = datetime.fromisoformat(event.timestamp)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Corrupt audit event at line {line}: invalid timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(
            f"Corrupt audit event at line {line}: timestamp has no timezone"
        )


def _consistent_hash(
    events: tuple[AuditEvent | None, ...], name: str, errors: list[str]
) -> str | None:
    values = [_payload_hash(event, name, errors) for event in events if event]
    present = [value for value in values if value is not None]
    if present and any(value != present[0] for value in present[1:]):
        errors.append(f"changed or stale {name}")
    return present[0] if present else None


def _payload_hash(event: AuditEvent | None, name: str, errors: list[str]) -> str | None:
    if event is None:
        return None
    value = event.payload.get(name)
    if not _valid_hash(value):
        errors.append(f"{event.event_type}: missing or malformed {name}")
        return None
    return value


def _payload_string(
    event: AuditEvent | None, name: str, errors: list[str]
) -> str | None:
    if event is None:
        return None
    value = event.payload.get(name)
    if not isinstance(value, str) or not value:
        errors.append(f"{event.event_type}: missing or malformed {name}")
        return None
    return value


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None
