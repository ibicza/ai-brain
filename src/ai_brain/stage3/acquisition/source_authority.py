"""Independent source authenticity, analysis, retention, and publication axes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.source_artifact_provenance import (
    ArtifactAuthenticityMode,
    SourceCorrespondenceStatus,
    SourceTreeCorrespondence,
)
from ai_brain.stage3.acquisition.spdx_license import (
    AUTOMATIC_SPDX_MATCH_STATUSES,
    LicenseDocumentRole,
)


class SourceAuthenticityStatus(StrEnum):
    AUTHENTIC = "AUTHENTIC"
    AUTHENTIC_WITH_SINGLE_CHANNEL = "AUTHENTIC_WITH_SINGLE_CHANNEL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CONFLICT = "CONFLICT"
    INVALID = "INVALID"


class KnowledgeAcquisitionEligibility(StrEnum):
    ELIGIBLE_FOR_ANALYSIS = "ELIGIBLE_FOR_ANALYSIS"
    ELIGIBLE_FOR_LOCAL_EVALUATION = "ELIGIBLE_FOR_LOCAL_EVALUATION"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INELIGIBLE = "INELIGIBLE"


class SourceUseScope(StrEnum):
    PRIVATE_LOCAL_ANALYSIS = "PRIVATE_LOCAL_ANALYSIS"
    LOCAL_RESEARCH_EVALUATION = "LOCAL_RESEARCH_EVALUATION"
    DERIVED_KNOWLEDGE_ONLY = "DERIVED_KNOWLEDGE_ONLY"
    RAW_SOURCE_RETENTION = "RAW_SOURCE_RETENTION"
    RAW_SOURCE_REDISTRIBUTION = "RAW_SOURCE_REDISTRIBUTION"
    PUBLIC_REPRODUCIBLE_EVALUATION = "PUBLIC_REPRODUCIBLE_EVALUATION"


class PublicationTarget(StrEnum):
    RAW_SOURCE_PUBLICATION = "RAW_SOURCE_PUBLICATION"
    SOURCE_EXCERPT_PUBLICATION = "SOURCE_EXCERPT_PUBLICATION"
    DERIVED_PACK_PUBLICATION = "DERIVED_PACK_PUBLICATION"
    METRICS_ONLY_PUBLICATION = "METRICS_ONLY_PUBLICATION"


class PublicationEligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INELIGIBLE = "INELIGIBLE"


class LicenseEvidenceFusionStatus(StrEnum):
    CORROBORATED = "CORROBORATED"
    VERIFIED_EXTERNAL_CHAIN = "VERIFIED_EXTERNAL_CHAIN"
    SINGLE_CHANNEL_VERIFIED = "SINGLE_CHANNEL_VERIFIED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    TRUE_LICENSE_CONFLICT = "TRUE_LICENSE_CONFLICT"
    ADDITIONAL_TERMS = "ADDITIONAL_TERMS"
    NO_PROJECT_LICENSE = "NO_PROJECT_LICENSE"


@dataclass(frozen=True)
class SourceUseAuthorizationReceipt:
    authority_kind: str
    authority_id: str
    authorized_scopes: tuple[SourceUseScope, ...]
    publication_targets: tuple[PublicationTarget, ...]
    policy_version: str
    receipt_hash: str


@dataclass(frozen=True)
class LicenseEvidenceFusionReceipt:
    pom_expressions: tuple[str, ...]
    project_document_receipt_hashes: tuple[str, ...]
    review_document_receipt_hashes: tuple[str, ...]
    ignored_nonproject_receipt_hashes: tuple[str, ...]
    resolved_expression: str | None
    status: LicenseEvidenceFusionStatus
    reasons: tuple[str, ...]
    receipt_hash: str


@dataclass(frozen=True)
class PublicationEligibilityDecision:
    target: PublicationTarget
    status: PublicationEligibilityStatus
    authorization_receipt_hash: str
    reason: str
    decision_hash: str


@dataclass(frozen=True)
class SourceEntryEligibility:
    artifact_path: str
    raw_sha256: str
    canonical_sha256: str
    source_authenticity: SourceAuthenticityStatus
    correspondence_class: SourceCorrespondenceStatus
    use_scopes: tuple[SourceUseScope, ...]
    publication_targets: tuple[PublicationTarget, ...]
    included: bool
    reason: str
    receipt_hash: str


@dataclass(frozen=True)
class CandidateEligibleSourceSet:
    entries: tuple[SourceEntryEligibility, ...]
    total_entry_count: int
    analysis_eligible_entry_count: int
    publication_eligible_entry_count: int
    excluded_entry_count: int
    reason_counts: tuple[tuple[str, int], ...]
    selected_manifest_hash: str
    receipt_hash: str


@dataclass(frozen=True)
class SourceAuthorityDecision:
    source_authenticity: SourceAuthenticityStatus
    knowledge_acquisition: KnowledgeAcquisitionEligibility
    source_use_scopes: tuple[SourceUseScope, ...]
    publication: tuple[PublicationEligibilityDecision, ...]
    license_expression: str | None
    license_fusion_status: LicenseEvidenceFusionStatus
    eligible_source_set_hash: str
    authorization_receipt_hash: str
    reasons: tuple[str, ...]
    decision_hash: str


def build_source_use_authorization(
    *,
    authority_kind: str,
    authority_id: str,
    authorized_scopes,
    publication_targets,
    policy_version: str,
) -> SourceUseAuthorizationReceipt:
    if authority_kind in {"MODEL", "ASSISTANT", "GENERATED_MODEL"}:
        raise ValueError("a model may not grant source-use or publication authority")
    scopes = tuple(
        sorted({SourceUseScope(item) for item in authorized_scopes}, key=str)
    )
    targets = tuple(
        sorted({PublicationTarget(item) for item in publication_targets}, key=str)
    )
    if not authority_id or not policy_version or not scopes:
        raise ValueError("source-use authorization is incomplete")
    raw_targets = {
        PublicationTarget.RAW_SOURCE_PUBLICATION,
        PublicationTarget.SOURCE_EXCERPT_PUBLICATION,
    }
    if (
        set(targets) & raw_targets
        and SourceUseScope.RAW_SOURCE_REDISTRIBUTION not in scopes
    ):
        raise ValueError("raw or excerpt publication exceeds the authorized use scope")
    if (
        PublicationTarget.DERIVED_PACK_PUBLICATION in targets
        and SourceUseScope.DERIVED_KNOWLEDGE_ONLY not in scopes
    ):
        raise ValueError("derived-pack publication exceeds the authorized use scope")
    body = {
        "authority_kind": authority_kind,
        "authority_id": authority_id,
        "authorized_scopes": scopes,
        "publication_targets": targets,
        "policy_version": policy_version,
    }
    return SourceUseAuthorizationReceipt(**body, receipt_hash=content_hash(body))


def verify_source_use_authorization(receipt: SourceUseAuthorizationReceipt) -> None:
    if not isinstance(receipt, SourceUseAuthorizationReceipt):
        raise TypeError("source-use authorization must be typed")
    body = asdict(receipt)
    claimed = body.pop("receipt_hash")
    rebuilt = build_source_use_authorization(**body)
    if rebuilt.receipt_hash != claimed:
        raise ValueError("source-use authorization hash mismatch")


def fuse_license_evidence(
    *,
    pom_expressions,
    document_receipts,
    source_correspondence_complete: bool,
) -> LicenseEvidenceFusionReceipt:
    pom = tuple(sorted(set(pom_expressions)))
    receipts = tuple(document_receipts)
    project = tuple(
        item
        for item in receipts
        if item.document_role
        in {LicenseDocumentRole.PROJECT_LICENSE, LicenseDocumentRole.MODULE_LICENSE}
    )
    ignored = tuple(item for item in receipts if item not in project)
    recognized = tuple(
        item
        for item in project
        if item.match_status in AUTOMATIC_SPDX_MATCH_STATUSES
        and item.template_license_id is not None
    )
    review = tuple(item for item in project if item not in recognized)
    additional = tuple(
        item
        for item in review
        if "additional-substantive-terms" in item.unmatched_substantive_spans
    )
    expressions = tuple(sorted({item.template_license_id for item in recognized}))
    declared_and_observed = tuple(sorted(set(pom) | set(expressions)))
    reasons = []
    resolved = None
    compatible_additional = tuple(
        item for item in additional if item.template_license_id in declared_and_observed
    )
    if len(declared_and_observed) > 1:
        status = LicenseEvidenceFusionStatus.TRUE_LICENSE_CONFLICT
        reasons.append("INCOMPATIBLE_IDENTIFIED_PROJECT_LICENSE_EXPRESSIONS")
    elif compatible_additional:
        resolved = compatible_additional[0].template_license_id
        status = LicenseEvidenceFusionStatus.ADDITIONAL_TERMS
        reasons.append("RECOGNIZED_BASE_LICENSE_WITH_ADDITIONAL_TERMS")
    elif expressions:
        resolved = expressions[0]
        matching_channels = len(recognized) + int(resolved in pom)
        if review:
            status = LicenseEvidenceFusionStatus.REVIEW_REQUIRED
            reasons.append("UNRECOGNIZED_PROJECT_LICENSE_CHANNEL")
        elif matching_channels >= 2 and source_correspondence_complete:
            status = LicenseEvidenceFusionStatus.VERIFIED_EXTERNAL_CHAIN
            reasons.append("POM_SPDX_SCM_AND_SOURCE_CORRESPONDENCE")
        elif matching_channels >= 2:
            status = LicenseEvidenceFusionStatus.CORROBORATED
            reasons.append("MULTIPLE_RECOGNIZED_LICENSE_CHANNELS")
        else:
            status = LicenseEvidenceFusionStatus.SINGLE_CHANNEL_VERIFIED
            reasons.append("ONE_RECOGNIZED_PROJECT_LICENSE_CHANNEL")
    elif len(pom) == 1:
        resolved = pom[0]
        status = LicenseEvidenceFusionStatus.REVIEW_REQUIRED
        reasons.append("POM_DECLARATION_ONLY")
    elif review:
        status = LicenseEvidenceFusionStatus.REVIEW_REQUIRED
        reasons.append("UNRECOGNIZED_PROJECT_LICENSE_DOCUMENT")
    else:
        status = LicenseEvidenceFusionStatus.NO_PROJECT_LICENSE
        reasons.append("NO_PROJECT_LICENSE_CHANNEL")
    body = {
        "pom_expressions": pom,
        "project_document_receipt_hashes": tuple(
            sorted(item.receipt_hash for item in recognized)
        ),
        "review_document_receipt_hashes": tuple(
            sorted(item.receipt_hash for item in review)
        ),
        "ignored_nonproject_receipt_hashes": tuple(
            sorted(item.receipt_hash for item in ignored)
        ),
        "resolved_expression": resolved,
        "status": status,
        "reasons": tuple(reasons),
    }
    return LicenseEvidenceFusionReceipt(**body, receipt_hash=content_hash(body))


def classify_source_authenticity(
    mode: ArtifactAuthenticityMode,
) -> SourceAuthenticityStatus:
    if mode is ArtifactAuthenticityMode.MULTI_CHANNEL_VERIFIED:
        return SourceAuthenticityStatus.AUTHENTIC
    if mode in {
        ArtifactAuthenticityMode.SHA256_SIDECAR_VERIFIED,
        ArtifactAuthenticityMode.OPENPGP_SIGNATURE_VERIFIED,
        ArtifactAuthenticityMode.IMMUTABLE_SCM_CONTENT_EQUIVALENCE,
    }:
        return SourceAuthenticityStatus.AUTHENTIC_WITH_SINGLE_CHANNEL
    return SourceAuthenticityStatus.REVIEW_REQUIRED


def build_candidate_eligible_source_set(
    correspondence: SourceTreeCorrespondence,
    *,
    authenticity: SourceAuthenticityStatus,
    authorization: SourceUseAuthorizationReceipt,
    authenticated_archive: bool = False,
) -> CandidateEligibleSourceSet:
    verify_source_use_authorization(authorization)
    allowed_correspondence = {
        SourceCorrespondenceStatus.RAW_EXACT_MATCH,
        SourceCorrespondenceStatus.CANONICAL_TEXT_EXACT_MATCH,
        SourceCorrespondenceStatus.PATH_RELOCATED_RAW_MATCH,
        SourceCorrespondenceStatus.PATH_RELOCATED_CANONICAL_MATCH,
        SourceCorrespondenceStatus.GENERATED_WITH_VERIFIED_PROVENANCE,
    }
    authentic = authenticity in {
        SourceAuthenticityStatus.AUTHENTIC,
        SourceAuthenticityStatus.AUTHENTIC_WITH_SINGLE_CHANNEL,
    }
    entries = []
    for item in correspondence.entries:
        verified_correspondence = item.status in allowed_correspondence
        archive_only = authenticated_archive and item.status in {
            SourceCorrespondenceStatus.UNMATCHED,
            SourceCorrespondenceStatus.AMBIGUOUS_MATCH,
        }
        included = authentic and (verified_correspondence or archive_only)
        reason = (
            "ELIGIBLE_AUTHENTIC_CORRESPONDENCE"
            if included and verified_correspondence
            else "ELIGIBLE_AUTHENTIC_ARCHIVE_SINGLE_CHANNEL"
            if included
            else (
                "SOURCE_AUTHENTICITY_REVIEW_REQUIRED"
                if not authentic
                else f"EXCLUDED_{item.status.value}"
            )
        )
        body = {
            "artifact_path": item.artifact_path,
            "raw_sha256": item.raw_sha256,
            "canonical_sha256": item.canonical_sha256,
            "source_authenticity": authenticity,
            "correspondence_class": item.status,
            "use_scopes": authorization.authorized_scopes,
            "publication_targets": authorization.publication_targets,
            "included": included,
            "reason": reason,
        }
        entries.append(SourceEntryEligibility(**body, receipt_hash=content_hash(body)))
    ordered = tuple(sorted(entries, key=lambda item: item.artifact_path))
    reasons = tuple(
        sorted(
            {
                item.reason: sum(other.reason == item.reason for other in ordered)
                for item in ordered
            }.items()
        )
    )
    selected = tuple(
        (item.artifact_path, item.raw_sha256, item.canonical_sha256, item.receipt_hash)
        for item in ordered
        if item.included
    )
    publication_eligible = sum(
        item.included
        and PublicationTarget.RAW_SOURCE_PUBLICATION in item.publication_targets
        for item in ordered
    )
    body = {
        "entries": ordered,
        "total_entry_count": len(ordered),
        "analysis_eligible_entry_count": len(selected),
        "publication_eligible_entry_count": publication_eligible,
        "excluded_entry_count": len(ordered) - len(selected),
        "reason_counts": reasons,
        "selected_manifest_hash": content_hash(selected),
    }
    return CandidateEligibleSourceSet(**body, receipt_hash=content_hash(body))


def build_source_authority_decision(
    *,
    authenticity_mode: ArtifactAuthenticityMode,
    fusion: LicenseEvidenceFusionReceipt,
    eligible_set: CandidateEligibleSourceSet,
    authorization: SourceUseAuthorizationReceipt,
) -> SourceAuthorityDecision:
    verify_source_use_authorization(authorization)
    authenticity = classify_source_authenticity(authenticity_mode)
    analysis_ok = (
        authenticity
        in {
            SourceAuthenticityStatus.AUTHENTIC,
            SourceAuthenticityStatus.AUTHENTIC_WITH_SINGLE_CHANNEL,
        }
        and eligible_set.analysis_eligible_entry_count > 0
        and SourceUseScope.PRIVATE_LOCAL_ANALYSIS in authorization.authorized_scopes
        and fusion.status is not LicenseEvidenceFusionStatus.TRUE_LICENSE_CONFLICT
    )
    if analysis_ok:
        acquisition = KnowledgeAcquisitionEligibility.ELIGIBLE_FOR_ANALYSIS
        reasons = ("AUTHENTIC_ELIGIBLE_SUBSET_WITH_EXPLICIT_LOCAL_SCOPE",)
    elif authenticity is SourceAuthenticityStatus.REVIEW_REQUIRED:
        acquisition = KnowledgeAcquisitionEligibility.REVIEW_REQUIRED
        reasons = ("SOURCE_AUTHENTICITY_REVIEW_REQUIRED",)
    else:
        acquisition = KnowledgeAcquisitionEligibility.INELIGIBLE
        reasons = ("NO_ANALYSIS_ELIGIBLE_SOURCE_SET",)
    publication = []
    for target in PublicationTarget:
        if target in authorization.publication_targets:
            status = PublicationEligibilityStatus.ELIGIBLE
            reason = "EXPLICIT_AUTHORIZATION_RECEIPT"
        else:
            status = PublicationEligibilityStatus.INELIGIBLE
            reason = "SCOPE_NOT_GRANTED"
        body = {
            "target": target,
            "status": status,
            "authorization_receipt_hash": authorization.receipt_hash,
            "reason": reason,
        }
        publication.append(
            PublicationEligibilityDecision(**body, decision_hash=content_hash(body))
        )
    body = {
        "source_authenticity": authenticity,
        "knowledge_acquisition": acquisition,
        "source_use_scopes": authorization.authorized_scopes,
        "publication": tuple(publication),
        "license_expression": fusion.resolved_expression,
        "license_fusion_status": fusion.status,
        "eligible_source_set_hash": eligible_set.receipt_hash,
        "authorization_receipt_hash": authorization.receipt_hash,
        "reasons": reasons,
    }
    return SourceAuthorityDecision(**body, decision_hash=content_hash(body))


def semantic_scope_invariant_hash(value) -> str:
    """Hash semantic content only; storage/export scope is intentionally absent."""

    if isinstance(value, dict) and "semantic_binding" in value:
        expected = {"semantic_binding", "source_use_scope", "raw_export_manifest"}
        if set(value) != expected:
            raise ValueError("source-scope semantic view field mismatch")
        SourceUseScope(value["source_use_scope"])
        if not isinstance(value["raw_export_manifest"], (tuple, list)):
            raise TypeError("raw export manifest must be an ordered sequence")
        return content_hash(value["semantic_binding"])
    return content_hash(value)
