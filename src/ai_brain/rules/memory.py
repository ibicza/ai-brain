"""Checksummed, durable RuleMemory with explicit migration and recovery."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, fields, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_brain.rules.ast import (
    ProgramAst,
    default_binding,
    parse_canonical_dsl,
    render_canonical_program,
)
from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.rules.statuses import VerificationStatus
from ai_brain.rules.verifier import VerificationResult, property_verify

RULE_MEMORY_SCHEMA_VERSION = 1
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ROOT_FIELDS = {
    "schema_version",
    "allow_hypothesis_identified",
    "records",
    "content_sha256",
}
_LEGACY_ROOT_FIELDS = _ROOT_FIELDS - {"content_sha256"}


class RuleMemoryIntegrityError(ValueError):
    """The primary RuleMemory fails trusted schema or checksum validation."""


class StoredRuleParseError(RuleMemoryIntegrityError):
    """A checksummed RuleMemory contains malformed canonical rule DSL."""


class RuleMemoryRecoveryError(RuntimeError, ValueError):
    """Neither the primary nor its designated backup can be trusted."""


class RuleMemoryRecoveryRequiredError(RuntimeError):
    """A write was refused until explicit backup recovery is completed."""


class RuleMemoryIOError(OSError):
    """Expected filesystem I/O prevented a RuleMemory operation."""


@dataclass(frozen=True)
class RuleRecord:
    rule_id: str
    program_json: str
    semantic_hash: str
    status: VerificationStatus
    specification: ProgramSpecification
    verification_evidence: dict[str, Any] | None = None
    version: int = 1
    deprecated: bool = False
    provenance: str = ""


class RuleMemory:
    def __init__(
        self,
        *,
        allow_hypothesis_identified: bool = False,
        recovery_source: str = "new",
    ) -> None:
        if not isinstance(allow_hypothesis_identified, bool):
            raise TypeError("allow_hypothesis_identified must be bool")
        self.records: dict[str, RuleRecord] = {}
        self.allow_hypothesis_identified = allow_hypothesis_identified
        self.recovery_source = recovery_source

    def can_store(self, status: VerificationStatus) -> bool:
        if status in {
            VerificationStatus.FORMALLY_VERIFIED,
            VerificationStatus.PROPERTY_VERIFIED,
        }:
            return True
        return bool(
            self.allow_hypothesis_identified
            and status == VerificationStatus.IDENTIFIED_IN_HYPOTHESIS_SPACE
        )

    def add(
        self,
        program: ProgramAst,
        specification: ProgramSpecification,
        status: VerificationStatus,
        *,
        provenance: str = "",
        verification_evidence: VerificationResult | dict[str, Any] | None = None,
    ) -> RuleRecord:
        if not self.can_store(status):
            raise ValueError(f"RuleMemory rejects status {status}")
        evidence = _evidence_dict(verification_evidence)
        _validate_status_evidence(status, specification, evidence)
        semantic_hash = program.semantic_hash(alpha=False, order_insensitive=False)
        for record in self.records.values():
            if not record.deprecated and record.semantic_hash == semantic_hash:
                raise ValueError(f"Duplicate semantic rule {semantic_hash}")
        next_number = (
            max((int(rule_id.split("-")[1]) for rule_id in self.records), default=0) + 1
        )
        version = 1 + max(
            (
                record.version
                for record in self.records.values()
                if record.semantic_hash == semantic_hash
            ),
            default=0,
        )
        record = RuleRecord(
            rule_id=f"rule-{next_number:05d}-{semantic_hash[:8]}",
            program_json=render_canonical_program(program, default_binding()),
            semantic_hash=semantic_hash,
            status=status,
            specification=specification,
            verification_evidence=evidence,
            provenance=provenance,
            version=version,
        )
        self.records[record.rule_id] = record
        return record

    def save(self, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuleMemoryIOError(
                f"RuleMemory directory creation failed: {path.parent}: {exc}"
            ) from exc
        rendered = _render(self)
        # Validate the exact bytes before they are eligible to replace anything.
        self._load_text(rendered, source="temporary validation")
        backup = path.with_suffix(path.suffix + ".bak")
        if path.exists():
            try:
                current_memory = self.load(path)
                current = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise RuleMemoryRecoveryRequiredError(
                    "RuleMemory primary is not writable until explicit recovery"
                ) from exc
            except (RuleMemoryIntegrityError, RuleMemoryIOError) as exc:
                raise RuleMemoryRecoveryRequiredError(
                    "RuleMemory primary is not writable until explicit recovery"
                ) from exc
            if current_memory.recovery_source != "primary":
                raise RuleMemoryRecoveryRequiredError(
                    "RuleMemory write requires a validated primary"
                )
            _atomic_write(backup, current)
            self.load(backup)
        _atomic_write(path, rendered)
        self.load(path)

    @classmethod
    def load(cls, path: Path) -> RuleMemory:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise RuleMemoryIOError(f"RuleMemory read failed: {path}: {exc}") from exc
        try:
            return cls._load_text(text, source="primary")
        except RuleMemoryIntegrityError:
            raise
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            raise RuleMemoryIntegrityError(f"Corrupt RuleMemory: {exc}") from exc

    @classmethod
    def _load_text(cls, text: str, *, source: str) -> RuleMemory:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Corrupt RuleMemory: invalid JSON ({source})") from exc
        if not isinstance(data, dict):
            raise TypeError("Corrupt RuleMemory: root must be an object")
        if "schema_version" in data and (
            data["schema_version"] != RULE_MEMORY_SCHEMA_VERSION
            or isinstance(data["schema_version"], bool)
        ):
            raise ValueError("Unsupported RuleMemory schema")
        if "content_sha256" not in data:
            raise ValueError("Corrupt RuleMemory: missing mandatory checksum")
        _exact_keys(data, _ROOT_FIELDS, "RuleMemory root")
        if not isinstance(data["allow_hypothesis_identified"], bool):
            raise TypeError("Corrupt RuleMemory: policy flag must be bool")
        checksum = data["content_sha256"]
        if not isinstance(checksum, str) or _SHA256.fullmatch(checksum) is None:
            raise ValueError("Corrupt RuleMemory: malformed or missing checksum")
        body = {key: value for key, value in data.items() if key != "content_sha256"}
        if _digest(body) != checksum:
            raise ValueError("Corrupt RuleMemory: checksum mismatch")
        return cls._from_body(body, recovery_source=source)

    @classmethod
    def _from_body(cls, body: dict[str, Any], *, recovery_source: str) -> RuleMemory:
        records = body["records"]
        if not isinstance(records, list):
            raise TypeError("Corrupt RuleMemory: records must be a list")
        memory = cls(
            allow_hypothesis_identified=body["allow_hypothesis_identified"],
            recovery_source=recovery_source,
        )
        active_hashes: set[str] = set()
        expected_record_fields = {item.name for item in fields(RuleRecord)}
        for index, source_row in enumerate(records):
            if not isinstance(source_row, dict):
                raise TypeError(f"Corrupt RuleMemory record {index}: not an object")
            _exact_keys(
                source_row, expected_record_fields, f"RuleMemory record {index}"
            )
            record = _record_from_json(source_row, index)
            try:
                program = parse_canonical_dsl(record.program_json)[0]
            except (TypeError, ValueError) as exc:
                raise StoredRuleParseError(
                    f"Corrupt RuleMemory record {index}: malformed AST"
                ) from exc
            if record.rule_id in memory.records:
                raise ValueError(f"Corrupt RuleMemory: duplicate id {record.rule_id}")
            if not memory.can_store(record.status):
                raise ValueError(
                    f"Corrupt RuleMemory: rejected status {record.rule_id}"
                )
            _validate_status_evidence(
                record.status, record.specification, record.verification_evidence
            )
            actual_hash = program.semantic_hash(alpha=False, order_insensitive=False)
            if actual_hash != record.semantic_hash:
                raise ValueError(
                    f"Corrupt RuleMemory: semantic hash mismatch {record.rule_id}"
                )
            if not record.deprecated and record.semantic_hash in active_hashes:
                raise ValueError("Corrupt RuleMemory: duplicate active semantic rule")
            if not record.deprecated:
                active_hashes.add(record.semantic_hash)
            memory.records[record.rule_id] = record
        return memory

    @classmethod
    def load_with_backup(cls, path: Path) -> RuleMemory:
        try:
            memory = cls.load(path)
            memory.recovery_source = "primary"
            return memory
        except (RuleMemoryIntegrityError, RuleMemoryIOError) as primary_error:
            backup = path.with_suffix(path.suffix + ".bak")
            if not backup.exists():
                raise
            try:
                memory = cls.load(backup)
            except (RuleMemoryIntegrityError, RuleMemoryIOError) as backup_error:
                raise RuleMemoryRecoveryError(
                    "RuleMemory recovery failed: both primary and backup are invalid; "
                    f"primary={primary_error}; backup={backup_error}"
                ) from backup_error
            memory.recovery_source = f"backup:{backup}"
            return memory

    def deprecate(self, rule_id: str) -> RuleRecord:
        record = self.records[rule_id]
        updated = replace(record, deprecated=True)
        self.records[rule_id] = updated
        return updated

    def active_records(self) -> list[RuleRecord]:
        return [record for record in self.records.values() if not record.deprecated]

    def programs(self) -> list[ProgramAst]:
        return [
            parse_canonical_dsl(record.program_json)[0]
            for record in self.records.values()
        ]


def migrate_legacy_rule_memory(source: Path, destination: Path) -> dict[str, Any]:
    """Explicitly validate and migrate a checksum-less schema-v1 RuleMemory."""
    try:
        raw = source.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid legacy RuleMemory: {exc}") from exc
    if not isinstance(data, dict):
        raise TypeError("Invalid legacy RuleMemory: root must be an object")
    _exact_keys(data, _LEGACY_ROOT_FIELDS, "legacy RuleMemory root")
    if data["schema_version"] != RULE_MEMORY_SCHEMA_VERSION or isinstance(
        data["schema_version"], bool
    ):
        raise ValueError("Invalid legacy RuleMemory schema")
    if not isinstance(data["allow_hypothesis_identified"], bool):
        raise TypeError("Invalid legacy RuleMemory policy flag")
    memory = RuleMemory._from_body(data, recovery_source=f"migration:{source}")
    reverified: list[str] = []
    for record in memory.active_records():
        program = parse_canonical_dsl(record.program_json)[0]
        result = property_verify(program, record.specification, large=True)
        if not result.accepted:
            raise ValueError(
                f"Legacy active rule failed re-verification: {record.rule_id}"
            )
        reverified.append(record.rule_id)
    if destination.exists():
        # Never silently overwrite an existing destination, valid or otherwise.
        raise FileExistsError(f"Migration destination already exists: {destination}")
    memory.save(destination)
    backup = destination.with_suffix(destination.suffix + ".legacy.bak")
    _atomic_write(backup, raw.decode("utf-8"))
    return {
        "source": str(source),
        "destination": str(destination),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "destination_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "records": len(memory.records),
        "active_rules_reverified": reverified,
        "legacy_backup": str(backup),
        "schema_version": RULE_MEMORY_SCHEMA_VERSION,
        "migrated_at": datetime.now(UTC).isoformat(),
    }


def recover_rule_memory(path: Path) -> tuple[RuleMemory, dict[str, Any]]:
    """Explicitly restore a corrupt primary from its fully validated backup."""
    try:
        RuleMemory.load(path)
    except (RuleMemoryIntegrityError, RuleMemoryIOError):
        pass
    else:
        raise RuleMemoryRecoveryRequiredError(
            "RuleMemory recovery refused because the primary is already valid"
        )
    backup = path.with_suffix(path.suffix + ".bak")
    try:
        backup_memory = RuleMemory.load(backup)
        corrupt_bytes = path.read_bytes()
        backup_bytes = backup.read_bytes()
    except (RuleMemoryIntegrityError, RuleMemoryIOError, OSError) as exc:
        raise RuleMemoryRecoveryError(
            f"RuleMemory backup cannot restore the primary: {exc}"
        ) from exc
    timestamp = datetime.now(UTC)
    suffix = timestamp.strftime("%Y%m%dT%H%M%S%fZ")
    corrupt_path = path.with_name(f"{path.name}.{suffix}.corrupt")
    _atomic_write_bytes(corrupt_path, corrupt_bytes)
    _atomic_write_bytes(path, backup_bytes)
    try:
        restored = RuleMemory.load(path)
    except (RuleMemoryIntegrityError, RuleMemoryIOError) as exc:
        raise RuleMemoryRecoveryError(
            "Restored RuleMemory primary failed post-write validation"
        ) from exc
    if set(restored.records) != set(backup_memory.records):
        raise RuleMemoryRecoveryError(
            "Restored RuleMemory record set differs from backup"
        )
    evidence = {
        "primary": str(path),
        "backup": str(backup),
        "preserved_corrupt_primary": str(corrupt_path),
        "corrupt_primary_sha256": hashlib.sha256(corrupt_bytes).hexdigest(),
        "restored_primary_sha256": hashlib.sha256(backup_bytes).hexdigest(),
        "backup_sha256": hashlib.sha256(backup_bytes).hexdigest(),
        "record_count": len(restored.records),
        "active_rule_count": len(restored.active_records()),
        "recovered_at": timestamp.isoformat(),
        "schema_version": RULE_MEMORY_SCHEMA_VERSION,
    }
    return restored, evidence


def _render(memory: RuleMemory) -> str:
    body = {
        "schema_version": RULE_MEMORY_SCHEMA_VERSION,
        "allow_hypothesis_identified": memory.allow_hypothesis_identified,
        "records": [
            {
                **asdict(record),
                "status": str(record.status),
                "specification": asdict(record.specification),
            }
            for record in memory.records.values()
        ],
    }
    return (
        json.dumps(
            {**body, "content_sha256": _digest(body)},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _digest(body: dict[str, Any]) -> str:
    canonical = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    temp_name: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        _fsync_directory(path.parent)
    except OSError as exc:
        raise RuleMemoryIOError(
            f"RuleMemory atomic write failed: {path}: {exc}"
        ) from exc
    finally:
        if temp_name is not None and os.path.exists(temp_name):
            try:
                os.unlink(temp_name)
            except OSError:
                pass


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _record_from_json(row: dict[str, Any], index: int) -> RuleRecord:
    for name in ("rule_id", "program_json", "semantic_hash", "provenance"):
        if not isinstance(row[name], str):
            raise TypeError(f"Corrupt RuleMemory record {index}: {name} must be string")
    if not row["rule_id"] or not row["program_json"]:
        raise ValueError(f"Corrupt RuleMemory record {index}: blank identity/program")
    if _SHA256.fullmatch(row["semantic_hash"]) is None:
        raise ValueError(f"Corrupt RuleMemory record {index}: malformed semantic hash")
    if isinstance(row["version"], bool) or not isinstance(row["version"], int):
        raise TypeError(f"Corrupt RuleMemory record {index}: invalid version type")
    if row["version"] < 1:
        raise ValueError(f"Corrupt RuleMemory record {index}: invalid version")
    if not isinstance(row["deprecated"], bool):
        raise TypeError(f"Corrupt RuleMemory record {index}: deprecated must be bool")
    if not isinstance(row["status"], str):
        raise TypeError(f"Corrupt RuleMemory record {index}: status must be string")
    evidence = row["verification_evidence"]
    if evidence is not None and not isinstance(evidence, dict):
        raise ValueError(
            f"Corrupt RuleMemory record {index}: evidence must be object/null"
        )
    specification = _specification_from_json(row["specification"], index)
    try:
        status = VerificationStatus(row["status"])
    except ValueError as exc:
        raise ValueError(f"Corrupt RuleMemory record {index}: invalid status") from exc
    return RuleRecord(
        rule_id=row["rule_id"],
        program_json=row["program_json"],
        semantic_hash=row["semantic_hash"],
        status=status,
        specification=specification,
        verification_evidence=dict(evidence) if evidence is not None else None,
        version=row["version"],
        deprecated=row["deprecated"],
        provenance=row["provenance"],
    )


def _specification_from_json(value: Any, index: int) -> ProgramSpecification:
    expected = {item.name for item in fields(ProgramSpecification)}
    if not isinstance(value, dict):
        raise TypeError(f"Corrupt RuleMemory record {index}: missing specification")
    _exact_keys(value, expected, f"RuleMemory specification {index}")
    simple = (
        "inputs",
        "outputs",
        "drops",
        "preserve",
        "terminate_when_empty",
        "allowed_variables",
        "allowed_primitives",
    )
    converted: dict[str, Any] = {}
    for name in simple:
        items = value[name]
        if not isinstance(items, list) or any(
            not isinstance(item, str) for item in items
        ):
            raise ValueError(
                f"Corrupt RuleMemory record {index}: {name} must be string array"
            )
        converted[name] = tuple(items)
    transfers = _strict_rows(value["transfers"], 2, index, "transfers")
    if any(any(not isinstance(item, str) for item in row) for row in transfers):
        raise ValueError(f"Corrupt RuleMemory record {index}: invalid transfer")
    phases = _strict_rows(value["phase_constraints"], 3, index, "phase_constraints")
    for action, source, destination in phases:
        if not isinstance(action, str) or not isinstance(source, str):
            raise TypeError(f"Corrupt RuleMemory record {index}: invalid phase")
        if destination is not None and not isinstance(destination, str):
            raise ValueError(f"Corrupt RuleMemory record {index}: invalid destination")
    if not isinstance(value["unsupported"], bool):
        raise TypeError(f"Corrupt RuleMemory record {index}: unsupported must be bool")
    return ProgramSpecification(
        **converted,
        transfers=transfers,
        phase_constraints=phases,
        unsupported=value["unsupported"],
    )


def _strict_rows(value: Any, arity: int, index: int, name: str) -> tuple[tuple, ...]:
    if not isinstance(value, list):
        raise TypeError(f"Corrupt RuleMemory record {index}: {name} must be array")
    result = []
    for row in value:
        if not isinstance(row, list) or len(row) != arity:
            raise ValueError(f"Corrupt RuleMemory record {index}: malformed {name}")
        result.append(tuple(row))
    return tuple(result)


def _validate_status_evidence(
    status: VerificationStatus,
    specification: ProgramSpecification,
    evidence: dict[str, Any] | None,
) -> None:
    if status != VerificationStatus.PROPERTY_VERIFIED:
        return
    if not specification.is_full():
        raise ValueError("PROPERTY_VERIFIED requires a non-empty ProgramSpecification")
    if not evidence or evidence.get("accepted") is not True:
        raise ValueError("PROPERTY_VERIFIED requires verifier evidence")
    if evidence.get("status") != str(VerificationStatus.PROPERTY_VERIFIED):
        raise ValueError("PROPERTY_VERIFIED evidence has incompatible status")


def _exact_keys(row: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(row)
    if actual != expected:
        raise ValueError(
            f"{label} schema mismatch: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _evidence_dict(
    evidence: VerificationResult | dict[str, Any] | None,
) -> dict[str, Any] | None:
    if evidence is None:
        return None
    if isinstance(evidence, VerificationResult):
        return {
            "accepted": evidence.accepted,
            "status": str(evidence.status),
            "reason": evidence.reason,
            "counterexample": evidence.counterexample,
        }
    result = dict(evidence)
    if "status" in result:
        result["status"] = str(result["status"])
    return result
