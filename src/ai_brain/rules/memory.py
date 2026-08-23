"""RuleMemory with explicit verification-status write policy."""

from __future__ import annotations

import json
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
        semantic_hash = program.semantic_hash(alpha=True, order_insensitive=True)
        for record in self.records.values():
            if not record.deprecated and record.semantic_hash == semantic_hash:
                raise ValueError(f"Duplicate semantic rule {semantic_hash}")
        record = RuleRecord(
            rule_id=f"rule-{len(self.records) + 1:05d}-{semantic_hash[:8]}",
            program_json=render_canonical_program(program, default_binding()),
            semantic_hash=semantic_hash,
            status=status,
            specification=specification,
            verification_evidence=evidence,
            provenance=provenance,
        )
        self.records[record.rule_id] = record
        return record

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
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
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> RuleMemory:
        data = json.loads(path.read_text(encoding="utf-8"))
        memory = cls(
            allow_hypothesis_identified=bool(
                data.get("allow_hypothesis_identified", False)
            )
        )
        if data.get("schema_version") != 1:
            raise ValueError("Unsupported RuleMemory schema")
        for row in data["records"]:
            row["status"] = VerificationStatus(row["status"])
            row["specification"] = ProgramSpecification(**row["specification"])
            record = RuleRecord(**row)
            memory.records[record.rule_id] = record
        return memory

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
