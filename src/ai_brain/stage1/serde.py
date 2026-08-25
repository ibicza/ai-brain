"""Strict JSON serialization for trusted Stage-1 workflow artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path
from typing import Any

from ai_brain.rules.statuses import VerificationStatus
from ai_brain.stage1.models import (
    ApprovalDecision,
    ApprovalEnvelope,
    ExecutionFailureCode,
    ExecutionLimits,
    ExecutionResult,
    InstalledRuleReceipt,
    IssueCode,
    ProposalIssue,
    ProposalStatus,
    RuleProposal,
    SemanticFamily,
    SourceKind,
    VerifiedCandidateBundle,
    VerifiedReviewArtifact,
    content_hash,
    specification_hash,
    verified_review_content_hash,
)
from ai_brain.stage1.specifications import specification_from_dict
from ai_brain.stage1.version import WORKFLOW_ARTIFACT_SCHEMA_VERSION

_SHA256 = re.compile(r"[0-9a-f]{64}")


def write_artifact(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON artifact {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object in {path}")
    return value


def proposal_from_json(row: dict[str, Any]) -> RuleProposal:
    _exact_keys(row, RuleProposal, "RuleProposal")
    _schema(row)
    specification_row = row["specification"]
    if specification_row is not None and not isinstance(specification_row, dict):
        raise TypeError("RuleProposal.specification must be an object or null")
    specification = (
        specification_from_dict(specification_row)
        if specification_row is not None
        else None
    )
    declared_hash = _optional_hash(row, "specification_hash")
    if specification is not None:
        if declared_hash != specification_hash(specification):
            raise ValueError("RuleProposal.specification_hash mismatch")
    elif declared_hash is not None:
        raise ValueError("RuleProposal without specification must not have its hash")
    family_value = row["semantic_family"]
    if family_value is not None and not isinstance(family_value, str):
        raise TypeError("RuleProposal.semantic_family must be a string or null")
    issues_value = row["issues"]
    if not isinstance(issues_value, list):
        raise TypeError("RuleProposal.issues must be an array")
    issues: list[ProposalIssue] = []
    for index, item in enumerate(issues_value):
        if not isinstance(item, dict):
            raise TypeError(f"RuleProposal.issues[{index}] must be an object")
        _exact_named_keys(item, {"code", "field", "message"}, "ProposalIssue")
        issues.append(
            ProposalIssue(
                IssueCode(_string(item, "code")),
                _string(item, "field"),
                _string(item, "message"),
            )
        )
    provenance_value = row["provenance"]
    if not isinstance(provenance_value, list) or any(
        not isinstance(item, dict) for item in provenance_value
    ):
        raise TypeError("RuleProposal.provenance must be an array of objects")
    _json_value(provenance_value, "RuleProposal.provenance")
    return RuleProposal(
        proposal_id=_string(row, "proposal_id"),
        source_kind=SourceKind(_string(row, "source_kind")),
        original_input=_string(row, "original_input", allow_empty=True),
        language=_optional_string(row, "language"),
        status=ProposalStatus(_string(row, "status")),
        specification=specification,
        semantic_family=SemanticFamily(family_value) if family_value else None,
        issues=tuple(issues),
        parser_name=_string(row, "parser_name", allow_empty=True),
        parser_version=_string(row, "parser_version", allow_empty=True),
        specification_hash=declared_hash,
        provenance=tuple(provenance_value),
        created_at=_timestamp(row, "created_at"),
        revision=_positive_int(row, "revision"),
        schema_version=row["schema_version"],
    )


def candidate_from_json(row: dict[str, Any]) -> VerifiedCandidateBundle:
    _exact_keys(row, VerifiedCandidateBundle, "VerifiedCandidateBundle")
    _schema(row)
    evidence = _object(row, "verification_evidence")
    _json_value(evidence, "VerifiedCandidateBundle.verification_evidence")
    candidate_dsl = _string(row, "candidate_dsl")
    candidate_hash = _hash(row, "candidate_hash")
    evidence_hash = _hash(row, "evidence_hash")
    if content_hash(candidate_dsl) != candidate_hash:
        raise ValueError("VerifiedCandidateBundle.candidate_hash mismatch")
    if content_hash(evidence) != evidence_hash:
        raise ValueError("VerifiedCandidateBundle.evidence_hash mismatch")
    verification_status = VerificationStatus(_string(row, "verification_status"))
    return VerifiedCandidateBundle(
        proposal_id=_string(row, "proposal_id"),
        proposal_hash=_hash(row, "proposal_hash"),
        specification_hash=_hash(row, "specification_hash"),
        candidate_dsl=candidate_dsl,
        candidate_hash=candidate_hash,
        verification_status=str(verification_status),
        verification_evidence=evidence,
        evidence_hash=evidence_hash,
        compiler_name=_string(row, "compiler_name"),
        created_at=_timestamp(row, "created_at"),
        schema_version=row["schema_version"],
    )


def review_from_json(row: dict[str, Any]) -> VerifiedReviewArtifact:
    _exact_keys(row, VerifiedReviewArtifact, "VerifiedReviewArtifact")
    _schema(row)
    evidence = _object(row, "verification_evidence")
    _json_value(evidence, "VerifiedReviewArtifact.verification_evidence")
    static_result = _object(row, "static_verification_result")
    abstract_result = _object(row, "abstract_verification_result")
    property_result = _object(row, "property_verification_result")
    _json_value(static_result, "VerifiedReviewArtifact.static_verification_result")
    _json_value(abstract_result, "VerifiedReviewArtifact.abstract_verification_result")
    _json_value(property_result, "VerifiedReviewArtifact.property_verification_result")
    artifact = VerifiedReviewArtifact(
        proposal_id=_string(row, "proposal_id"),
        proposal_hash=_hash(row, "proposal_hash"),
        specification_hash=_hash(row, "specification_hash"),
        original_input=_string(row, "original_input", allow_empty=True),
        semantic_effect_summary=_string(row, "semantic_effect_summary"),
        changed_registers=_string_array(row, "changed_registers"),
        preserved_registers=_string_array(row, "preserved_registers"),
        termination_condition=_string_array(row, "termination_condition"),
        ordered_phases=_phase_rows(row["ordered_phases"]),
        compiler_name=_string(row, "compiler_name"),
        candidate_dsl=_string(row, "candidate_dsl"),
        candidate_hash=_hash(row, "candidate_hash"),
        static_verification_result=static_result,
        abstract_verification_result=abstract_result,
        property_verification_result=property_result,
        verification_evidence=evidence,
        evidence_hash=_hash(row, "evidence_hash"),
        stage1_version=_string(row, "stage1_version"),
        warnings=_string_array(row, "warnings"),
        created_at=_timestamp(row, "created_at"),
        review_hash=_hash(row, "review_hash"),
        schema_version=row["schema_version"],
    )
    if content_hash(artifact.candidate_dsl) != artifact.candidate_hash:
        raise ValueError("VerifiedReviewArtifact.candidate_hash mismatch")
    if content_hash(artifact.verification_evidence) != artifact.evidence_hash:
        raise ValueError("VerifiedReviewArtifact.evidence_hash mismatch")
    if verified_review_content_hash(artifact) != artifact.review_hash:
        raise ValueError("VerifiedReviewArtifact.review_hash mismatch")
    return artifact


def approval_from_json(row: dict[str, Any]) -> ApprovalEnvelope:
    _exact_keys(row, ApprovalEnvelope, "ApprovalEnvelope")
    _schema(row)
    return ApprovalEnvelope(
        decision=ApprovalDecision(_string(row, "decision")),
        identity=_string(row, "identity"),
        identity_type=_string(row, "identity_type"),
        timestamp=_timestamp(row, "timestamp"),
        proposal_id=_string(row, "proposal_id"),
        proposal_hash=_hash(row, "proposal_hash"),
        specification_hash=_hash(row, "specification_hash"),
        candidate_hash=_hash(row, "candidate_hash"),
        evidence_hash=_hash(row, "evidence_hash"),
        verified_review_hash=_hash(row, "verified_review_hash"),
        stage1_version=_string(row, "stage1_version"),
        schema_version=row["schema_version"],
    )


def receipt_from_json(row: dict[str, Any]) -> InstalledRuleReceipt:
    _exact_keys(row, InstalledRuleReceipt, "InstalledRuleReceipt")
    _schema(row)
    return InstalledRuleReceipt(
        proposal_id=_string(row, "proposal_id"),
        proposal_hash=_hash(row, "proposal_hash"),
        installed_rule_id=_string(row, "installed_rule_id"),
        rule_semantic_hash=_hash(row, "rule_semantic_hash"),
        specification_hash=_hash(row, "specification_hash"),
        candidate_hash=_hash(row, "candidate_hash"),
        evidence_hash=_hash(row, "evidence_hash"),
        verified_review_hash=_hash(row, "verified_review_hash"),
        approval_hash=_hash(row, "approval_hash"),
        rule_memory_schema_version=_positive_int(row, "rule_memory_schema_version"),
        stage1_version=_string(row, "stage1_version"),
        installation_timestamp=_timestamp(row, "installation_timestamp"),
        schema_version=row["schema_version"],
    )


def execution_result_from_json(row: dict[str, Any]) -> ExecutionResult:
    _exact_keys(row, ExecutionResult, "ExecutionResult")
    _schema(row)
    limits_row = _object(row, "limits")
    _exact_keys(limits_row, ExecutionLimits, "ExecutionLimits")
    for name in (
        "max_register_value",
        "max_total_units",
        "max_execution_steps",
        "max_trace_actions",
    ):
        _positive_int(limits_row, name)
    for name in ("capture_trace", "fail_on_trace_overflow"):
        if not isinstance(limits_row[name], bool):
            raise TypeError(f"ExecutionLimits.{name} must be bool")
    _string(limits_row, "version")
    final_state = row["final_state"]
    if final_state is not None:
        final_state = _state(final_state, "ExecutionResult.final_state")
    for name in ("halted", "trace_requested", "trace_truncated"):
        if not isinstance(row[name], bool):
            raise TypeError(f"ExecutionResult.{name} must be bool")
    failure_reason = _optional_string(row, "failure_reason")
    if failure_reason is not None:
        failure_reason = str(ExecutionFailureCode(failure_reason))
    result = ExecutionResult(
        rule_id=_string(row, "rule_id"),
        proposal_id=_string(row, "proposal_id", allow_empty=True),
        initial_state=_state(row["initial_state"], "ExecutionResult.initial_state"),
        final_state=final_state,
        executed_steps=_nonnegative_int(row, "executed_steps"),
        halted=row["halted"],
        trace_requested=row["trace_requested"],
        trace_truncated=row["trace_truncated"],
        captured_actions=_string_array(row, "captured_actions"),
        action_stream_hash=_hash(row, "action_stream_hash"),
        execution_hash=_hash(row, "execution_hash"),
        limits_version=_string(row, "limits_version"),
        limits=dict(limits_row),
        failure_reason=failure_reason,
        schema_version=row["schema_version"],
    )
    if result.limits_version != limits_row["version"]:
        raise ValueError("ExecutionResult limits version mismatch")
    if result.final_state is not None:
        core = {
            "rule_id": result.rule_id,
            "proposal_id": result.proposal_id,
            "initial_state_hash": content_hash(result.initial_state),
            "final_state_hash": content_hash(result.final_state),
            "executed_steps": result.executed_steps,
            "halted": result.halted,
            "trace_requested": result.trace_requested,
            "trace_truncated": result.trace_truncated,
            "action_stream_hash": result.action_stream_hash,
            "limits": result.limits,
            "failure_reason": result.failure_reason,
        }
        if content_hash(core) != result.execution_hash:
            raise ValueError("ExecutionResult.execution_hash mismatch")
    return result


def _exact_keys(row: dict[str, Any], artifact_type: type, label: str) -> None:
    _exact_named_keys(row, {item.name for item in fields(artifact_type)}, label)


def _exact_named_keys(row: dict[str, Any], expected: set[str], label: str) -> None:
    if not isinstance(row, dict):
        raise TypeError(f"{label} must be a JSON object")
    actual = set(row)
    if actual != expected:
        raise ValueError(
            f"{label} schema mismatch: missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}"
        )


def _schema(row: dict[str, Any]) -> None:
    value = row["schema_version"]
    if isinstance(value, bool) or value != WORKFLOW_ARTIFACT_SCHEMA_VERSION:
        raise ValueError("Unsupported workflow artifact schema_version")


def _string(row: dict[str, Any], name: str, *, allow_empty: bool = False) -> str:
    value = row[name]
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not allow_empty and not value.strip():
        raise ValueError(f"{name} must not be blank")
    return value


def _optional_string(row: dict[str, Any], name: str) -> str | None:
    value = row[name]
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{name} must be a string or null")
    return value


def _positive_int(row: dict[str, Any], name: str) -> int:
    value = row[name]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TypeError(f"{name} must be a positive integer")
    return value


def _nonnegative_int(row: dict[str, Any], name: str) -> int:
    value = row[name]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"{name} must be a non-negative integer")
    return value


def _hash(row: dict[str, Any], name: str) -> str:
    value = _string(row, name)
    if _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    return value


def _optional_hash(row: dict[str, Any], name: str) -> str | None:
    return None if row[name] is None else _hash(row, name)


def _timestamp(row: dict[str, Any], name: str) -> str:
    value = _string(row, name)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value


def _object(row: dict[str, Any], name: str) -> dict[str, Any]:
    value = row[name]
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be a JSON object")
    return dict(value)


def _string_array(row: dict[str, Any], name: str) -> tuple[str, ...]:
    value = row[name]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{name} must be an array of strings")
    return tuple(value)


def _phase_rows(value: Any) -> tuple[tuple[str, str, str | None], ...]:
    if not isinstance(value, list):
        raise TypeError("ordered_phases must be an array")
    result: list[tuple[str, str, str | None]] = []
    for index, item in enumerate(value):
        if not isinstance(item, list) or len(item) != 3:
            raise TypeError(f"ordered_phases[{index}] must be a three-item array")
        action, source, destination = item
        if not isinstance(action, str) or not isinstance(source, str):
            raise TypeError(f"ordered_phases[{index}] action/source must be strings")
        if destination is not None and not isinstance(destination, str):
            raise TypeError(f"ordered_phases[{index}] destination must be string/null")
        result.append((action, source, destination))
    return tuple(result)


def _state(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != {"R0", "R1", "R2", "R3"}:
        raise TypeError(f"{label} must contain exactly R0, R1, R2, and R3")
    if any(
        isinstance(item, bool) or not isinstance(item, int) for item in value.values()
    ):
        raise TypeError(f"{label} values must be integers")
    return dict(value)


def _json_value(value: Any, label: str) -> None:
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, list):
        for item in value:
            _json_value(item, label)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _json_value(item, label)
        return
    raise TypeError(f"{label} contains a non-JSON value")
