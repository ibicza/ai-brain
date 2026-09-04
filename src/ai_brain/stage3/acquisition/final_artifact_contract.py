"""Single generated contract for final artifact paths, roles, schemas and claims."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash

FINAL_ARTIFACT_CONTRACT_VERSION = 1


class FinalArtifactRole(StrEnum):
    FINAL_SOURCE_BYTES = "FINAL_SOURCE_BYTES"
    FINAL_ACQUISITION_BYTES = "FINAL_ACQUISITION_BYTES"
    FINAL_SOURCE_RECEIPT = "FINAL_SOURCE_RECEIPT"
    FINAL_SELECTOR_OUTPUT = "FINAL_SELECTOR_OUTPUT"
    FINAL_PHYSICAL_CENSUS = "FINAL_PHYSICAL_CENSUS"
    FINAL_PRODUCTION_OUTPUT = "FINAL_PRODUCTION_OUTPUT"
    FINAL_CANDIDATE_PACK = "FINAL_CANDIDATE_PACK"
    FINAL_ORACLE_OUTPUT = "FINAL_ORACLE_OUTPUT"
    FINAL_GOLDEN = "FINAL_GOLDEN"
    FINAL_EVALUATION = "FINAL_EVALUATION"
    FINAL_APPROVAL = "FINAL_APPROVAL"
    FINAL_INSTALLATION = "FINAL_INSTALLATION"
    FINAL_DECISION = "FINAL_DECISION"
    GENERIC_EMPTY_RESULT = "GENERIC_EMPTY_RESULT"
    PROCESS_AUDIT = "PROCESS_AUDIT"
    QUALITY_LOG = "QUALITY_LOG"
    HUMAN_READABLE_REPORT = "HUMAN_READABLE_REPORT"


class FinalArtifactFieldClass(StrEnum):
    PUBLIC = "PUBLIC"
    PREDECLARED = "PREDECLARED"
    AUDIT = "AUDIT"
    SECRET = "SECRET"


@dataclass(frozen=True)
class FinalArtifactFieldContract:
    field_name: str
    field_class: FinalArtifactFieldClass
    mandatory_disclosure_claim: str | None = None


@dataclass(frozen=True)
class FinalArtifactTypeContract:
    artifact_type: str
    path_pattern: str
    role: FinalArtifactRole
    media_type: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    forbidden_fields: tuple[str, ...]
    field_contracts: tuple[FinalArtifactFieldContract, ...]
    sample_path: str


@dataclass(frozen=True)
class FinalArtifactContract:
    schema_version: int
    artifact_types: tuple[FinalArtifactTypeContract, ...]
    protected_roles: tuple[FinalArtifactRole, ...]
    contract_hash: str


@dataclass(frozen=True)
class FinalArtifactValidation:
    relative_path: str
    artifact_type: str
    role: FinalArtifactRole
    observed_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    unexpected_fields: tuple[str, ...]
    unclassified_fields: tuple[str, ...]
    disclosure_fields: tuple[str, ...]
    public_or_predeclared_fields: tuple[str, ...]
    status: str
    validation_hash: str


_SECRET_CLAIMS = {
    "archive_hash": "FINAL_ARCHIVE_HASH",
    "source_archive_sha256": "FINAL_ARCHIVE_HASH",
    "downloaded_bytes_sha256": "FINAL_ARCHIVE_HASH",
    "pom_hash": "FINAL_POM_HASH",
    "pom_sha256": "FINAL_POM_HASH",
    "raw_sha256": "FINAL_RAW_SOURCE_HASH",
    "raw_source_hashes": "FINAL_RAW_SOURCE_HASH",
    "canonical_sha256": "FINAL_CANONICAL_SOURCE_HASH",
    "canonical_source_hashes": "FINAL_CANONICAL_SOURCE_HASH",
    "source_tree_hash": "FINAL_SOURCE_TREE_HASH",
    "scm_revision": "FINAL_SCM_REVISION",
    "immutable_commit": "FINAL_SCM_REVISION",
    "selected_relative_paths": "FINAL_SELECTED_RELATIVE_PATH",
    "artifact_path": "FINAL_SELECTED_RELATIVE_PATH",
    "target_id": "FINAL_TARGET_IDENTITY",
    "target_ids": "FINAL_TARGET_IDENTITY",
    "target_identities": "FINAL_TARGET_IDENTITY",
    "proposal_manifest_hash": "FINAL_PROPOSAL_MANIFEST_HASH",
    "production_output_hash": "FINAL_PRODUCTION_OUTPUT_HASH",
    "selector_output_hash": "FINAL_SELECTOR_OUTPUT_HASH",
    "trust_closure_hash": "FINAL_TRUST_CLOSURE_HASH",
    "candidate_pack_hash": "FINAL_CANDIDATE_PACK_HASH",
    "candidate_pack_tree_hash": "FINAL_CANDIDATE_PACK_HASH",
    "pack_content_hash": "FINAL_CANDIDATE_PACK_HASH",
    "oracle_hash": "FINAL_ORACLE_HASH",
    "golden_hash": "FINAL_GOLDEN_HASH",
    "report_hash": "FINAL_EVALUATION_HASH",
    "approval_hash": "FINAL_DECISION_HASH",
    "decision_hash": "FINAL_DECISION_HASH",
    "installed_pack_hash": "FINAL_PRODUCTION_OUTPUT_HASH",
}

# These final-observation fields must never become non-protected merely because
# an artifact is renamed to a PROCESS_AUDIT path.  The narrower set deliberately
# excludes generic audit integrity fields such as ``report_hash``: historical
# audit artifacts legitimately carry those without disclosing a frozen result.
_NEUTRAL_FORBIDDEN_DISCLOSURE_FIELDS = frozenset(
    {
        "source_archive_sha256",
        "raw_source_hashes",
        "canonical_source_hashes",
        "source_tree_hash",
        "selected_relative_paths",
        "target_identities",
        "production_output_hash",
        "trust_closure_hash",
        "candidate_pack_hash",
        "candidate_pack_tree_hash",
        "oracle_hash",
        "golden_hash",
        "decision_hash",
        "approval_hash",
        "installed_pack_hash",
        "pom_sha256",
        "scm_revision",
        "selector_output_hash",
        "proposal_manifest_hash",
    }
)

_ROLE_REQUIRED_CLAIMS = {
    FinalArtifactRole.FINAL_SOURCE_BYTES: frozenset({"FINAL_RAW_SOURCE_HASH"}),
    FinalArtifactRole.FINAL_ACQUISITION_BYTES: frozenset({"FINAL_ARCHIVE_HASH"}),
    FinalArtifactRole.FINAL_SOURCE_RECEIPT: frozenset(
        {
            "FINAL_ARCHIVE_HASH",
            "FINAL_POM_HASH",
            "FINAL_RAW_SOURCE_HASH",
            "FINAL_CANONICAL_SOURCE_HASH",
            "FINAL_SOURCE_TREE_HASH",
            "FINAL_SCM_REVISION",
        }
    ),
    FinalArtifactRole.FINAL_SELECTOR_OUTPUT: frozenset(
        {
            "FINAL_SELECTED_RELATIVE_PATH",
            "FINAL_RAW_SOURCE_HASH",
            "FINAL_CANONICAL_SOURCE_HASH",
            "FINAL_SELECTOR_OUTPUT_HASH",
        }
    ),
    FinalArtifactRole.FINAL_PHYSICAL_CENSUS: frozenset({"FINAL_EVALUATION_HASH"}),
    FinalArtifactRole.FINAL_PRODUCTION_OUTPUT: frozenset(
        {
            "FINAL_TARGET_IDENTITY",
            "FINAL_PROPOSAL_MANIFEST_HASH",
            "FINAL_TRUST_CLOSURE_HASH",
            "FINAL_CANDIDATE_PACK_HASH",
        }
    ),
    FinalArtifactRole.FINAL_CANDIDATE_PACK: frozenset(
        {"FINAL_CANDIDATE_PACK_HASH", "FINAL_TARGET_IDENTITY"}
    ),
    FinalArtifactRole.FINAL_ORACLE_OUTPUT: frozenset({"FINAL_ORACLE_HASH"}),
    FinalArtifactRole.FINAL_GOLDEN: frozenset({"FINAL_GOLDEN_HASH"}),
    FinalArtifactRole.FINAL_EVALUATION: frozenset({"FINAL_EVALUATION_HASH"}),
    FinalArtifactRole.FINAL_APPROVAL: frozenset({"FINAL_DECISION_HASH"}),
    FinalArtifactRole.FINAL_INSTALLATION: frozenset({"FINAL_PRODUCTION_OUTPUT_HASH"}),
    FinalArtifactRole.FINAL_DECISION: frozenset({"FINAL_DECISION_HASH"}),
}

_AUDIT_FIELDS = frozenset(
    {
        "acquired_at",
        "acquisition_run_id",
        "audit_event",
        "audit_hash",
        "host",
        "network_receipt_hash",
        "network_receipt_hashes",
        "redirect_chain",
        "remote_ref_response_hash",
        "commit_retrieval_request_hash",
        "commit_retrieval_response_hash",
        "detached_signature_sha256",
        "detached_signature_status",
        "detached_signature_url",
        "frozen_key_provenance_hash",
        "signature_verification_receipt_hash",
        "signer_fingerprint",
        "tag_object",
        "tag_to_commit_verified",
    }
)

_PREDECLARED_FIELDS = frozenset(
    {
        "canonical_repository_path",
        "classifier",
        "coordinate",
        "declared_name",
        "declaration_source",
        "extension",
        "f17_sha",
        "family_id",
        "license_evidence_mode",
        "license_status",
        "media_type",
        "name",
        "namespace",
        "repository",
        "repository_host",
        "repository_url",
        "requested_ref",
        "requested_url",
        "requirement",
        "schema_version",
        "source_url",
        "spdx_identifier",
        "version",
    }
)

_KNOWN_FIELDS = frozenset(
    {
        "acquired_at",
        "acquisition_run_id",
        "ambiguous_count",
        "archive_hash",
        "archive_hash_overlap_count",
        "archives",
        "artifact_authenticity_mode",
        "artifact_digest",
        "artifact_path",
        "artifact_size",
        "audit_event",
        "audit_hash",
        "bundle_tree_hash",
        "canonical_license_sha256",
        "canonical_only_match_count",
        "canonical_repository_path",
        "canonical_sha256",
        "canonical_source_hashes",
        "canonical_source_overlap_count",
        "classifier",
        "commit_retrieval_request_hash",
        "commit_retrieval_response_hash",
        "conflicts",
        "content_length",
        "coordinate",
        "coordinate_overlap_count",
        "correspondence",
        "correspondence_hash",
        "correspondence_overlap_count",
        "decision_hash",
        "decisions",
        "declaration_fingerprint_overlap_count",
        "declaration_fingerprints",
        "declaration_hash",
        "declaration_source",
        "declared_name",
        "denied",
        "detached_signature_sha256",
        "detached_signature_status",
        "detached_signature_url",
        "disclosure_reason",
        "downloaded_bytes_sha256",
        "downloaded_candidate_count",
        "eligible_distinct_root_count",
        "eligible_entry_count",
        "eligible_root",
        "eligible_roots",
        "entries",
        "entry_hash",
        "entry_hashes",
        "envelope_hash",
        "evaluator_run_count",
        "evidence_mode",
        "evidence_path",
        "exact_match",
        "exact_match_count",
        "extension",
        "f17_sha",
        "family_id",
        "file_count",
        "files",
        "final_url",
        "frozen_key_provenance_hash",
        "generated_match_count",
        "host",
        "immutable_commit",
        "license_claims",
        "license_evidence_mode",
        "license_path",
        "license_raw_sha256",
        "license_status",
        "license_texts",
        "manifest_hash",
        "match_count",
        "matching_classes",
        "media_type",
        "metrics_used_for_qualification",
        "minimum_distinct_eligible_roots",
        "minimum_eligible_roots",
        "name",
        "namespace",
        "network_acquisition_count",
        "network_receipt_hash",
        "network_receipt_hashes",
        "normalization_receipt_hash",
        "normalized_text_sha256",
        "originating_chain",
        "outcome",
        "pom_digest",
        "pom_hash",
        "pom_hash_overlap_count",
        "pom_repository_metadata",
        "pom_sha256",
        "previous_manifest_hash",
        "production_run_count",
        "provenance_envelope_hash",
        "provenance_identity_hash",
        "qualification_decision_hash",
        "qualification_reasons",
        "qualification_set_hash",
        "qualification_status",
        "raw_exact_match_count",
        "raw_sha256",
        "raw_source_hashes",
        "raw_source_overlap_count",
        "raw_text_sha256",
        "real_callable_source_file_count",
        "real_callable_target_count",
        "reason",
        "reasons",
        "receipt_hash",
        "redirect_chain",
        "registry_manifest_hash",
        "relocated_canonical_match_count",
        "relocated_match_count",
        "relocated_raw_match_count",
        "remote_ref_response_hash",
        "report_hash",
        "repository",
        "repository_host",
        "repository_metadata",
        "repository_path",
        "repository_url",
        "requested_ref",
        "requested_url",
        "required_failures",
        "requirement",
        "schema_version",
        "scm_revision",
        "scm_revision_overlap_count",
        "selected_path_manifest_hash",
        "selected_path_manifest_overlap_count",
        "selected_relative_paths",
        "selector_invocation_count",
        "selector_rerun_count",
        "semantic_identity_hash",
        "sidecar_sha256",
        "sidecar_verified",
        "signature_verification_receipt_hash",
        "signer_fingerprint",
        "source_archive_sha256",
        "source_tree_hash",
        "source_tree_overlap_count",
        "source_url",
        "source_url_overlap_count",
        "spdx_identifier",
        "status",
        "tag_object",
        "tag_to_commit_verified",
        "unmatched_count",
        "version",
        # Contract-generated M-33.6c artifacts.
        "artifact_type",
        "bindings",
        "contract_hash",
        "contract_version",
        "field_path",
        "license_expression",
        "manifest_entries",
        "manifest_hashes",
        "platform",
        "protected_roles",
        "role",
        "selected",
        "source_path",
        "targets",
        "validation_hash",
        "claims",
        "minimum_claim_denominator",
        "relative_path",
        "content_hash",
        "oracle_hash",
        "golden_hash",
        "approval_hash",
    }
)


_NONPROTECTED_ROLES = frozenset(
    {
        FinalArtifactRole.FINAL_ACQUISITION_BYTES,
        FinalArtifactRole.GENERIC_EMPTY_RESULT,
        FinalArtifactRole.PROCESS_AUDIT,
        FinalArtifactRole.QUALITY_LOG,
        FinalArtifactRole.HUMAN_READABLE_REPORT,
    }
)


def _field_contracts(
    role: FinalArtifactRole,
) -> tuple[FinalArtifactFieldContract, ...]:
    values = []
    for name in sorted(_KNOWN_FIELDS | set(_SECRET_CLAIMS)):
        if name in _SECRET_CLAIMS and role not in _NONPROTECTED_ROLES:
            classification = FinalArtifactFieldClass.SECRET
            claim = _SECRET_CLAIMS[name]
        elif name in _AUDIT_FIELDS:
            classification = FinalArtifactFieldClass.AUDIT
            claim = None
        elif name in _PREDECLARED_FIELDS:
            classification = FinalArtifactFieldClass.PREDECLARED
            claim = None
        else:
            classification = FinalArtifactFieldClass.PUBLIC
            claim = None
        values.append(FinalArtifactFieldContract(name, classification, claim))
    return tuple(values)


def _type(
    artifact_type,
    pattern,
    role,
    media_type,
    required=(),
    optional=(),
    *,
    forbidden=("password", "credential", "private_key", "secret_token"),
    sample,
):
    return FinalArtifactTypeContract(
        artifact_type,
        pattern,
        role,
        media_type,
        tuple(sorted(required)),
        tuple(sorted(optional)),
        tuple(sorted(forbidden)),
        _field_contracts(role) if media_type == "application/json" else (),
        sample,
    )


_QUALIFICATION_FIELDS = (
    "decisions",
    "eligible_roots",
    "metrics_used_for_qualification",
    "minimum_eligible_roots",
    "qualification_set_hash",
    "required_failures",
    "selector_invocation_count",
    "selector_rerun_count",
    "status",
)
_PROVENANCE_FIELDS = (
    "artifact_authenticity_mode",
    "artifact_digest",
    "audit_event",
    "conflicts",
    "coordinate",
    "correspondence",
    "envelope_hash",
    "license_claims",
    "license_evidence_mode",
    "license_status",
    "license_texts",
    "pom_digest",
    "pom_repository_metadata",
    "repository_metadata",
    "schema_version",
    "scm_revision",
    "semantic_identity_hash",
)
_DISCLOSED_ENTRY_FIELDS = (
    "archive_hash",
    "canonical_source_hashes",
    "coordinate",
    "correspondence_hash",
    "declaration_fingerprints",
    "disclosure_reason",
    "entry_hash",
    "originating_chain",
    "pom_hash",
    "raw_source_hashes",
    "schema_version",
    "scm_revision",
    "selected_path_manifest_hash",
    "selected_relative_paths",
    "source_tree_hash",
    "source_url",
    "version",
)


def _default_types() -> tuple[FinalArtifactTypeContract, ...]:
    all_json_fields = tuple(sorted(_KNOWN_FIELDS | set(_SECRET_CLAIMS)))
    return (
        _type(
            "source-snapshot",
            r"evaluation/[^/]+/source_snapshots/.+\.java",
            FinalArtifactRole.FINAL_SOURCE_BYTES,
            "text/x-java-source",
            sample="evaluation/m336c_h/source_snapshots/a/A.java",
        ),
        _type(
            "candidate-source-jar",
            r"evaluation/[^/]+/acquisition_bundle/candidates/[^/]+/source\.jar",
            FinalArtifactRole.FINAL_ACQUISITION_BYTES,
            "application/java-archive",
            sample="evaluation/m336b_final_java/acquisition_bundle/candidates/gson/source.jar",
        ),
        _type(
            "candidate-pom",
            r"evaluation/[^/]+/acquisition_bundle/candidates/[^/]+/pom\.xml",
            FinalArtifactRole.FINAL_ACQUISITION_BYTES,
            "application/xml",
            sample="evaluation/m336b_final_java/acquisition_bundle/candidates/gson/pom.xml",
        ),
        _type(
            "candidate-scm",
            r"evaluation/[^/]+/acquisition_bundle/candidates/[^/]+/scm\.zip",
            FinalArtifactRole.FINAL_ACQUISITION_BYTES,
            "application/zip",
            sample="evaluation/m336b_final_java/acquisition_bundle/candidates/gson/scm.zip",
        ),
        _type(
            "candidate-provenance",
            r"evaluation/[^/]+/acquisition_bundle/candidates/[^/]+/provenance\.json",
            FinalArtifactRole.FINAL_SOURCE_RECEIPT,
            "application/json",
            _PROVENANCE_FIELDS,
            sample="evaluation/m336b_final_java/acquisition_bundle/candidates/gson/provenance.json",
        ),
        _type(
            "candidate-qualification",
            r"evaluation/[^/]+/acquisition_bundle/candidates/[^/]+/qualification\.json",
            FinalArtifactRole.FINAL_SOURCE_RECEIPT,
            "application/json",
            (
                "coordinate",
                "decision_hash",
                "eligible_root",
                "evidence_mode",
                "provenance_envelope_hash",
                "provenance_identity_hash",
                "reasons",
                "requirement",
                "status",
            ),
            sample="evaluation/m336b_final_java/acquisition_bundle/candidates/gson/qualification.json",
        ),
        _type(
            "candidate-disclosed-match",
            r"evaluation/[^/]+/acquisition_bundle/candidates/[^/]+/disclosed_match\.json",
            FinalArtifactRole.FINAL_SOURCE_RECEIPT,
            "application/json",
            ("denied", "match_count", "matching_classes", "report_hash"),
            sample="evaluation/m336b_final_java/acquisition_bundle/candidates/gson/disclosed_match.json",
        ),
        _type(
            "qualification-set",
            r"evaluation/[^/]+/(?:acquisition_bundle/)?candidate_qualification_receipts\.json",
            FinalArtifactRole.FINAL_SOURCE_RECEIPT,
            "application/json",
            _QUALIFICATION_FIELDS,
            sample="evaluation/m336b_final_java/candidate_qualification_receipts.json",
        ),
        _type(
            "jdk-provider",
            r"evaluation/[^/]+/jdk_provider_receipt\.json",
            FinalArtifactRole.FINAL_SOURCE_RECEIPT,
            "application/json",
            (),
            all_json_fields,
            sample="evaluation/m336c_h/jdk_provider_receipt.json",
        ),
        _type(
            "source-acquisition",
            r"evaluation/[^/]+/(?:acquisition_bundle/)?source_acquisition_receipts\.json",
            FinalArtifactRole.FINAL_SOURCE_RECEIPT,
            "application/json",
            ("archives",),
            (
                "downloaded_candidate_count",
                "eligible_distinct_root_count",
                "f17_sha",
                "manifest_hash",
                "qualification_set_hash",
                "registry_manifest_hash",
                "schema_version",
            ),
            sample="evaluation/m336b_final_java/source_acquisition_receipts.json",
        ),
        _type(
            "sealed-acquisition",
            r"evaluation/[^/]+/sealed_acquisition_bundle\.json",
            FinalArtifactRole.FINAL_SOURCE_RECEIPT,
            "application/json",
            (
                "bundle_tree_hash",
                "file_count",
                "files",
                "manifest_hash",
                "network_acquisition_count",
                "registry_manifest_hash",
                "schema_version",
                "selector_invocation_count",
                "selector_rerun_count",
            ),
            sample="evaluation/m336b_final_java/sealed_acquisition_bundle.json",
        ),
        _type(
            "selector",
            r"evaluation/[^/]+/(?:selector_receipt|selection_execution)\.json",
            FinalArtifactRole.FINAL_SELECTOR_OUTPUT,
            "application/json",
            (),
            all_json_fields,
            sample="evaluation/m336c_h/selector_receipt.json",
        ),
        _type(
            "physical-census",
            r"evaluation/[^/]+/physical_census\.json",
            FinalArtifactRole.FINAL_PHYSICAL_CENSUS,
            "application/json",
            (
                "downloaded_candidate_count",
                "eligible_distinct_root_count",
                "real_callable_source_file_count",
                "real_callable_target_count",
                "reason",
                "report_hash",
                "schema_version",
                "selector_invocation_count",
                "status",
            ),
            sample="evaluation/m336b_final_java/physical_census.json",
        ),
        _type(
            "source-overlap",
            r"evaluation/[^/]+/source_overlap\.json",
            FinalArtifactRole.FINAL_EVALUATION,
            "application/json",
            (
                "archive_hash_overlap_count",
                "canonical_source_overlap_count",
                "coordinate_overlap_count",
                "correspondence_overlap_count",
                "declaration_fingerprint_overlap_count",
                "pom_hash_overlap_count",
                "raw_source_overlap_count",
                "report_hash",
                "schema_version",
                "scm_revision_overlap_count",
                "selected_path_manifest_overlap_count",
                "source_tree_overlap_count",
                "source_url_overlap_count",
                "status",
            ),
            sample="evaluation/m336b_final_java/source_overlap.json",
        ),
        _type(
            "blocked-result",
            r"evaluation/[^/]+/blocked_result\.json",
            FinalArtifactRole.FINAL_DECISION,
            "application/json",
            (
                "decision_hash",
                "downloaded_candidate_count",
                "eligible_distinct_root_count",
                "evaluator_run_count",
                "f17_sha",
                "minimum_distinct_eligible_roots",
                "outcome",
                "production_run_count",
                "qualification_set_hash",
                "reason",
                "registry_manifest_hash",
                "schema_version",
                "selector_invocation_count",
                "selector_rerun_count",
            ),
            sample="evaluation/m336b_final_java/blocked_result.json",
        ),
        _type(
            "disclosed-entry",
            r"artifacts/acquisition/disclosed_java/entries/[0-9a-f]{64}\.json",
            FinalArtifactRole.FINAL_SOURCE_RECEIPT,
            "application/json",
            _DISCLOSED_ENTRY_FIELDS,
            sample="artifacts/acquisition/disclosed_java/entries/" + "a" * 64 + ".json",
        ),
        _type(
            "disclosed-manifest",
            r"artifacts/acquisition/disclosed_java/(?:registry_manifest|manifests/[0-9a-f]{64})\.json",
            FinalArtifactRole.FINAL_SOURCE_RECEIPT,
            "application/json",
            (
                "entry_hashes",
                "manifest_hash",
                "previous_manifest_hash",
                "schema_version",
            ),
            sample="artifacts/acquisition/disclosed_java/registry_manifest.json",
        ),
        _type(
            "production",
            r"evaluation/[^/]+/(?:production_output|production_disclosure|production_counts|component_manifest|packability_report|trust_closure|candidate_replay|platform_comparison|production_summary)\.json",
            FinalArtifactRole.FINAL_PRODUCTION_OUTPUT,
            "application/json",
            (),
            all_json_fields,
            sample="evaluation/m336c_h/production_output.json",
        ),
        _type(
            "candidate-pack-disclosure",
            r"evaluation/[^/]+/(?:candidate_pack/(?:disclosure|candidate_pack)|candidate_pack(?:_tree|_disclosure)?)\.json",
            FinalArtifactRole.FINAL_CANDIDATE_PACK,
            "application/json",
            (),
            all_json_fields,
            sample="evaluation/m336c_h/candidate_pack/disclosure.json",
        ),
        _type(
            "candidate-pack",
            r"evaluation/[^/]+/candidate_pack/(?!disclosure\.json$|candidate_pack\.json$).+",
            FinalArtifactRole.FINAL_CANDIDATE_PACK,
            "application/octet-stream",
            sample="evaluation/m336c_h/candidate_pack/manifest.json",
        ),
        _type(
            "oracle-json",
            r"evaluation/[^/]+/(?:oracle/.+|oracle_disclosure)\.json",
            FinalArtifactRole.FINAL_ORACLE_OUTPUT,
            "application/json",
            (),
            all_json_fields,
            sample="evaluation/m336c_h/oracle/output.json",
        ),
        _type(
            "oracle",
            r"evaluation/[^/]+/oracle/.+(?<!\.json)",
            FinalArtifactRole.FINAL_ORACLE_OUTPUT,
            "application/octet-stream",
            sample="evaluation/m336c_h/oracle/output.bin",
        ),
        _type(
            "golden-json",
            r"evaluation/[^/]+/(?:goldens/.+|golden_disclosure|golden_.+)\.json",
            FinalArtifactRole.FINAL_GOLDEN,
            "application/json",
            (),
            all_json_fields,
            sample="evaluation/m336c_h/goldens/golden.json",
        ),
        _type(
            "golden",
            r"evaluation/[^/]+/goldens/.+(?<!\.json)",
            FinalArtifactRole.FINAL_GOLDEN,
            "application/octet-stream",
            sample="evaluation/m336c_h/goldens/golden.bin",
        ),
        _type(
            "final-decision",
            r"evaluation/[^/]+/(?:final_decision|outcome)\.json",
            FinalArtifactRole.FINAL_DECISION,
            "application/json",
            (),
            all_json_fields,
            sample="evaluation/m336c_h/final_decision.json",
        ),
        _type(
            "approval",
            r"evaluation/[^/]+/(?:approval|release_approval)\.json",
            FinalArtifactRole.FINAL_APPROVAL,
            "application/json",
            (),
            all_json_fields,
            sample="evaluation/m336c_h/release_approval.json",
        ),
        _type(
            "installation",
            r"evaluation/[^/]+/(?:installation|runtime_proof)\.json",
            FinalArtifactRole.FINAL_INSTALLATION,
            "application/json",
            (),
            all_json_fields,
            sample="evaluation/m336c_h/installation.json",
        ),
        _type(
            "evaluation",
            r"evaluation/[^/]+/(?:evaluation.*|metrics_.*|semantic_metrics|trust_metrics|diagnostic_metrics|replay_mutations|final_metrics|final_gate|role_manifest|disclosure_report|input|corpus_census)\.json",
            FinalArtifactRole.FINAL_EVALUATION,
            "application/json",
            (),
            all_json_fields,
            sample="evaluation/m336c_h/evaluation_report.json",
        ),
        _type(
            "process-audit-json",
            r"evaluation/[^/]+/(?:.+audit|platform/.+)\.json",
            FinalArtifactRole.PROCESS_AUDIT,
            "application/json",
            (),
            all_json_fields + ("count",),
            sample="evaluation/m336c_h/renamed_audit.json",
        ),
        _type(
            "installed-pack",
            r"evaluation/[^/]+/installed_pack/.+",
            FinalArtifactRole.FINAL_INSTALLATION,
            "application/octet-stream",
            sample="evaluation/m336c_h/installed_pack/manifest.json",
        ),
        _type(
            "generic-empty-result",
            r"evaluation/[^/]+/(?:generic_empty_result|empty_result)\.json",
            FinalArtifactRole.GENERIC_EMPTY_RESULT,
            "application/json",
            (),
            all_json_fields,
            sample="evaluation/m336c_h/generic_empty_result.json",
        ),
        _type(
            "process-audit-text",
            r"evaluation/[^/]+/.+audit\.txt",
            FinalArtifactRole.PROCESS_AUDIT,
            "text/plain",
            sample="evaluation/m336c_h/source_copy_audit.txt",
        ),
        _type(
            "quality-log",
            r"runs/.+\.(?:log|txt)",
            FinalArtifactRole.QUALITY_LOG,
            "text/plain",
            sample="runs/m336c_final_gate/windows/full.log",
        ),
        _type(
            "human-report",
            r"(?:docs|runs)/.+\.md",
            FinalArtifactRole.HUMAN_READABLE_REPORT,
            "text/markdown",
            sample="docs/m336c_report.md",
        ),
    )


class FinalArtifactContractRegistry:
    def __init__(self, artifact_types=None):
        defaults = _default_types()
        if artifact_types is not None and tuple(artifact_types) != defaults:
            raise ValueError("caller-supplied final artifact contracts are forbidden")
        types = defaults
        protected = tuple(
            role for role in FinalArtifactRole if role not in _NONPROTECTED_ROLES
        )
        body = {
            "schema_version": FINAL_ARTIFACT_CONTRACT_VERSION,
            "artifact_types": types,
            "protected_roles": protected,
        }
        self.contract = FinalArtifactContract(**body, contract_hash=content_hash(body))
        self._compiled = tuple(
            (item, re.compile(r"\A" + item.path_pattern + r"\Z")) for item in types
        )
        self._verify_registry()

    def match(self, path: str) -> FinalArtifactTypeContract:
        normalized = canonical_artifact_path(path)
        matches = tuple(
            item for item, pattern in self._compiled if pattern.fullmatch(normalized)
        )
        if len(matches) != 1:
            raise ValueError(
                f"final artifact path matched {len(matches)} contracts: {normalized}"
            )
        return matches[0]

    def validate(self, path: str, raw: bytes) -> FinalArtifactValidation:
        contract = self.match(path)
        observed = ()
        missing = ()
        unexpected = ()
        unclassified = ()
        disclosure = ()
        public = ()
        if contract.media_type == "application/json":
            try:
                value = json.loads(
                    raw.decode("utf-8", errors="strict"), object_pairs_hook=_unique
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(
                    "contract JSON is malformed or has duplicate keys"
                ) from exc
            if not isinstance(value, dict):
                raise TypeError("contract JSON root must be an object")
            if "schema_version" in value and value["schema_version"] not in {1, 2}:
                raise ValueError("contract JSON schema version mismatch")
            observed = tuple(sorted(value))
            required = set(contract.required_fields)
            allowed = required | set(contract.optional_fields)
            missing = tuple(sorted(required - set(value)))
            unexpected = tuple(sorted(set(value) - allowed))
            names = tuple(sorted(_walk_field_names(value)))
            contracts = {item.field_name: item for item in contract.field_contracts}
            unclassified = tuple(name for name in names if name not in contracts)
            disclosure = tuple(
                name
                for name in names
                if name in contracts
                and contracts[name].mandatory_disclosure_claim is not None
            )
            public = tuple(
                name
                for name in names
                if name in contracts
                and contracts[name].field_class
                in {FinalArtifactFieldClass.PUBLIC, FinalArtifactFieldClass.PREDECLARED}
            )
            forbidden = set(contract.forbidden_fields) & set(names)
            unexpected = tuple(sorted(set(unexpected) | forbidden))
        status = (
            "PASS" if not missing and not unexpected and not unclassified else "FAIL"
        )
        body = {
            "relative_path": canonical_artifact_path(path),
            "artifact_type": contract.artifact_type,
            "role": contract.role,
            "observed_fields": observed,
            "missing_fields": missing,
            "unexpected_fields": unexpected,
            "unclassified_fields": unclassified,
            "disclosure_fields": disclosure,
            "public_or_predeclared_fields": public,
            "status": status,
        }
        return FinalArtifactValidation(**body, validation_hash=content_hash(body))

    def disclosure_claim_specs(self, path: str, raw: bytes):
        contract = self.match(path)
        if contract.media_type != "application/json":
            return ()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
        fields = {item.field_name: item for item in contract.field_contracts}
        names = set(_walk_field_names(value))
        if names & set(contract.forbidden_fields):
            raise ValueError("cannot extract disclosure claims from invalid artifact")
        result = []
        for field_path, name, leaf in _walk_leaves(value):
            field = fields.get(name)
            if field is None:
                continue
            if field.mandatory_disclosure_claim and isinstance(leaf, (str, int, bool)):
                result.append((field.mandatory_disclosure_claim, field_path, str(leaf)))
        return tuple(sorted(set(result)))

    def required_claim_kinds(self, role: FinalArtifactRole) -> frozenset[str]:
        return _ROLE_REQUIRED_CLAIMS.get(role, frozenset())

    def disclosure_field_names(self) -> frozenset[str]:
        """Return fields that remain disclosure-sensitive under every path role."""

        return _NEUTRAL_FORBIDDEN_DISCLOSURE_FIELDS

    def _verify_registry(self):
        if not self.contract.artifact_types:
            raise ValueError("final artifact contract denominator is empty")
        patterns = tuple(item.path_pattern for item in self.contract.artifact_types)
        if len(patterns) != len(set(patterns)):
            raise ValueError("duplicate final artifact contract pattern")
        for item in self.contract.artifact_types:
            matches = tuple(
                other.artifact_type
                for other, pattern in self._compiled
                if pattern.fullmatch(item.sample_path)
            )
            if matches != (item.artifact_type,):
                raise ValueError("overlapping final artifact contract patterns")


def canonical_artifact_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip("/")
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or pure.as_posix() != normalized
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ValueError("final artifact path is not canonical")
    return normalized


def _walk_field_names(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_field_names(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_field_names(child)


def _walk_leaves(value, path="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_leaves(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_leaves(child, f"{path}[{index}]")
    else:
        name = re.split(r"\.|\[", path)[-1].rstrip("]")
        if name.isdigit():
            parent = path.rsplit("[", 1)[0]
            name = parent.rsplit(".", 1)[-1]
        yield path, name, value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


FINAL_ARTIFACT_CONTRACT_REGISTRY = FinalArtifactContractRegistry()


def contract_binary_claim(path: str, raw: bytes) -> tuple[str, str, str]:
    contract = FINAL_ARTIFACT_CONTRACT_REGISTRY.match(path)
    if contract.role is FinalArtifactRole.FINAL_SOURCE_BYTES:
        return "FINAL_RAW_SOURCE_HASH", "$bytes", bytes_hash(raw)
    if contract.role is FinalArtifactRole.FINAL_ACQUISITION_BYTES:
        return "FINAL_ARCHIVE_HASH", "$bytes", bytes_hash(raw)
    raise ValueError("artifact does not have a binary disclosure claim")
