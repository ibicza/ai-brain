"""Generic, deterministic source-artifact provenance and qualification types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ai_brain.stage2.facts.canonical import content_hash

SOURCE_ARTIFACT_PROVENANCE_SCHEMA_VERSION = 1


class LicenseEvidenceMode(StrEnum):
    EMBEDDED_EXACT_LICENSE = "EMBEDDED_EXACT_LICENSE"
    POM_PLUS_IMMUTABLE_SCM_LICENSE = "POM_PLUS_IMMUTABLE_SCM_LICENSE"
    EMBEDDED_AND_SCM_CORROBORATED = "EMBEDDED_AND_SCM_CORROBORATED"
    POM_DECLARATION_ONLY = "POM_DECLARATION_ONLY"
    CONFLICTING_LICENSE_EVIDENCE = "CONFLICTING_LICENSE_EVIDENCE"
    NO_LICENSE_EVIDENCE = "NO_LICENSE_EVIDENCE"


class ProvenanceStatus(StrEnum):
    VERIFIED = "VERIFIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CONFLICT = "CONFLICT"
    INELIGIBLE = "INELIGIBLE"
    UNRESOLVED = "UNRESOLVED"
    BLOCKED = "BLOCKED"


class SourceCorrespondenceStatus(StrEnum):
    EXACT_MATCH = "EXACT_MATCH"
    PATH_RELOCATED_EXACT_CONTENT = "PATH_RELOCATED_EXACT_CONTENT"
    GENERATED_WITH_VERIFIED_PROVENANCE = "GENERATED_WITH_VERIFIED_PROVENANCE"
    UNMATCHED = "UNMATCHED"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"


class CandidateRequirement(StrEnum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"


class CandidateQualificationStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INELIGIBLE_PROVENANCE = "INELIGIBLE_PROVENANCE"
    INELIGIBLE_LICENSE = "INELIGIBLE_LICENSE"
    INELIGIBLE_RELEASE = "INELIGIBLE_RELEASE"
    DENYLISTED = "DENYLISTED"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class SourceArtifactCoordinate:
    repository: str
    namespace: str
    name: str
    version: str
    classifier: str
    extension: str
    canonical_repository_path: str


@dataclass(frozen=True)
class ArtifactDigestEvidence:
    downloaded_bytes_sha256: str
    sidecar_sha256: str | None
    sidecar_verified: bool
    detached_signature_url: str | None
    artifact_size: int


@dataclass(frozen=True)
class RepositoryMetadataEvidence:
    repository_host: str
    requested_url: str
    final_url: str
    redirect_chain: tuple[str, ...]
    content_length: int
    media_type: str
    network_receipt_hash: str


@dataclass(frozen=True)
class LicenseClaim:
    spdx_identifier: str
    declaration_source: str
    declared_name: str
    declaration_hash: str


@dataclass(frozen=True)
class LicenseTextEvidence:
    evidence_path: str
    raw_text_sha256: str
    normalized_text_sha256: str
    canonical_license_sha256: str
    exact_match: bool


@dataclass(frozen=True)
class ScmRevisionEvidence:
    repository_url: str
    requested_ref: str
    immutable_commit: str
    tag_to_commit_verified: bool
    source_tree_hash: str


@dataclass(frozen=True)
class SourceTreeCorrespondenceEntry:
    artifact_path: str
    repository_path: str | None
    raw_sha256: str
    canonical_sha256: str
    status: SourceCorrespondenceStatus
    entry_hash: str


@dataclass(frozen=True)
class SourceTreeCorrespondence:
    entries: tuple[SourceTreeCorrespondenceEntry, ...]
    exact_match_count: int
    relocated_match_count: int
    generated_match_count: int
    unmatched_count: int
    ambiguous_count: int
    eligible_entry_count: int
    correspondence_hash: str


@dataclass(frozen=True)
class ProvenanceAuditEvent:
    acquired_at: str
    host: str
    acquisition_run_id: str
    network_receipt_hashes: tuple[str, ...]
    audit_hash: str


@dataclass(frozen=True)
class SourceArtifactProvenanceEnvelope:
    schema_version: int
    coordinate: SourceArtifactCoordinate
    artifact_digest: ArtifactDigestEvidence
    repository_metadata: RepositoryMetadataEvidence
    pom_digest: ArtifactDigestEvidence
    license_claims: tuple[LicenseClaim, ...]
    license_texts: tuple[LicenseTextEvidence, ...]
    license_evidence_mode: LicenseEvidenceMode
    license_status: ProvenanceStatus
    scm_revision: ScmRevisionEvidence | None
    correspondence: SourceTreeCorrespondence | None
    conflicts: tuple[str, ...]
    semantic_identity_hash: str
    audit_event: ProvenanceAuditEvent
    envelope_hash: str


@dataclass(frozen=True)
class ArtifactQualificationDecision:
    coordinate: SourceArtifactCoordinate
    requirement: CandidateRequirement
    status: CandidateQualificationStatus
    evidence_mode: LicenseEvidenceMode
    reasons: tuple[str, ...]
    eligible_root: str | None
    provenance_identity_hash: str
    decision_hash: str


def build_provenance_audit_event(
    *, acquired_at: str, host: str, acquisition_run_id: str, network_receipt_hashes
) -> ProvenanceAuditEvent:
    body = {
        "acquired_at": acquired_at,
        "host": host,
        "acquisition_run_id": acquisition_run_id,
        "network_receipt_hashes": tuple(sorted(network_receipt_hashes)),
    }
    return ProvenanceAuditEvent(**body, audit_hash=content_hash(body))


def build_provenance_envelope(**values) -> SourceArtifactProvenanceEnvelope:
    """Bind semantic evidence separately from host/time/run audit facts."""

    semantic = {
        key: values[key]
        for key in (
            "schema_version",
            "coordinate",
            "artifact_digest",
            "repository_metadata",
            "pom_digest",
            "license_claims",
            "license_texts",
            "license_evidence_mode",
            "license_status",
            "scm_revision",
            "correspondence",
            "conflicts",
        )
    }
    semantic_identity_hash = content_hash(semantic)
    body = {**semantic, "semantic_identity_hash": semantic_identity_hash}
    envelope_hash = content_hash({**body, "audit_event": values["audit_event"]})
    return SourceArtifactProvenanceEnvelope(
        **body, audit_event=values["audit_event"], envelope_hash=envelope_hash
    )


def qualify_artifact(
    envelope: SourceArtifactProvenanceEnvelope,
    *,
    requirement: CandidateRequirement,
    eligible_root: str | None,
    denied: bool = False,
    release_compatible: bool = True,
) -> ArtifactQualificationDecision:
    reasons = []
    if denied:
        status = CandidateQualificationStatus.DENYLISTED
        reasons.append("PERMANENT_DISCLOSED_MATERIAL_DENYLIST")
    elif envelope.conflicts or envelope.license_status is ProvenanceStatus.CONFLICT:
        status = CandidateQualificationStatus.CONFLICT
        reasons.extend(envelope.conflicts or ("CONFLICTING_LICENSE_EVIDENCE",))
    elif not release_compatible:
        status = CandidateQualificationStatus.INELIGIBLE_RELEASE
        reasons.append("INELIGIBLE_RELEASE")
    elif envelope.license_status is ProvenanceStatus.REVIEW_REQUIRED:
        status = CandidateQualificationStatus.REVIEW_REQUIRED
        reasons.append("LICENSE_EVIDENCE_REQUIRES_REVIEW")
    elif envelope.license_status is not ProvenanceStatus.VERIFIED:
        status = CandidateQualificationStatus.INELIGIBLE_LICENSE
        reasons.append("LICENSE_EVIDENCE_NOT_VERIFIED")
    elif not envelope.artifact_digest.sidecar_verified:
        status = CandidateQualificationStatus.INELIGIBLE_PROVENANCE
        reasons.append("ARTIFACT_DIGEST_NOT_VERIFIED")
    elif envelope.license_evidence_mode in {
        LicenseEvidenceMode.POM_PLUS_IMMUTABLE_SCM_LICENSE,
        LicenseEvidenceMode.EMBEDDED_AND_SCM_CORROBORATED,
    } and (
        envelope.scm_revision is None
        or not envelope.scm_revision.tag_to_commit_verified
        or envelope.correspondence is None
        or envelope.correspondence.unmatched_count
        or envelope.correspondence.ambiguous_count
    ):
        status = CandidateQualificationStatus.INELIGIBLE_PROVENANCE
        reasons.append("SOURCE_REVISION_LINK_INCOMPLETE")
    else:
        status = CandidateQualificationStatus.ELIGIBLE
        reasons.append("COMPLETE_FROZEN_EVIDENCE")
    body = {
        "coordinate": envelope.coordinate,
        "requirement": requirement,
        "status": status,
        "evidence_mode": envelope.license_evidence_mode,
        "reasons": tuple(reasons),
        "eligible_root": eligible_root
        if status is CandidateQualificationStatus.ELIGIBLE
        else None,
        "provenance_identity_hash": envelope.semantic_identity_hash,
    }
    return ArtifactQualificationDecision(**body, decision_hash=content_hash(body))


def qualify_candidate_set(decisions, *, minimum_eligible_roots: int) -> dict:
    ordered = tuple(
        sorted(decisions, key=lambda item: item.coordinate.canonical_repository_path)
    )
    required_failures = tuple(
        item.coordinate.canonical_repository_path
        for item in ordered
        if item.requirement is CandidateRequirement.REQUIRED
        and item.status is not CandidateQualificationStatus.ELIGIBLE
    )
    eligible = tuple(
        item for item in ordered if item.status is CandidateQualificationStatus.ELIGIBLE
    )
    ready = not required_failures and len(eligible) >= minimum_eligible_roots
    body = {
        "decisions": ordered,
        "eligible_roots": tuple(item.eligible_root for item in eligible),
        "required_failures": required_failures,
        "minimum_eligible_roots": minimum_eligible_roots,
        "selector_invocation_count": 1 if ready else 0,
        "selector_rerun_count": 0,
        "metrics_used_for_qualification": 0,
        "status": "READY_FOR_SINGLE_SELECTION" if ready else "BLOCKED",
    }
    return {**body, "qualification_set_hash": content_hash(body)}


def execute_candidate_qualification(
    candidates,
    *,
    qualifier,
    selector,
    minimum_eligible_roots: int,
):
    """Qualify every frozen candidate before a single selector invocation."""

    frozen_candidates = tuple(candidates)
    decisions = tuple(qualifier(item) for item in frozen_candidates)
    if len(decisions) != len(frozen_candidates):
        raise ValueError("every frozen candidate requires a qualification receipt")
    qualification = qualify_candidate_set(
        decisions, minimum_eligible_roots=minimum_eligible_roots
    )
    selected = ()
    if qualification["status"] == "READY_FOR_SINGLE_SELECTION":
        selected = selector(qualification["eligible_roots"])
    return qualification, selected
