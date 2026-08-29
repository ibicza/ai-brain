from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from ai_brain.stage2.education.models import ActorIdentityType
from ai_brain.stage2.facts.canonical import content_hash, normalize_datetime
from ai_brain.stage3.knowledge_ir.version import PACK_APPROVAL_SCHEMA_VERSION


class PackApprovalDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NEEDS_NEW_CAPABILITY = "NEEDS_NEW_CAPABILITY"


@dataclass(frozen=True)
class DomainPackApprovalEnvelope:
    pack_hash: str
    knowledge_ir_schema: int
    concept_graph_hash: str
    source_binding_hashes: tuple[str, ...]
    capability_resolution_receipt_hashes: tuple[str, ...]
    validation_report_hash: str
    evaluation_manifest_hash: str
    reviewer_identity: str
    reviewer_type: ActorIdentityType
    decision: PackApprovalDecision
    policy_version: str
    timestamp: str
    schema_version: int
    approval_hash: str


def approve_pack(**values) -> DomainPackApprovalEnvelope:
    values.setdefault("schema_version", PACK_APPROVAL_SCHEMA_VERSION)
    value = DomainPackApprovalEnvelope(**values, approval_hash="")
    body = asdict(value)
    body.pop("approval_hash")
    result = DomainPackApprovalEnvelope(**{**body, "approval_hash": content_hash(body)})
    verify_approval(result)
    return result


def verify_approval(value: DomainPackApprovalEnvelope) -> None:
    if value.schema_version != PACK_APPROVAL_SCHEMA_VERSION:
        raise ValueError("unsupported pack approval schema")
    if value.decision is PackApprovalDecision.APPROVE and (
        value.reviewer_type is ActorIdentityType.MODEL
        or not value.reviewer_identity.strip()
    ):
        raise ValueError("MODEL or blank reviewer cannot approve a trusted pack")
    normalize_datetime(value.timestamp)
    body = asdict(value)
    digest = body.pop("approval_hash")
    if content_hash(body) != digest:
        raise ValueError("pack approval hash mismatch")
