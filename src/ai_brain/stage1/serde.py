"""Strict JSON serialization for Stage-1 workflow artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, TypeVar

from ai_brain.rules.specifications import ProgramSpecification
from ai_brain.stage1.models import (
    ApprovalDecision,
    ApprovalEnvelope,
    IssueCode,
    ProposalIssue,
    ProposalStatus,
    RuleProposal,
    SemanticFamily,
    SourceKind,
    VerifiedCandidateBundle,
)

T = TypeVar("T")


def write_artifact(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object in {path}")
    return value


def proposal_from_json(row: dict[str, Any]) -> RuleProposal:
    specification = row.get("specification")
    return RuleProposal(
        proposal_id=str(row["proposal_id"]),
        source_kind=SourceKind(row["source_kind"]),
        original_input=str(row["original_input"]),
        language=row.get("language"),
        status=ProposalStatus(row["status"]),
        specification=ProgramSpecification(**specification) if specification else None,
        semantic_family=(
            SemanticFamily(row["semantic_family"])
            if row.get("semantic_family") is not None
            else None
        ),
        issues=tuple(
            ProposalIssue(IssueCode(item["code"]), item["field"], item["message"])
            for item in row.get("issues", ())
        ),
        parser_name=str(row.get("parser_name", "")),
        parser_version=str(row.get("parser_version", "")),
        specification_hash=row.get("specification_hash"),
        provenance=tuple(row.get("provenance", ())),
        created_at=str(row.get("created_at", "")),
        revision=int(row.get("revision", 1)),
    )


def candidate_from_json(row: dict[str, Any]) -> VerifiedCandidateBundle:
    return VerifiedCandidateBundle(**row)


def approval_from_json(row: dict[str, Any]) -> ApprovalEnvelope:
    return ApprovalEnvelope(**{**row, "decision": ApprovalDecision(row["decision"])})
