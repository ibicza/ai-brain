"""Generic, deterministic source-artifact provenance and qualification types."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from enum import StrEnum

from ai_brain.stage2.facts.canonical import content_hash

SOURCE_ARTIFACT_PROVENANCE_SCHEMA_VERSION = 2
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


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
    RAW_EXACT_MATCH = "RAW_EXACT_MATCH"
    CANONICAL_TEXT_EXACT_MATCH = "CANONICAL_TEXT_EXACT_MATCH"
    PATH_RELOCATED_RAW_MATCH = "PATH_RELOCATED_RAW_MATCH"
    PATH_RELOCATED_CANONICAL_MATCH = "PATH_RELOCATED_CANONICAL_MATCH"
    EXACT_MATCH = "EXACT_MATCH"
    PATH_RELOCATED_EXACT_CONTENT = "PATH_RELOCATED_EXACT_CONTENT"
    GENERATED_WITH_VERIFIED_PROVENANCE = "GENERATED_WITH_VERIFIED_PROVENANCE"
    UNMATCHED = "UNMATCHED"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"


class ArtifactAuthenticityMode(StrEnum):
    SHA256_SIDECAR_VERIFIED = "SHA256_SIDECAR_VERIFIED"
    OPENPGP_SIGNATURE_VERIFIED = "OPENPGP_SIGNATURE_VERIFIED"
    IMMUTABLE_SCM_CONTENT_EQUIVALENCE = "IMMUTABLE_SCM_CONTENT_EQUIVALENCE"
    MULTI_CHANNEL_VERIFIED = "MULTI_CHANNEL_VERIFIED"
    REPOSITORY_TLS_ONLY = "REPOSITORY_TLS_ONLY"


class DetachedSignatureStatus(StrEnum):
    ABSENT = "ABSENT"
    PRESENT_UNVERIFIED = "PRESENT_UNVERIFIED"
    VERIFIED = "VERIFIED"


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
    detached_signature_sha256: str | None = None
    detached_signature_status: DetachedSignatureStatus = DetachedSignatureStatus.ABSENT
    signer_fingerprint: str | None = None
    frozen_key_provenance_hash: str | None = None
    signature_verification_receipt_hash: str | None = None


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
class ScmRevisionVerificationReceipt:
    repository_url: str
    requested_ref: str
    immutable_commit: str
    tag_to_commit_verified: bool
    source_tree_hash: str
    tag_object: str | None
    remote_ref_response_hash: str
    commit_retrieval_request_hash: str
    commit_retrieval_response_hash: str
    source_archive_sha256: str
    license_path: str | None
    license_raw_sha256: str | None
    receipt_hash: str


# Historical import compatibility. V2 authority is the verified receipt, never a bool.
ScmRevisionEvidence = ScmRevisionVerificationReceipt


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
    raw_exact_match_count: int = 0
    canonical_only_match_count: int = 0
    relocated_raw_match_count: int = 0
    relocated_canonical_match_count: int = 0
    normalization_receipt_hash: str | None = None


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
    scm_revision: ScmRevisionVerificationReceipt | None
    correspondence: SourceTreeCorrespondence | None
    conflicts: tuple[str, ...]
    semantic_identity_hash: str
    audit_event: ProvenanceAuditEvent
    envelope_hash: str
    pom_repository_metadata: RepositoryMetadataEvidence | None = None
    artifact_authenticity_mode: ArtifactAuthenticityMode = (
        ArtifactAuthenticityMode.REPOSITORY_TLS_ONLY
    )


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
    provenance_envelope_hash: str | None = None


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

    authenticity = values.get("artifact_authenticity_mode")
    if authenticity is None:
        authenticity = derive_artifact_authenticity_mode(
            values["artifact_digest"],
            values.get("scm_revision"),
            values.get("correspondence"),
        )
    pom_repository = values.get("pom_repository_metadata")
    semantic = {
        "schema_version": values["schema_version"],
        "coordinate": values["coordinate"],
        "artifact_digest": values["artifact_digest"],
        "repository_metadata": values["repository_metadata"],
        "pom_digest": values["pom_digest"],
        "pom_repository_metadata": pom_repository,
        "license_claims": tuple(values["license_claims"]),
        "license_texts": tuple(values["license_texts"]),
        "license_evidence_mode": values["license_evidence_mode"],
        "license_status": values["license_status"],
        "scm_revision": values.get("scm_revision"),
        "correspondence": values.get("correspondence"),
        "artifact_authenticity_mode": authenticity,
        "conflicts": tuple(values["conflicts"]),
    }
    semantic_identity_hash = content_hash(semantic)
    body = {**semantic, "semantic_identity_hash": semantic_identity_hash}
    envelope_hash = content_hash({**body, "audit_event": values["audit_event"]})
    return SourceArtifactProvenanceEnvelope(
        schema_version=semantic["schema_version"],
        coordinate=semantic["coordinate"],
        artifact_digest=semantic["artifact_digest"],
        repository_metadata=semantic["repository_metadata"],
        pom_digest=semantic["pom_digest"],
        license_claims=semantic["license_claims"],
        license_texts=semantic["license_texts"],
        license_evidence_mode=semantic["license_evidence_mode"],
        license_status=semantic["license_status"],
        scm_revision=semantic["scm_revision"],
        correspondence=semantic["correspondence"],
        conflicts=semantic["conflicts"],
        semantic_identity_hash=semantic_identity_hash,
        audit_event=values["audit_event"],
        envelope_hash=envelope_hash,
        pom_repository_metadata=pom_repository,
        artifact_authenticity_mode=authenticity,
    )


def derive_artifact_authenticity_mode(
    digest: ArtifactDigestEvidence,
    scm_revision: ScmRevisionVerificationReceipt | None,
    correspondence: SourceTreeCorrespondence | None,
) -> ArtifactAuthenticityMode:
    channels = 0
    sidecar = digest.sidecar_verified
    signature = digest.detached_signature_status is DetachedSignatureStatus.VERIFIED
    scm = bool(
        scm_revision
        and scm_revision.tag_to_commit_verified
        and correspondence
        and correspondence.eligible_entry_count
        and not correspondence.unmatched_count
        and not correspondence.ambiguous_count
    )
    channels = sum((sidecar, signature, scm))
    if channels > 1:
        return ArtifactAuthenticityMode.MULTI_CHANNEL_VERIFIED
    if sidecar:
        return ArtifactAuthenticityMode.SHA256_SIDECAR_VERIFIED
    if signature:
        return ArtifactAuthenticityMode.OPENPGP_SIGNATURE_VERIFIED
    if scm:
        return ArtifactAuthenticityMode.IMMUTABLE_SCM_CONTENT_EQUIVALENCE
    return ArtifactAuthenticityMode.REPOSITORY_TLS_ONLY


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
    elif (
        envelope.artifact_authenticity_mode
        is ArtifactAuthenticityMode.REPOSITORY_TLS_ONLY
    ):
        status = CandidateQualificationStatus.INELIGIBLE_PROVENANCE
        reasons.append("NO_STRONG_ARTIFACT_AUTHENTICITY_CHANNEL")
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
        "provenance_envelope_hash": envelope.envelope_hash,
    }
    decision_hash = content_hash(body)
    return ArtifactQualificationDecision(
        coordinate=body["coordinate"],
        requirement=body["requirement"],
        status=body["status"],
        evidence_mode=body["evidence_mode"],
        reasons=body["reasons"],
        eligible_root=body["eligible_root"],
        provenance_identity_hash=body["provenance_identity_hash"],
        decision_hash=decision_hash,
        provenance_envelope_hash=body["provenance_envelope_hash"],
    )


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
    eligible_roots = tuple(item.eligible_root for item in eligible)
    distinct_roots = tuple(sorted(set(eligible_roots)))
    ready = (
        not required_failures
        and len(distinct_roots) >= minimum_eligible_roots
        and len(eligible_roots) == len(distinct_roots)
    )
    body = {
        "decisions": ordered,
        "eligible_roots": distinct_roots,
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


def dump_source_artifact_provenance_envelope(
    envelope: SourceArtifactProvenanceEnvelope,
) -> bytes:
    verify_source_artifact_provenance_envelope(envelope)
    from ai_brain.stage2.facts.canonical import canonical_json

    return (canonical_json(asdict(envelope)) + "\n").encode("utf-8")


def load_source_artifact_provenance_envelope(
    raw: bytes | str,
) -> SourceArtifactProvenanceEnvelope:
    encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
    try:
        value = json.loads(
            encoded.decode("utf-8", errors="strict"), object_pairs_hook=_unique_object
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed source-artifact provenance JSON") from exc
    _expect_fields(
        value,
        {
            "schema_version",
            "coordinate",
            "artifact_digest",
            "repository_metadata",
            "pom_digest",
            "pom_repository_metadata",
            "license_claims",
            "license_texts",
            "license_evidence_mode",
            "license_status",
            "scm_revision",
            "correspondence",
            "artifact_authenticity_mode",
            "conflicts",
            "semantic_identity_hash",
            "audit_event",
            "envelope_hash",
        },
        "provenance envelope",
    )
    coordinate = _load_coordinate(value["coordinate"])
    artifact_digest = _load_digest(value["artifact_digest"])
    pom_digest = _load_digest(value["pom_digest"])
    repository = _load_repository(value["repository_metadata"])
    pom_repository = (
        None
        if value["pom_repository_metadata"] is None
        else _load_repository(value["pom_repository_metadata"])
    )
    if not isinstance(value["license_claims"], list):
        raise TypeError("license_claims must be an array")
    claims = tuple(_load_license_claim(item) for item in value["license_claims"])
    if not isinstance(value["license_texts"], list):
        raise TypeError("license_texts must be an array")
    texts = tuple(_load_license_text(item) for item in value["license_texts"])
    scm = None if value["scm_revision"] is None else _load_scm(value["scm_revision"])
    correspondence = (
        None
        if value["correspondence"] is None
        else _load_correspondence(value["correspondence"])
    )
    audit = _load_audit(value["audit_event"])
    if not isinstance(value["conflicts"], list) or not all(
        isinstance(item, str) for item in value["conflicts"]
    ):
        raise TypeError("conflicts must be a string array")
    try:
        envelope = SourceArtifactProvenanceEnvelope(
            schema_version=value["schema_version"],
            coordinate=coordinate,
            artifact_digest=artifact_digest,
            repository_metadata=repository,
            pom_digest=pom_digest,
            license_claims=claims,
            license_texts=texts,
            license_evidence_mode=LicenseEvidenceMode(value["license_evidence_mode"]),
            license_status=ProvenanceStatus(value["license_status"]),
            scm_revision=scm,
            correspondence=correspondence,
            conflicts=tuple(value["conflicts"]),
            semantic_identity_hash=value["semantic_identity_hash"],
            audit_event=audit,
            envelope_hash=value["envelope_hash"],
            pom_repository_metadata=pom_repository,
            artifact_authenticity_mode=ArtifactAuthenticityMode(
                value["artifact_authenticity_mode"]
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "invalid source-artifact provenance enum or field type"
        ) from exc
    verify_source_artifact_provenance_envelope(envelope)
    if dump_source_artifact_provenance_envelope(envelope) != encoded:
        raise ValueError("provenance JSON is not canonical and byte-identical")
    return envelope


def verify_source_artifact_provenance_envelope(
    envelope: SourceArtifactProvenanceEnvelope,
    *,
    artifact_bytes: bytes | None = None,
    pom_bytes: bytes | None = None,
) -> None:
    if not isinstance(envelope, SourceArtifactProvenanceEnvelope):
        raise TypeError("provenance envelope must be typed")
    if envelope.schema_version != SOURCE_ARTIFACT_PROVENANCE_SCHEMA_VERSION:
        raise ValueError("unsupported source-artifact provenance schema")
    _verify_coordinate(envelope.coordinate)
    _verify_digest(envelope.artifact_digest, artifact_bytes)
    _verify_digest(envelope.pom_digest, pom_bytes)
    _verify_repository(envelope.repository_metadata, envelope.artifact_digest)
    if envelope.pom_repository_metadata is None:
        raise ValueError("POM repository metadata receipt is required")
    _verify_repository(envelope.pom_repository_metadata, envelope.pom_digest)
    for claim in envelope.license_claims:
        _verify_license_claim(claim)
    for evidence in envelope.license_texts:
        _verify_license_text(evidence)
    if envelope.scm_revision is not None:
        verify_scm_revision_receipt(envelope.scm_revision)
    if envelope.correspondence is not None:
        verify_source_tree_correspondence(envelope.correspondence)
    expected_authenticity = derive_artifact_authenticity_mode(
        envelope.artifact_digest, envelope.scm_revision, envelope.correspondence
    )
    if envelope.artifact_authenticity_mode is not expected_authenticity:
        raise ValueError("artifact authenticity mode is not evidence-derived")
    _verify_signature_authority(envelope.artifact_digest)
    expected_mode, expected_status, expected_conflicts = _derive_license_result(
        envelope
    )
    if (
        envelope.license_evidence_mode is not expected_mode
        or envelope.license_status is not expected_status
        or envelope.conflicts != expected_conflicts
    ):
        raise ValueError("license result is not evidence-derived")
    semantic = _semantic_body(envelope)
    if content_hash(semantic) != envelope.semantic_identity_hash:
        raise ValueError("provenance semantic identity hash mismatch")
    verify_provenance_audit_event(envelope.audit_event)
    if (
        content_hash(
            {
                **semantic,
                "semantic_identity_hash": envelope.semantic_identity_hash,
                "audit_event": envelope.audit_event,
            }
        )
        != envelope.envelope_hash
    ):
        raise ValueError("provenance envelope hash mismatch")


def verify_artifact_qualification_decision(
    decision: ArtifactQualificationDecision,
    *,
    envelope: SourceArtifactProvenanceEnvelope,
    requirement: CandidateRequirement,
    expected_coordinate: SourceArtifactCoordinate,
) -> None:
    verify_source_artifact_provenance_envelope(envelope)
    if (
        decision.coordinate != expected_coordinate
        or envelope.coordinate != expected_coordinate
    ):
        raise ValueError("qualification coordinate does not match frozen candidate")
    if decision.requirement is not requirement:
        raise ValueError("qualification requirement does not match frozen policy")
    if decision.provenance_identity_hash != envelope.semantic_identity_hash:
        raise ValueError("qualification provenance identity mismatch")
    if decision.provenance_envelope_hash != envelope.envelope_hash:
        raise ValueError("qualification envelope hash mismatch")
    body = asdict(decision)
    claimed = body.pop("decision_hash")
    if content_hash(body) != claimed:
        raise ValueError("qualification decision hash mismatch")
    if (decision.status is CandidateQualificationStatus.ELIGIBLE) != bool(
        decision.eligible_root
    ):
        raise ValueError("qualification eligible-root invariant failed")


def verify_candidate_qualification_set(
    receipt: dict,
    *,
    candidates,
    decisions: tuple[ArtifactQualificationDecision, ...],
    envelopes: tuple[SourceArtifactProvenanceEnvelope, ...],
    minimum_eligible_roots: int,
) -> None:
    expected_fields = {
        "decisions",
        "eligible_roots",
        "required_failures",
        "minimum_eligible_roots",
        "selector_invocation_count",
        "selector_rerun_count",
        "metrics_used_for_qualification",
        "status",
        "qualification_set_hash",
    }
    _expect_fields(receipt, expected_fields, "qualification set")
    candidate_rows = tuple(candidates)
    if len(candidate_rows) != len(decisions) or len(decisions) != len(envelopes):
        raise ValueError(
            "qualification candidate/decision/envelope denominator mismatch"
        )
    coordinates = tuple(item.coordinate for item in candidate_rows)
    if len(coordinates) != len(set(coordinates)):
        raise ValueError("frozen candidate coordinates must be unique")
    repository_paths = tuple(item.canonical_repository_path for item in coordinates)
    if len(repository_paths) != len(set(repository_paths)):
        raise ValueError("frozen candidate repository paths must be unique")
    decision_coordinates = tuple(item.coordinate for item in decisions)
    if set(decision_coordinates) != set(coordinates) or len(
        set(decision_coordinates)
    ) != len(decision_coordinates):
        raise ValueError("qualification decisions are missing, extra, or duplicated")
    envelope_map = {item.coordinate: item for item in envelopes}
    artifact_hashes = tuple(
        item.artifact_digest.downloaded_bytes_sha256 for item in envelopes
    )
    if len(artifact_hashes) != len(set(artifact_hashes)):
        raise ValueError("candidate artifact bytes must be unique")
    for candidate, decision in zip(candidate_rows, decisions, strict=True):
        verify_artifact_qualification_decision(
            decision,
            envelope=envelope_map[decision.coordinate],
            requirement=candidate.requirement,
            expected_coordinate=candidate.coordinate,
        )
    expected = qualify_candidate_set(
        decisions, minimum_eligible_roots=minimum_eligible_roots
    )
    if receipt != expected:
        raise ValueError("qualification set is not independently derived")


def verify_provenance_audit_event(event: ProvenanceAuditEvent) -> None:
    body = asdict(event)
    claimed = body.pop("audit_hash")
    if (
        not event.acquired_at
        or not event.host
        or not event.acquisition_run_id
        or tuple(sorted(event.network_receipt_hashes)) != event.network_receipt_hashes
        or any(not _is_hash(item) for item in event.network_receipt_hashes)
        or content_hash(body) != claimed
    ):
        raise ValueError("invalid provenance audit event")


def verify_scm_revision_receipt(receipt: ScmRevisionVerificationReceipt) -> None:
    body = asdict(receipt)
    claimed = body.pop("receipt_hash")
    hashes = (
        receipt.source_tree_hash,
        receipt.remote_ref_response_hash,
        receipt.commit_retrieval_request_hash,
        receipt.commit_retrieval_response_hash,
        receipt.source_archive_sha256,
    )
    if (
        not receipt.repository_url.startswith("https://")
        or not receipt.requested_ref.startswith("refs/tags/")
        or not receipt.tag_to_commit_verified
        or not isinstance(receipt.immutable_commit, str)
        or not re.fullmatch(r"[0-9a-f]{40}", receipt.immutable_commit)
        or not all(_is_hash(item) for item in hashes)
        or (
            receipt.tag_object is not None
            and not re.fullmatch(r"[0-9a-f]{40}", receipt.tag_object)
        )
        or (
            receipt.license_raw_sha256 is not None
            and not _is_hash(receipt.license_raw_sha256)
        )
        or content_hash(body) != claimed
    ):
        raise ValueError("invalid SCM revision verification receipt")


def verify_source_tree_correspondence(value: SourceTreeCorrespondence) -> None:
    for entry in value.entries:
        body = asdict(entry)
        claimed = body.pop("entry_hash")
        if (
            not _is_hash(entry.raw_sha256)
            or not _is_hash(entry.canonical_sha256)
            or content_hash(body) != claimed
        ):
            raise ValueError("source correspondence entry hash mismatch")
    counts = {
        status: sum(item.status is status for item in value.entries)
        for status in SourceCorrespondenceStatus
    }
    accepted = {
        SourceCorrespondenceStatus.RAW_EXACT_MATCH,
        SourceCorrespondenceStatus.CANONICAL_TEXT_EXACT_MATCH,
        SourceCorrespondenceStatus.PATH_RELOCATED_RAW_MATCH,
        SourceCorrespondenceStatus.PATH_RELOCATED_CANONICAL_MATCH,
        SourceCorrespondenceStatus.GENERATED_WITH_VERIFIED_PROVENANCE,
    }
    expected = {
        "exact_match_count": counts[SourceCorrespondenceStatus.RAW_EXACT_MATCH]
        + counts[SourceCorrespondenceStatus.CANONICAL_TEXT_EXACT_MATCH],
        "relocated_match_count": counts[
            SourceCorrespondenceStatus.PATH_RELOCATED_RAW_MATCH
        ]
        + counts[SourceCorrespondenceStatus.PATH_RELOCATED_CANONICAL_MATCH],
        "generated_match_count": counts[
            SourceCorrespondenceStatus.GENERATED_WITH_VERIFIED_PROVENANCE
        ],
        "unmatched_count": counts[SourceCorrespondenceStatus.UNMATCHED],
        "ambiguous_count": counts[SourceCorrespondenceStatus.AMBIGUOUS_MATCH],
        "eligible_entry_count": sum(item.status in accepted for item in value.entries),
        "raw_exact_match_count": counts[SourceCorrespondenceStatus.RAW_EXACT_MATCH],
        "canonical_only_match_count": counts[
            SourceCorrespondenceStatus.CANONICAL_TEXT_EXACT_MATCH
        ],
        "relocated_raw_match_count": counts[
            SourceCorrespondenceStatus.PATH_RELOCATED_RAW_MATCH
        ],
        "relocated_canonical_match_count": counts[
            SourceCorrespondenceStatus.PATH_RELOCATED_CANONICAL_MATCH
        ],
    }
    if any(
        getattr(value, key) != expected_item for key, expected_item in expected.items()
    ):
        raise ValueError("source correspondence counters mismatch")
    if value.normalization_receipt_hash is not None and not _is_hash(
        value.normalization_receipt_hash
    ):
        raise ValueError("invalid correspondence normalization receipt")
    body = asdict(value)
    claimed = body.pop("correspondence_hash")
    if content_hash(body) != claimed:
        raise ValueError("source correspondence hash mismatch")


def _derive_license_result(envelope):
    pom_values = {item.spdx_identifier for item in envelope.license_claims}
    embedded = tuple(
        item
        for item in envelope.license_texts
        if not item.evidence_path.startswith("SCM/")
    )
    scm = tuple(
        item for item in envelope.license_texts if item.evidence_path.startswith("SCM/")
    )
    embedded_exact = bool(embedded) and all(item.exact_match for item in embedded)
    scm_exact = bool(scm) and all(item.exact_match for item in scm)
    pom_apache = pom_values == {"Apache-2.0"}
    conflicts = []
    if pom_values and not pom_apache:
        conflicts.append("POM_LICENSE_CONFLICT")
    if embedded and not embedded_exact:
        conflicts.append("EMBEDDED_LICENSE_CONFLICT")
    if scm and not scm_exact:
        conflicts.append("SCM_LICENSE_CONFLICT")
    if conflicts:
        return (
            LicenseEvidenceMode.CONFLICTING_LICENSE_EVIDENCE,
            ProvenanceStatus.CONFLICT,
            tuple(conflicts),
        )
    complete_scm = bool(
        envelope.scm_revision
        and envelope.correspondence
        and envelope.correspondence.eligible_entry_count
        and not envelope.correspondence.unmatched_count
        and not envelope.correspondence.ambiguous_count
    )
    if embedded_exact and pom_apache and scm_exact and complete_scm:
        return (
            LicenseEvidenceMode.EMBEDDED_AND_SCM_CORROBORATED,
            ProvenanceStatus.VERIFIED,
            (),
        )
    if embedded_exact:
        return LicenseEvidenceMode.EMBEDDED_EXACT_LICENSE, ProvenanceStatus.VERIFIED, ()
    if pom_apache and scm_exact and complete_scm:
        return (
            LicenseEvidenceMode.POM_PLUS_IMMUTABLE_SCM_LICENSE,
            ProvenanceStatus.VERIFIED,
            (),
        )
    if pom_apache:
        return (
            LicenseEvidenceMode.POM_DECLARATION_ONLY,
            ProvenanceStatus.REVIEW_REQUIRED,
            (),
        )
    return LicenseEvidenceMode.NO_LICENSE_EVIDENCE, ProvenanceStatus.INELIGIBLE, ()


def _semantic_body(envelope):
    return {
        "schema_version": envelope.schema_version,
        "coordinate": envelope.coordinate,
        "artifact_digest": envelope.artifact_digest,
        "repository_metadata": envelope.repository_metadata,
        "pom_digest": envelope.pom_digest,
        "pom_repository_metadata": envelope.pom_repository_metadata,
        "license_claims": envelope.license_claims,
        "license_texts": envelope.license_texts,
        "license_evidence_mode": envelope.license_evidence_mode,
        "license_status": envelope.license_status,
        "scm_revision": envelope.scm_revision,
        "correspondence": envelope.correspondence,
        "artifact_authenticity_mode": envelope.artifact_authenticity_mode,
        "conflicts": envelope.conflicts,
    }


def _verify_coordinate(value):
    if not isinstance(value, SourceArtifactCoordinate):
        raise TypeError("coordinate must be typed")
    name = f"{value.name}-{value.version}-{value.classifier}.{value.extension}"
    expected_path = (
        f"{value.namespace.replace('.', '/')}/{value.name}/{value.version}/{name}"
    )
    if (
        value.repository != "https://repo.maven.apache.org/maven2"
        or value.classifier != "sources"
        or value.extension != "jar"
        or value.canonical_repository_path != expected_path
    ):
        raise ValueError("coordinate repository path derivation mismatch")


def _verify_digest(value, payload):
    if not isinstance(value, ArtifactDigestEvidence):
        raise TypeError("artifact digest must be typed")
    if (
        not _is_hash(value.downloaded_bytes_sha256)
        or type(value.artifact_size) is not int
        or value.artifact_size < 0
    ):
        raise ValueError("invalid artifact digest evidence")
    if payload is not None:
        from ai_brain.stage2.facts.canonical import bytes_hash

        if (
            bytes_hash(payload) != value.downloaded_bytes_sha256
            or len(payload) != value.artifact_size
        ):
            raise ValueError("artifact payload digest or size mismatch")
    if value.sidecar_verified:
        if value.sidecar_sha256 != value.downloaded_bytes_sha256:
            raise ValueError("verified sidecar does not bind artifact digest")
    elif value.sidecar_sha256 is not None:
        raise ValueError("unverified sidecar cannot assert a digest")


def _verify_repository(value, digest):
    if not isinstance(value, RepositoryMetadataEvidence):
        raise TypeError("repository metadata must be typed")
    body = {
        "requested_url": value.requested_url,
        "final_url": value.final_url,
        "redirect_chain": value.redirect_chain,
        "content_length": value.content_length,
        "media_type": value.media_type,
    }
    if (
        value.repository_host != "repo.maven.apache.org"
        or not value.requested_url.startswith("https://repo.maven.apache.org/maven2/")
        or value.final_url != value.requested_url
        or value.redirect_chain
        or value.content_length != digest.artifact_size
        or content_hash(body) != value.network_receipt_hash
    ):
        raise ValueError("invalid repository metadata receipt")


def _verify_signature_authority(value):
    status = value.detached_signature_status
    if status is DetachedSignatureStatus.ABSENT:
        if any(
            item is not None
            for item in (
                value.detached_signature_url,
                value.detached_signature_sha256,
                value.signer_fingerprint,
                value.frozen_key_provenance_hash,
                value.signature_verification_receipt_hash,
            )
        ):
            raise ValueError("absent detached signature has evidence fields")
    elif status is DetachedSignatureStatus.PRESENT_UNVERIFIED:
        if not value.detached_signature_url or not _is_hash(
            value.detached_signature_sha256 or ""
        ):
            raise ValueError("unverified detached signature is not byte-bound")
        if any(
            item is not None
            for item in (
                value.signer_fingerprint,
                value.frozen_key_provenance_hash,
                value.signature_verification_receipt_hash,
            )
        ):
            raise ValueError("unverified detached signature cannot claim authority")
    elif status is DetachedSignatureStatus.VERIFIED and not all(
        (
            value.detached_signature_url,
            _is_hash(value.detached_signature_sha256 or ""),
            value.signer_fingerprint,
            _is_hash(value.frozen_key_provenance_hash or ""),
            _is_hash(value.signature_verification_receipt_hash or ""),
        )
    ):
        raise ValueError("verified signature lacks frozen signer authority")


def _verify_license_claim(value):
    body = asdict(value)
    claimed = body.pop("declaration_hash")
    if (
        not value.spdx_identifier
        or not value.declaration_source
        or content_hash(body) != claimed
    ):
        raise ValueError("invalid license declaration hash")


def _verify_license_text(value):
    if not all(
        _is_hash(item)
        for item in (
            value.raw_text_sha256,
            value.normalized_text_sha256,
            value.canonical_license_sha256,
        )
    ) or value.exact_match is not (
        value.normalized_text_sha256 == value.canonical_license_sha256
    ):
        raise ValueError("invalid license text evidence")


def _load_coordinate(value):
    fields = {
        "repository",
        "namespace",
        "name",
        "version",
        "classifier",
        "extension",
        "canonical_repository_path",
    }
    _expect_fields(value, fields, "coordinate")
    return SourceArtifactCoordinate(**value)


def _load_digest(value):
    fields = {
        "downloaded_bytes_sha256",
        "sidecar_sha256",
        "sidecar_verified",
        "detached_signature_url",
        "artifact_size",
        "detached_signature_sha256",
        "detached_signature_status",
        "signer_fingerprint",
        "frozen_key_provenance_hash",
        "signature_verification_receipt_hash",
    }
    _expect_fields(value, fields, "artifact digest")
    return ArtifactDigestEvidence(
        **{
            key: item
            for key, item in value.items()
            if key != "detached_signature_status"
        },
        detached_signature_status=DetachedSignatureStatus(
            value["detached_signature_status"]
        ),
    )


def _load_repository(value):
    fields = {
        "repository_host",
        "requested_url",
        "final_url",
        "redirect_chain",
        "content_length",
        "media_type",
        "network_receipt_hash",
    }
    _expect_fields(value, fields, "repository metadata")
    return RepositoryMetadataEvidence(
        **{**value, "redirect_chain": tuple(value["redirect_chain"])}
    )


def _load_license_claim(value):
    _expect_fields(
        value,
        {"spdx_identifier", "declaration_source", "declared_name", "declaration_hash"},
        "license claim",
    )
    return LicenseClaim(**value)


def _load_license_text(value):
    _expect_fields(
        value,
        {
            "evidence_path",
            "raw_text_sha256",
            "normalized_text_sha256",
            "canonical_license_sha256",
            "exact_match",
        },
        "license text",
    )
    return LicenseTextEvidence(**value)


def _load_scm(value):
    fields = {
        "repository_url",
        "requested_ref",
        "immutable_commit",
        "tag_to_commit_verified",
        "source_tree_hash",
        "tag_object",
        "remote_ref_response_hash",
        "commit_retrieval_request_hash",
        "commit_retrieval_response_hash",
        "source_archive_sha256",
        "license_path",
        "license_raw_sha256",
        "receipt_hash",
    }
    _expect_fields(value, fields, "SCM revision receipt")
    return ScmRevisionVerificationReceipt(**value)


def _load_correspondence(value):
    fields = {
        "entries",
        "exact_match_count",
        "relocated_match_count",
        "generated_match_count",
        "unmatched_count",
        "ambiguous_count",
        "eligible_entry_count",
        "correspondence_hash",
        "raw_exact_match_count",
        "canonical_only_match_count",
        "relocated_raw_match_count",
        "relocated_canonical_match_count",
        "normalization_receipt_hash",
    }
    _expect_fields(value, fields, "source correspondence")
    entries = []
    for row in value["entries"]:
        _expect_fields(
            row,
            {
                "artifact_path",
                "repository_path",
                "raw_sha256",
                "canonical_sha256",
                "status",
                "entry_hash",
            },
            "source correspondence entry",
        )
        entries.append(
            SourceTreeCorrespondenceEntry(
                **{**row, "status": SourceCorrespondenceStatus(row["status"])}
            )
        )
    return SourceTreeCorrespondence(**{**value, "entries": tuple(entries)})


def _load_audit(value):
    _expect_fields(
        value,
        {
            "acquired_at",
            "host",
            "acquisition_run_id",
            "network_receipt_hashes",
            "audit_hash",
        },
        "audit event",
    )
    return ProvenanceAuditEvent(
        **{**value, "network_receipt_hashes": tuple(value["network_receipt_hashes"])}
    )


def _expect_fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"invalid {label} field set")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _is_hash(value):
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))
