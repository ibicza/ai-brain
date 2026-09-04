"""Wall-clock-independent Java pack identity and separate audit receipt."""

from __future__ import annotations

from dataclasses import dataclass

from ai_brain.stage2.facts.canonical import content_hash, normalize_datetime

JAVA_SEMANTIC_COMPILATION_EPOCH = "1970-01-01T00:00:00Z"
JAVA_COMPILATION_IDENTITY_POLICY = "m336.semantic-compilation-identity.v1"


@dataclass(frozen=True)
class JavaCompilationAuditReceipt:
    bundle_hash: str
    compiler_identity_hash: str
    audit_timestamp: str
    policy_version: str
    semantic_receipt_hash: str
    audit_receipt_hash: str


def build_java_compilation_audit_receipt(
    *, bundle_hash: str, compiler_identity_hash: str, audit_timestamp: str
) -> JavaCompilationAuditReceipt:
    """Keep event time visible without permitting it to affect semantic identity."""

    normalize_datetime(audit_timestamp)
    semantic = {
        "bundle_hash": bundle_hash,
        "compiler_identity_hash": compiler_identity_hash,
        "policy_version": JAVA_COMPILATION_IDENTITY_POLICY,
    }
    body = {
        **semantic,
        "audit_timestamp": audit_timestamp,
        "semantic_receipt_hash": content_hash(semantic),
    }
    return JavaCompilationAuditReceipt(**body, audit_receipt_hash=content_hash(body))
