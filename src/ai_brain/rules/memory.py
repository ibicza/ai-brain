"""RuleMemory with explicit verification-status write policy."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
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
from ai_brain.rules.verifier import VerificationResult


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
    def __init__(self, *, allow_hypothesis_identified: bool = False) -> None:
        self.records: dict[str, RuleRecord] = {}
        self.allow_hypothesis_identified = allow_hypothesis_identified

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
        if status == VerificationStatus.PROPERTY_VERIFIED:
            if not specification.is_full():
                raise ValueError(
                    "PROPERTY_VERIFIED requires a non-empty ProgramSpecification"
                )
            if not evidence or not evidence.get("accepted"):
                raise ValueError("PROPERTY_VERIFIED requires verifier evidence")
            if evidence.get("status") != VerificationStatus.PROPERTY_VERIFIED:
                raise ValueError("PROPERTY_VERIFIED evidence has incompatible status")
        # Logical roles are externally bound to R0-R3 and phase order is
        # observable. Renamed or reordered programs are distinct installed rules.
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
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "schema_version": 1,
            "allow_hypothesis_identified": self.allow_hypothesis_identified,
            "records": [
                {
                    **asdict(record),
                    "status": str(record.status),
                    "specification": asdict(record.specification),
                }
                for record in self.records.values()
            ],
        }
        canonical = json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        import hashlib

        payload = {
            **body,
            "content_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        }
        rendered = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        if path.exists():
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        file_descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(
                file_descriptor, "w", encoding="utf-8", newline="\n"
            ) as stream:
                stream.write(rendered)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @classmethod
    def load(cls, path: Path) -> RuleMemory:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Corrupt RuleMemory: {exc}") from exc
        if not isinstance(data, dict):
            raise TypeError("Corrupt RuleMemory: root must be an object")
        if data.get("schema_version") != 1:
            raise ValueError("Unsupported RuleMemory schema")
        checksum = data.pop("content_sha256", None)
        import hashlib

        canonical = json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        if (
            checksum is not None
            and hashlib.sha256(canonical.encode("utf-8")).hexdigest() != checksum
        ):
            raise ValueError("Corrupt RuleMemory: checksum mismatch")
        memory = cls(
            allow_hypothesis_identified=bool(
                data.get("allow_hypothesis_identified", False)
            )
        )
        records = data.get("records")
        if not isinstance(records, list):
            raise TypeError("Corrupt RuleMemory: records must be a list")
        active_hashes: set[str] = set()
        for source_row in records:
            row = dict(source_row)
            try:
                row["status"] = VerificationStatus(row["status"])
                row["specification"] = ProgramSpecification(**row["specification"])
                record = RuleRecord(**row)
                program = parse_canonical_dsl(record.program_json)[0]
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Corrupt RuleMemory record: {exc}") from exc
            if record.rule_id in memory.records:
                raise ValueError(f"Corrupt RuleMemory: duplicate id {record.rule_id}")
            if not memory.can_store(record.status):
                raise ValueError(
                    f"Corrupt RuleMemory: rejected status {record.rule_id}"
                )
            if record.version < 1:
                raise ValueError(
                    f"Corrupt RuleMemory: invalid version {record.rule_id}"
                )
            if record.status == VerificationStatus.PROPERTY_VERIFIED and (
                not record.specification.is_full()
                or not record.verification_evidence
                or not record.verification_evidence.get("accepted")
                or record.verification_evidence.get("status")
                != VerificationStatus.PROPERTY_VERIFIED
            ):
                raise ValueError(
                    f"Corrupt RuleMemory: invalid evidence {record.rule_id}"
                )
            if (
                program.semantic_hash(alpha=False, order_insensitive=False)
                != record.semantic_hash
            ):
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
            return cls.load(path)
        except (TypeError, ValueError):
            backup = path.with_suffix(path.suffix + ".bak")
            if not backup.exists():
                raise
            return cls.load(backup)

    def deprecate(self, rule_id: str) -> RuleRecord:
        from dataclasses import replace

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
