"""Strict versioned public-artifact and local-source-vault contracts."""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
import stat
import unicodedata
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DRIVE = re.compile(r"^[A-Za-z]:")
_SECRET_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
)
_SECRET_VALUE = re.compile(
    r"(?i)(?:api[_-]?key|password|passwd|secret|bearer|authorization|"
    r"aws_secret_access_key|github_token)\s*[:=]\s*\S+"
)
_JAVA_EXCERPT = re.compile(
    r"(?m)(?:^|\n)\s*(?:package\s+[A-Za-z_$][\w.$]*\s*;|"
    r"import\s+(?:static\s+)?[A-Za-z_$][\w.$*]*\s*;|"
    r"(?:public|protected|private)\s+(?:(?:static|final|abstract|sealed)\s+)*"
    r"(?:class|interface|enum|record)\s+[A-Za-z_$][\w$]*)"
)
_SOURCE_MARKERS = (
    b"PK\x03\x04",
    b"public class ",
    b"public interface ",
    b"package java.",
)


class PublicArtifactRole(StrEnum):
    FREEZE = "FREEZE"
    ACQUISITION_RECEIPTS = "ACQUISITION_RECEIPTS"
    QUALIFICATION = "QUALIFICATION"
    SELECTOR = "SELECTOR"
    PRODUCTION = "PRODUCTION"
    CANDIDATE_PACK = "CANDIDATE_PACK"
    VAULT_HASH_MANIFEST = "VAULT_HASH_MANIFEST"
    SEAL = "SEAL"
    EVALUATION = "EVALUATION"
    READINESS = "READINESS"


@dataclass(frozen=True)
class RecursiveFieldContract:
    name: str
    value_type: str
    required: bool = True
    enum_values: tuple[str, ...] = ()
    pattern: str | None = None
    minimum: int | None = None
    maximum: int | None = None
    min_items: int | None = None
    max_items: int | None = None
    unique_items: bool = False
    sorted_items: bool = False
    allow_null: bool = False
    item_contract: RecursiveFieldContract | None = None
    tuple_fields: tuple[RecursiveFieldContract, ...] = ()
    object_fields: tuple[RecursiveFieldContract, ...] = ()


@dataclass(frozen=True)
class PublicArtifactTypeContract:
    artifact_type: str
    path_pattern: str
    role: PublicArtifactRole
    media_type: str
    schema_version: int
    fields: tuple[RecursiveFieldContract, ...]
    expected_magic_hex: str | None
    minimum_bytes: int | None
    maximum_bytes: int | None
    contract_hash: str


@dataclass(frozen=True)
class PublicArtifactValidation:
    relative_path: str
    artifact_type: str
    role: PublicArtifactRole
    byte_size: int
    sha256: str
    status: str
    validation_hash: str


def _field(name: str, value_type: str, **kwargs) -> RecursiveFieldContract:
    return RecursiveFieldContract(name, value_type, **kwargs)


def _artifact(
    name: str,
    pattern: str,
    role: PublicArtifactRole,
    fields: tuple[RecursiveFieldContract, ...],
    *,
    media_type: str = "application/json",
    expected_magic_hex: str | None = None,
    minimum_bytes: int | None = None,
    maximum_bytes: int | None = None,
) -> PublicArtifactTypeContract:
    body = {
        "artifact_type": name,
        "path_pattern": pattern,
        "role": role,
        "media_type": media_type,
        "schema_version": 1,
        "fields": fields,
        "expected_magic_hex": expected_magic_hex,
        "minimum_bytes": minimum_bytes,
        "maximum_bytes": maximum_bytes,
    }
    return PublicArtifactTypeContract(**body, contract_hash=content_hash(body))


_HASH = _field("hash", "string", pattern=r"[0-9a-f]{64}")
_STRING_ITEM = _field("item", "string")
_GIT_SHA_FIELD = _field("git_sha", "string", pattern=r"[0-9a-f]{40}")
_STRING_HASH_PAIR = _field(
    "pair",
    "array",
    min_items=2,
    max_items=2,
    tuple_fields=(_STRING_ITEM, _HASH),
)
_STRING_INTEGER_PAIR = _field(
    "pair",
    "array",
    min_items=2,
    max_items=2,
    tuple_fields=(_STRING_ITEM, _field("count", "integer", minimum=0)),
)
_AUTHORITY_RECEIPT_FIELDS = (
    _field("authority_root_hash", "string", pattern=r"[0-9a-f]{64}"),
    _field("authority_policy_id", "string"),
    _field("authority_policy_version", "string"),
    _field("f19_sha", "string", pattern=r"[0-9a-f]{40}"),
    _field("acquisition_run_id", "string"),
    _field("candidate_family_id", "string"),
    _field("maven_coordinate", "string"),
    _field("source_repository_url", "string"),
    _field("source_jar_sha256", "string", pattern=r"[0-9a-f]{64}"),
    _field("pom_sha256", "string", pattern=r"[0-9a-f]{64}"),
    _field("immutable_scm_commit", "string", pattern=r"[0-9a-f]{40}"),
    _field("scm_archive_sha256", "string", pattern=r"[0-9a-f]{64}"),
    _field("source_tree_hash", "string", pattern=r"[0-9a-f]{64}"),
    _field("local_vault_manifest_hash", "string", pattern=r"[0-9a-f]{64}"),
    _field(
        "permitted_source_use_scopes",
        "array",
        min_items=1,
        unique_items=True,
        item_contract=_STRING_ITEM,
    ),
    _field(
        "permitted_publication_targets",
        "array",
        min_items=1,
        unique_items=True,
        item_contract=_STRING_ITEM,
    ),
    _field(
        "denied_publication_targets",
        "array",
        min_items=1,
        unique_items=True,
        item_contract=_STRING_ITEM,
    ),
    _field("parent_receipt_hash", "string", pattern=r"[0-9a-f]{64}", allow_null=True),
    _field("receipt_hash", "string", pattern=r"[0-9a-f]{64}"),
)
_CORRESPONDENCE_ENTRY_FIELDS = (
    _field("artifact_path", "string"),
    _field("scm_path", "string", allow_null=True),
    _field(
        "correspondence_class",
        "string",
        enum_values=(
            "RAW_EXACT_MATCH",
            "CANONICAL_TEXT_EXACT_MATCH",
            "PATH_RELOCATED_RAW_MATCH",
            "PATH_RELOCATED_CANONICAL_MATCH",
            "EXACT_MATCH",
            "PATH_RELOCATED_EXACT_CONTENT",
            "GENERATED_WITH_VERIFIED_PROVENANCE",
            "UNMATCHED",
            "AMBIGUOUS_MATCH",
        ),
    ),
    _field("selected", "boolean"),
    _field("complete", "boolean"),
    _field("reason", "string"),
    _field("decision_hash", "string", pattern=r"[0-9a-f]{64}"),
)
_CORRESPONDENCE_FIELDS = (
    _field(
        "entries",
        "array",
        min_items=1,
        unique_items=True,
        sorted_items=True,
        item_contract=_field(
            "entry", "object", object_fields=_CORRESPONDENCE_ENTRY_FIELDS
        ),
    ),
    *(
        _field(name, "integer", minimum=0)
        for name in (
            "total_candidate_java_entries",
            "raw_exact_entries",
            "canonical_only_entries",
            "relocated_entries",
            "generated_entries",
            "unmatched_entries",
            "ambiguous_entries",
            "selected_entries",
            "selected_entries_with_complete_scm_correspondence",
        )
    ),
    _field("complete_for_selected", "boolean"),
    _field("correspondence_hash", "string", pattern=r"[0-9a-f]{64}"),
)
_ACQUISITION_RECEIPT_FIELDS = (
    _field("family_id", "string"),
    _field("coordinate", "string"),
    _field("source_url", "string"),
    _field("source_jar_sha256", "string", pattern=r"[0-9a-f]{64}"),
    _field("source_jar_size", "integer", minimum=0),
    _field("pom_sha256", "string", pattern=r"[0-9a-f]{64}"),
    _field("immutable_scm_commit", "string", pattern=r"[0-9a-f]{40}"),
    _field("scm_archive_sha256", "string", pattern=r"[0-9a-f]{64}"),
    _field("scm_archive_size", "integer", minimum=0),
    _field("source_tree_hash", "string", pattern=r"[0-9a-f]{64}"),
    _field("authority_receipt_hash", "string", pattern=r"[0-9a-f]{64}"),
)
_QUALIFICATION_DECISION_FIELDS = (
    _field("family_id", "string"),
    _field("organization_id", "string"),
    _field("coordinate", "string"),
    _field(
        "source_authenticity_decision",
        "string",
        enum_values=("AUTHENTIC", "REVIEW_REQUIRED"),
    ),
    _field(
        "knowledge_acquisition_eligibility_decision",
        "string",
        enum_values=("ELIGIBLE_FOR_ANALYSIS", "INELIGIBLE"),
    ),
    _field(
        "source_retention_decision",
        "string",
        enum_values=("ALLOWED_SEALED_VAULT_ONLY", "DENIED"),
    ),
    _field(
        "raw_source_publication_decision",
        "string",
        enum_values=("DENIED", "NOT_AUTHORIZED"),
    ),
    _field(
        "source_excerpt_publication_decision",
        "string",
        enum_values=("DENIED", "NOT_AUTHORIZED"),
    ),
    _field(
        "derived_pack_publication_decision",
        "string",
        enum_values=("ALLOWED", "NOT_APPLICABLE"),
    ),
    _field(
        "metrics_publication_decision",
        "string",
        enum_values=("ALLOWED", "NOT_AUTHORIZED"),
    ),
    _field(
        "scm_correspondence_decision",
        "string",
        enum_values=("COMPLETE", "INCOMPLETE"),
    ),
    _field(
        "scoped_license_decision",
        "string",
        enum_values=("RESOLVED", "REVIEW_REQUIRED"),
    ),
    _field("candidate_eligible_source_set_count", "integer", minimum=0),
    _field(
        "scoped_license_expressions",
        "array",
        unique_items=True,
        sorted_items=True,
        item_contract=_STRING_ITEM,
    ),
    _field("legal_document_count", "integer", minimum=0),
    _field("unclassified_legal_document_count", "integer", minimum=0),
    _field("authority_receipt_hash", "string", pattern=r"[0-9a-f]{64}"),
    _field("authority", "object", object_fields=_AUTHORITY_RECEIPT_FIELDS),
    _field(
        "qualification_errors",
        "array",
        unique_items=True,
        item_contract=_STRING_ITEM,
    ),
    _field("decision_hash", "string", pattern=r"[0-9a-f]{64}"),
)
_VAULT_ROW_FIELDS = (
    _field("candidate_id", "string"),
    _field("relative_path", "string"),
    _field(
        "role",
        "string",
        enum_values=(
            "SOURCE_JAR",
            "POM",
            "SCM_ARCHIVE",
            "JAVA_SOURCE",
            "LEGAL_DOCUMENT",
            "QUALIFICATION_WORK",
        ),
    ),
    _field("byte_size", "integer", minimum=0),
    _field("sha256", "string", pattern=r"[0-9a-f]{64}"),
    _field("parent_artifact_hash", "string", pattern=r"[0-9a-f]{64}"),
    _field("source_use_receipt_hash", "string", pattern=r"[0-9a-f]{64}"),
    _field("row_hash", "string", pattern=r"[0-9a-f]{64}"),
)
_READINESS_CRITERION_FIELDS = (
    _field("name", "string"),
    _field(
        "primary_report_hashes",
        "array",
        min_items=1,
        unique_items=True,
        sorted_items=True,
        item_contract=_HASH,
    ),
    _field("numerator", "integer", minimum=0),
    _field("denominator", "integer", minimum=1),
    _field("formula", "string", enum_values=("EQ", "GE", "RATIO_EQ", "RATIO_GE")),
    _field("observed_result", "string"),
    _field("threshold", "string"),
    _field("passed", "boolean"),
    _field("criterion_hash", "string", pattern=r"[0-9a-f]{64}"),
)

_PUBLIC_CONTRACTS = (
    _artifact(
        "freeze-manifest",
        r"freeze/m336d_freeze_manifest\.json",
        PublicArtifactRole.FREEZE,
        (
            _field("schema_version", "integer", minimum=1, maximum=1),
            _field("r19_sha", "string", pattern=r"[0-9a-f]{40}"),
            _field("authority_statement_sha256", "string", pattern=r"[0-9a-f]{64}"),
            _field("authority_root_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("candidate_pool_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("selector_policy_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("thresholds_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("contract_registry_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field(
                "frozen_artifacts",
                "array",
                min_items=1,
                unique_items=True,
                sorted_items=True,
                item_contract=_STRING_HASH_PAIR,
            ),
            _field("freeze_manifest_hash", "string", pattern=r"[0-9a-f]{64}"),
        ),
    ),
    _artifact(
        "acquisition-receipts",
        r"h19/acquisition_receipts\.json",
        PublicArtifactRole.ACQUISITION_RECEIPTS,
        (
            _field("schema_version", "integer", minimum=1, maximum=1),
            _field("f19_sha", "string", pattern=r"[0-9a-f]{40}"),
            _field("acquisition_run_id", "string"),
            _field("global_acquisition_count", "integer", minimum=1, maximum=1),
            _field("candidate_count", "integer", minimum=1),
            _field(
                "receipts",
                "array",
                min_items=1,
                max_items=30,
                unique_items=True,
                item_contract=_field(
                    "receipt", "object", object_fields=_ACQUISITION_RECEIPT_FIELDS
                ),
            ),
            _field("report_hash", "string", pattern=r"[0-9a-f]{64}"),
        ),
    ),
    _artifact(
        "qualification-decisions",
        r"h19/qualification_decisions\.json",
        PublicArtifactRole.QUALIFICATION,
        (
            _field("schema_version", "integer", minimum=1, maximum=1),
            _field("candidate_count", "integer", minimum=1),
            _field("analysis_eligible_root_count", "integer", minimum=0),
            _field("analysis_eligible_java_entry_count", "integer", minimum=0),
            _field("raw_source_publication_root_count", "integer", minimum=0),
            _field("source_excerpt_publication_root_count", "integer", minimum=0),
            _field("derived_pack_publication_root_count", "integer", minimum=0),
            _field("metrics_publication_root_count", "integer", minimum=0),
            _field("typed_decisions_per_candidate", "integer", minimum=10, maximum=10),
            _field(
                "decisions",
                "array",
                min_items=1,
                max_items=30,
                unique_items=True,
                item_contract=_field(
                    "decision", "object", object_fields=_QUALIFICATION_DECISION_FIELDS
                ),
            ),
            _field("report_hash", "string", pattern=r"[0-9a-f]{64}"),
        ),
    ),
    _artifact(
        "selector-receipt",
        r"h19/selector_receipt\.json",
        PublicArtifactRole.SELECTOR,
        (
            _field("schema_version", "integer", minimum=1, maximum=1),
            _field("selector_version", "string"),
            _field("selector_seed", "string"),
            _field("f19_sha", "string", pattern=r"[0-9a-f]{40}"),
            _field("selector_invocation_count", "integer", minimum=1, maximum=1),
            _field("selector_rerun_count", "integer", minimum=0, maximum=0),
            _field("selected_file_count", "integer", minimum=180, maximum=180),
            _field("selected_root_count", "integer", minimum=3),
            _field("maximum_one_root_fraction", "string", pattern=r"0\.[0-9]{6}"),
            _field("metrics_used_count", "integer", minimum=0, maximum=0),
            _field("oracle_golden_read_count", "integer", minimum=0, maximum=0),
            _field("selected_manifest_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field(
                "root_distribution",
                "array",
                min_items=3,
                unique_items=True,
                sorted_items=True,
                item_contract=_STRING_INTEGER_PAIR,
            ),
            _field("receipt_hash", "string", pattern=r"[0-9a-f]{64}"),
        ),
    ),
    _artifact(
        "production-output",
        r"h19/production/production_summary\.json",
        PublicArtifactRole.PRODUCTION,
        (
            _field("schema_version", "integer", minimum=1, maximum=1),
            _field("platform", "string", enum_values=("windows", "karina")),
            _field("production_output_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("production_batch_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("component_manifest_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("candidate_pack_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("candidate_tree_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("candidate_replay_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("candidate_replay_status", "string", enum_values=("PASS",)),
            _field(
                "production_evaluator_dependency_count", "integer", minimum=0, maximum=0
            ),
            _field("production_golden_read_count", "integer", minimum=0, maximum=0),
            _field("torch_imported", "boolean"),
            _field("status", "string", enum_values=("PASS",)),
            _field("summary_hash", "string", pattern=r"[0-9a-f]{64}"),
        ),
    ),
    _artifact(
        "candidate-pack",
        r"h19/candidate_pack\.json",
        PublicArtifactRole.CANDIDATE_PACK,
        (
            _field("schema_version", "integer", minimum=1, maximum=1),
            _field("candidate_pack_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("candidate_tree_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("compiled", "boolean"),
            _field("replay_passed", "boolean"),
            _field("report_hash", "string", pattern=r"[0-9a-f]{64}"),
        ),
    ),
    _artifact(
        "vault-hash-manifest",
        r"h19/vault_manifest\.json",
        PublicArtifactRole.VAULT_HASH_MANIFEST,
        (
            _field("schema_version", "integer", minimum=1, maximum=1),
            _field("f19_sha", "string", pattern=r"[0-9a-f]{40}"),
            _field("acquisition_run_id", "string"),
            _field("file_count", "integer", minimum=1),
            _field("tree_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("content_manifest_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("permission_report_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("write_protection_report_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("seal_timestamp", "string"),
            _field(
                "rows",
                "array",
                min_items=1,
                unique_items=True,
                item_contract=_field("row", "object", object_fields=_VAULT_ROW_FIELDS),
            ),
            _field(
                "row_hashes",
                "array",
                min_items=1,
                unique_items=True,
                item_contract=_HASH,
            ),
            _field("manifest_hash", "string", pattern=r"[0-9a-f]{64}"),
        ),
    ),
    _artifact(
        "h19-seal",
        r"h19/h19_seal\.json",
        PublicArtifactRole.SEAL,
        (
            _field("schema_version", "integer", minimum=1, maximum=1),
            _field("f19_sha", "string", pattern=r"[0-9a-f]{40}"),
            _field("public_payload_file_count", "integer", minimum=1),
            _field("public_tree_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("windows_production_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("karina_production_hash", "string", pattern=r"[0-9a-f]{64}"),
            _field("platform_difference_count", "integer", minimum=0, maximum=0),
            _field("production_completed_before_evaluator", "boolean"),
            _field("fresh_source_leak_count", "integer", minimum=0, maximum=0),
            _field("seal_hash", "string", pattern=r"[0-9a-f]{64}"),
        ),
    ),
    _artifact(
        "evaluation",
        r"e19/evaluation\.json",
        PublicArtifactRole.EVALUATION,
        (
            _field("schema_version", "integer", minimum=1, maximum=1),
            _field("h19_sha", "string", pattern=r"[0-9a-f]{40}"),
            _field("platform", "string", enum_values=("windows", "karina")),
            _field("production_sealed_before_evaluator", "boolean"),
            _field(
                "production_reference_license_agreement",
                "string",
                pattern=r"[01]\.[0-9]{6}",
            ),
            _field(
                "false_automatic_license_identity_count",
                "integer",
                minimum=0,
                maximum=0,
            ),
            _field(
                "selected_root_unresolved_disagreement_count",
                "integer",
                minimum=0,
                maximum=0,
            ),
            _field("location_precision", "string"),
            _field("location_recall", "string"),
            _field("semantic_precision", "string"),
            _field("semantic_recall", "string"),
            _field("trust_precision", "string"),
            _field("trust_coverage", "string"),
            _field("field_evidence_exactness", "string"),
            _field("resolution_agreement", "string"),
            _field("wrong_trusted_count", "integer", minimum=0, maximum=0),
            _field("post_trust_pack_failures", "integer", minimum=0, maximum=0),
            _field("candidate_pack_compiled", "boolean"),
            _field("candidate_replay_status", "string", enum_values=("PASS",)),
            _field("runtime_status", "string", enum_values=("PASS",)),
            _field("runtime_network_access_count", "integer", minimum=0, maximum=0),
            _field("status", "string", enum_values=("PASS",)),
            _field("report_hash", "string", pattern=r"[0-9a-f]{64}"),
        ),
    ),
    _artifact(
        "readiness",
        r"e19/readiness\.json",
        PublicArtifactRole.READINESS,
        (
            _field("schema_version", "integer", minimum=2, maximum=2),
            _field("mode", "string", enum_values=("FINAL_FRESH",)),
            _field(
                "primary_receipt_hashes",
                "array",
                min_items=1,
                unique_items=True,
                sorted_items=True,
                item_contract=_STRING_HASH_PAIR,
            ),
            _field(
                "criteria",
                "array",
                min_items=1,
                unique_items=True,
                item_contract=_field(
                    "criterion", "object", object_fields=_READINESS_CRITERION_FIELDS
                ),
            ),
            _field(
                "decision",
                "string",
                enum_values=(
                    "FRESH_JAVA_PROVEN",
                    "FRESH_JAVA_SEMANTICS_PASS_EXPORT_BLOCKED",
                ),
            ),
            _field("mandatory_count", "integer", minimum=1),
            _field("pass_count", "integer", minimum=0),
            _field(
                "failed_criteria",
                "array",
                unique_items=True,
                sorted_items=True,
                item_contract=_STRING_ITEM,
            ),
            _field("gate_hash", "string", pattern=r"[0-9a-f]{64}"),
        ),
    ),
)


class PublicFinalArtifactContractRegistry:
    def __init__(self) -> None:
        self._contracts = _PUBLIC_CONTRACTS
        patterns = [item.path_pattern for item in self._contracts]
        if len(patterns) != len(set(patterns)):
            raise ValueError("duplicate public artifact contract pattern")
        self.registry_hash = content_hash(self._contracts)

    @property
    def contracts(self) -> tuple[PublicArtifactTypeContract, ...]:
        return self._contracts

    def match(self, relative_path: str) -> PublicArtifactTypeContract:
        path = canonical_public_path(relative_path)
        matches = tuple(
            item for item in self._contracts if re.fullmatch(item.path_pattern, path)
        )
        if len(matches) != 1:
            raise ValueError("public artifact path has no unique typed contract")
        return matches[0]

    def validate(
        self,
        relative_path: str,
        raw: bytes,
        *,
        expected_sha256: str | None = None,
    ) -> PublicArtifactValidation:
        contract = self.match(relative_path)
        if contract.media_type != "application/json":
            if expected_sha256 is None or bytes_hash(raw) != expected_sha256:
                raise ValueError("binary artifact exact hash mismatch")
            if contract.expected_magic_hex is None or not raw.startswith(
                bytes.fromhex(contract.expected_magic_hex)
            ):
                raise ValueError("binary artifact magic mismatch")
            if contract.minimum_bytes is not None and len(raw) < contract.minimum_bytes:
                raise ValueError("binary artifact is below its size bound")
            if contract.maximum_bytes is not None and len(raw) > contract.maximum_bytes:
                raise ValueError("binary artifact exceeds its size bound")
            body = {
                "relative_path": relative_path,
                "artifact_type": contract.artifact_type,
                "role": contract.role,
                "byte_size": len(raw),
                "sha256": bytes_hash(raw),
                "status": "PASS",
            }
            return PublicArtifactValidation(**body, validation_hash=content_hash(body))
        if any(marker in raw for marker in _SOURCE_MARKERS):
            raise ValueError(
                "public artifact contains forbidden raw source/archive bytes"
            )
        text = raw.decode("utf-8", errors="strict")
        if any(marker in text for marker in _SECRET_MARKERS):
            raise ValueError("public artifact contains credential material")
        if _SECRET_VALUE.search(text):
            raise ValueError("public artifact contains an environment secret")
        if _JAVA_EXCERPT.search(text):
            raise ValueError("public artifact contains a Java source excerpt")
        if _contains_absolute_path(text):
            raise ValueError("public artifact contains a local absolute path")
        value = _strict_json(raw)
        _reject_embedded_source_payload(value)
        _validate_object(value, contract.fields, contract.artifact_type)
        _validate_cross_field_invariants(value, contract.artifact_type)
        body = {
            "relative_path": relative_path,
            "artifact_type": contract.artifact_type,
            "role": contract.role,
            "byte_size": len(raw),
            "sha256": bytes_hash(raw),
            "status": "PASS",
        }
        return PublicArtifactValidation(**body, validation_hash=content_hash(body))

    def validate_tree(
        self, artifacts: tuple[tuple[str, bytes], ...]
    ) -> tuple[PublicArtifactValidation, ...]:
        paths = tuple(canonical_public_path(path) for path, _raw in artifacts)
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate public artifact path")
        nfc = [unicodedata.normalize("NFC", path) for path in paths]
        if len(nfc) != len(set(nfc)):
            raise ValueError("Unicode NFC public artifact path collision")
        folded = [path.casefold() for path in paths]
        if len(folded) != len(set(folded)):
            raise ValueError("casefold public artifact path collision")
        return tuple(self.validate(path, raw) for path, raw in artifacts)


PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY = PublicFinalArtifactContractRegistry()


class LocalVaultRole(StrEnum):
    SOURCE_JAR = "SOURCE_JAR"
    POM = "POM"
    SCM_ARCHIVE = "SCM_ARCHIVE"
    JAVA_SOURCE = "JAVA_SOURCE"
    LEGAL_DOCUMENT = "LEGAL_DOCUMENT"
    QUALIFICATION_WORK = "QUALIFICATION_WORK"


@dataclass(frozen=True)
class LocalVaultManifestRow:
    candidate_id: str
    relative_canonical_path: str
    role: LocalVaultRole
    byte_size: int
    sha256: str
    parent_artifact_identity: str
    source_use_receipt_hash: str
    row_hash: str


@dataclass(frozen=True)
class LocalVaultManifest:
    schema_version: int
    f19_sha: str
    acquisition_run_id: str
    rows: tuple[LocalVaultManifestRow, ...]
    file_count: int
    tree_hash: str
    permission_report_hash: str
    write_protection_report_hash: str
    seal_timestamp: str
    manifest_hash: str


class LocalSourceVaultContractRegistry:
    def validate_root(self, root: Path, *, git_worktrees: tuple[Path, ...]) -> Path:
        resolved = root.resolve(strict=True)
        for worktree in git_worktrees:
            known = worktree.resolve(strict=True)
            if resolved == known or known in resolved.parents:
                raise ValueError("local source vault may not be inside a Git worktree")
        if resolved.is_symlink() or _is_reparse_point(resolved):
            raise ValueError("local source vault root may not be a link/reparse point")
        return resolved

    def build_manifest(
        self,
        root: Path,
        *,
        bindings: dict[str, tuple[str, LocalVaultRole, str, str]],
        git_worktrees: tuple[Path, ...],
        f19_sha: str,
        acquisition_run_id: str,
        seal_timestamp: str,
    ) -> LocalVaultManifest:
        resolved = self.validate_root(root, git_worktrees=git_worktrees)
        if not _GIT_SHA.fullmatch(f19_sha):
            raise ValueError("local vault F19 SHA is invalid")
        rows = []
        observed = set()
        for path in sorted(item for item in resolved.rglob("*") if item.is_file()):
            if path.is_symlink() or _is_reparse_point(path):
                raise ValueError("local vault contains a link/reparse point")
            relative = path.relative_to(resolved).as_posix()
            canonical_public_path(relative)
            if relative not in bindings:
                raise ValueError("local vault contains an unsealed extra file")
            candidate_id, role, parent, receipt_hash = bindings[relative]
            raw = path.read_bytes()
            body = {
                "candidate_id": candidate_id,
                "relative_canonical_path": relative,
                "role": LocalVaultRole(role),
                "byte_size": len(raw),
                "sha256": bytes_hash(raw),
                "parent_artifact_identity": parent,
                "source_use_receipt_hash": receipt_hash,
            }
            rows.append(LocalVaultManifestRow(**body, row_hash=content_hash(body)))
            observed.add(relative)
        if observed != set(bindings):
            raise ValueError("local vault manifest binding/file denominator mismatch")
        ordered = tuple(rows)
        tree_hash = content_hash(
            tuple((item.relative_canonical_path, item.sha256) for item in ordered)
        )
        permission = content_hash(
            tuple(
                (
                    item.relative_canonical_path,
                    stat.S_IMODE(
                        (resolved / item.relative_canonical_path).stat().st_mode
                    ),
                )
                for item in ordered
            )
        )
        write_protection = content_hash(
            tuple(
                (
                    item.relative_canonical_path,
                    not bool(
                        (resolved / item.relative_canonical_path).stat().st_mode
                        & stat.S_IWUSR
                    ),
                )
                for item in ordered
            )
        )
        if any(
            (resolved / item.relative_canonical_path).stat().st_mode & stat.S_IWUSR
            for item in ordered
        ):
            raise ValueError("local vault file is not write-protected")
        body = {
            "schema_version": 1,
            "f19_sha": f19_sha,
            "acquisition_run_id": acquisition_run_id,
            "rows": ordered,
            "file_count": len(ordered),
            "tree_hash": tree_hash,
            "permission_report_hash": permission,
            "write_protection_report_hash": write_protection,
            "seal_timestamp": seal_timestamp,
        }
        return LocalVaultManifest(**body, manifest_hash=content_hash(body))

    def verify_manifest(
        self,
        root: Path,
        manifest: LocalVaultManifest,
        *,
        git_worktrees: tuple[Path, ...],
    ) -> None:
        resolved = self.validate_root(root, git_worktrees=git_worktrees)
        body = asdict(manifest)
        claimed = body.pop("manifest_hash")
        if content_hash(body) != claimed:
            raise ValueError("local vault manifest hash mismatch")
        actual = tuple(
            (path.relative_to(resolved).as_posix(), bytes_hash(path.read_bytes()))
            for path in sorted(item for item in resolved.rglob("*") if item.is_file())
        )
        expected = tuple(
            (item.relative_canonical_path, item.sha256) for item in manifest.rows
        )
        if actual != expected or content_hash(actual) != manifest.tree_hash:
            raise ValueError("local vault file/tree hash mismatch")
        if manifest.file_count != len(manifest.rows):
            raise ValueError("local vault file denominator mismatch")
        for row in manifest.rows:
            row_body = asdict(row)
            claimed_row_hash = row_body.pop("row_hash")
            if content_hash(row_body) != claimed_row_hash:
                raise ValueError("local vault row hash mismatch")
        permission = content_hash(
            tuple(
                (
                    item.relative_canonical_path,
                    stat.S_IMODE(
                        (resolved / item.relative_canonical_path).stat().st_mode
                    ),
                )
                for item in manifest.rows
            )
        )
        write_protection_rows = tuple(
            (
                item.relative_canonical_path,
                not bool(
                    (resolved / item.relative_canonical_path).stat().st_mode
                    & stat.S_IWUSR
                ),
            )
            for item in manifest.rows
        )
        if (
            permission != manifest.permission_report_hash
            or content_hash(write_protection_rows)
            != manifest.write_protection_report_hash
            or not all(value for _path, value in write_protection_rows)
        ):
            raise ValueError("local vault permission/write-protection mismatch")


LOCAL_SOURCE_VAULT_CONTRACT_REGISTRY = LocalSourceVaultContractRegistry()


def canonical_public_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("artifact path must be non-empty POSIX text")
    if value != unicodedata.normalize("NFC", value) or _DRIVE.match(value):
        raise ValueError("artifact path is not NFC relative text")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError("artifact path is noncanonical or escapes its root")
    return value


def canonical_public_json(value: dict) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _strict_json(raw: bytes):
    text = raw.decode("utf-8", errors="strict")
    if "\r" in text or not text.endswith("\n") or text.endswith("\n\n"):
        raise ValueError("JSON artifact must use exact UTF-8/LF framing")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    def invalid_constant(value):
        raise ValueError(f"non-finite JSON value: {value}")

    value = json.loads(text, object_pairs_hook=unique, parse_constant=invalid_constant)
    if canonical_public_json(value) != raw:
        raise ValueError("JSON artifact is not canonical")
    return value


def _validate_object(value, fields: tuple[RecursiveFieldContract, ...], label: str):
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    expected = {item.name: item for item in fields}
    required = {item.name for item in fields if item.required}
    if set(value) - set(expected):
        raise ValueError(f"{label} contains an unknown nested field")
    if required - set(value):
        raise ValueError(f"{label} is missing a nested field")
    for name, item in value.items():
        _validate_field(item, expected[name], f"{label}.{name}")


def _validate_field(value, contract: RecursiveFieldContract, label: str):
    if value is None:
        if contract.allow_null:
            return
        raise TypeError(f"{label} has the wrong nested type")
    checks = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
    }
    if contract.value_type not in checks or not checks[contract.value_type](value):
        raise TypeError(f"{label} has the wrong nested type")
    if isinstance(value, str):
        if not value or value != unicodedata.normalize("NFC", value):
            raise ValueError(f"{label} is empty or non-NFC")
        if contract.enum_values and value not in contract.enum_values:
            raise ValueError(f"{label} has an invalid enum value")
        if contract.pattern and re.fullmatch(contract.pattern, value) is None:
            raise ValueError(f"{label} does not match its pattern")
    if isinstance(value, int) and not isinstance(value, bool):
        if contract.minimum is not None and value < contract.minimum:
            raise ValueError(f"{label} is below its minimum")
        if contract.maximum is not None and value > contract.maximum:
            raise ValueError(f"{label} is above its maximum")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{label} is not finite")
    if isinstance(value, list):
        if contract.min_items is not None and len(value) < contract.min_items:
            raise ValueError(f"{label} has an empty/short denominator")
        if contract.max_items is not None and len(value) > contract.max_items:
            raise ValueError(f"{label} exceeds its maximum cardinality")
        rendered = [canonical_json(item) for item in value]
        if contract.unique_items and len(rendered) != len(set(rendered)):
            raise ValueError(f"{label} contains duplicate items")
        if contract.sorted_items and rendered != sorted(rendered):
            raise ValueError(f"{label} is not canonically sorted")
        if contract.item_contract:
            for index, item in enumerate(value):
                _validate_field(item, contract.item_contract, f"{label}[{index}]")
        if contract.tuple_fields:
            if len(value) != len(contract.tuple_fields):
                raise ValueError(f"{label} has the wrong tuple cardinality")
            for index, (item, member_contract) in enumerate(
                zip(value, contract.tuple_fields, strict=True)
            ):
                _validate_field(item, member_contract, f"{label}[{index}]")
    if isinstance(value, dict):
        _validate_object(value, contract.object_fields, label)


def _contains_absolute_path(text: str) -> bool:
    return bool(
        re.search(r"(?:^|[\"'])[A-Za-z]:[\\/]", text)
        or re.search(r"(?:^|[\"'])/(?:home|Users|tmp|var/tmp)/", text)
    )


def _validate_cross_field_invariants(value: dict, artifact_type: str) -> None:
    hash_field = {
        "freeze-manifest": "freeze_manifest_hash",
        "acquisition-receipts": "report_hash",
        "qualification-decisions": "report_hash",
        "selector-receipt": "receipt_hash",
        "production-output": "summary_hash",
        "candidate-pack": "report_hash",
        "vault-hash-manifest": "manifest_hash",
        "h19-seal": "seal_hash",
        "evaluation": "report_hash",
        "readiness": "gate_hash",
    }[artifact_type]
    body = dict(value)
    claimed = body.pop(hash_field)
    if content_hash(body) != claimed:
        raise ValueError(f"{artifact_type} content hash invariant failed")
    if artifact_type == "freeze-manifest":
        names = [item[0] for item in value["frozen_artifacts"]]
        if len(names) != len(set(names)):
            raise ValueError("freeze manifest contains duplicate artifact names")
    elif artifact_type == "acquisition-receipts":
        rows = value["receipts"]
        if value["candidate_count"] != len(rows):
            raise ValueError("acquisition candidate denominator mismatch")
        if [item["family_id"] for item in rows] != sorted(
            item["family_id"] for item in rows
        ):
            raise ValueError("acquisition receipts are not family sorted")
    elif artifact_type == "qualification-decisions":
        rows = value["decisions"]
        if value["candidate_count"] != len(rows):
            raise ValueError("qualification candidate denominator mismatch")
        if [item["family_id"] for item in rows] != sorted(
            item["family_id"] for item in rows
        ):
            raise ValueError("qualification decisions are not family sorted")
        for row in rows:
            _verify_nested_hash(row, "decision_hash", "qualification decision")
            authority = row["authority"]
            _verify_nested_hash(authority, "receipt_hash", "authority receipt")
            if authority["receipt_hash"] != row["authority_receipt_hash"]:
                raise ValueError("qualification authority receipt binding mismatch")
        eligible = [
            row
            for row in rows
            if row["knowledge_acquisition_eligibility_decision"]
            == "ELIGIBLE_FOR_ANALYSIS"
        ]
        expected = {
            "analysis_eligible_root_count": len(eligible),
            "analysis_eligible_java_entry_count": sum(
                row["candidate_eligible_source_set_count"] for row in eligible
            ),
            "raw_source_publication_root_count": sum(
                row["raw_source_publication_decision"] == "ALLOWED" for row in rows
            ),
            "source_excerpt_publication_root_count": sum(
                row["source_excerpt_publication_decision"] == "ALLOWED" for row in rows
            ),
            "derived_pack_publication_root_count": sum(
                row["derived_pack_publication_decision"] == "ALLOWED"
                and row["knowledge_acquisition_eligibility_decision"]
                == "ELIGIBLE_FOR_ANALYSIS"
                for row in rows
            ),
            "metrics_publication_root_count": sum(
                row["metrics_publication_decision"] == "ALLOWED"
                and row["knowledge_acquisition_eligibility_decision"]
                == "ELIGIBLE_FOR_ANALYSIS"
                for row in rows
            ),
        }
        if any(value[name] != observed for name, observed in expected.items()):
            raise ValueError("qualification cross-field denominator mismatch")
    elif artifact_type == "selector-receipt":
        distribution = value["root_distribution"]
        if (
            len(distribution) != value["selected_root_count"]
            or sum(item[1] for item in distribution) != value["selected_file_count"]
            or max(item[1] for item in distribution) / value["selected_file_count"]
            > 0.35
        ):
            raise ValueError("selector distribution invariant failed")
    elif artifact_type == "vault-hash-manifest":
        rows = value["rows"]
        if value["file_count"] != len(rows) or value["row_hashes"] != [
            row["row_hash"] for row in rows
        ]:
            raise ValueError("vault manifest denominator/hash-list mismatch")
        if [row["relative_path"] for row in rows] != sorted(
            row["relative_path"] for row in rows
        ):
            raise ValueError("vault manifest rows are not path sorted")
        for row in rows:
            row_body = {
                "candidate_id": row["candidate_id"],
                "relative_canonical_path": row["relative_path"],
                "role": row["role"],
                "byte_size": row["byte_size"],
                "sha256": row["sha256"],
                "parent_artifact_identity": row["parent_artifact_hash"],
                "source_use_receipt_hash": row["source_use_receipt_hash"],
            }
            if content_hash(row_body) != row["row_hash"]:
                raise ValueError("vault manifest row hash mismatch")
    elif artifact_type == "h19-seal":
        if (
            not value["production_completed_before_evaluator"]
            or value["windows_production_hash"] != value["karina_production_hash"]
        ):
            raise ValueError("H19 production ordering/equality invariant failed")
    elif artifact_type == "production-output":
        if value["torch_imported"]:
            raise ValueError("production imported torch")
    elif artifact_type == "evaluation":
        if (
            not value["production_sealed_before_evaluator"]
            or not value["candidate_pack_compiled"]
        ):
            raise ValueError("evaluation ordering/pack invariant failed")
    elif artifact_type == "readiness":
        criteria = value["criteria"]
        if (
            value["mandatory_count"] != len(criteria)
            or value["pass_count"] != sum(item["passed"] for item in criteria)
            or value["failed_criteria"]
            != [item["name"] for item in criteria if not item["passed"]]
        ):
            raise ValueError("readiness criterion denominator mismatch")
        for row in criteria:
            _verify_nested_hash(row, "criterion_hash", "readiness criterion")


def _verify_nested_hash(value: dict, hash_field: str, label: str) -> None:
    body = dict(value)
    claimed = body.pop(hash_field)
    if content_hash(body) != claimed:
        raise ValueError(f"{label} hash invariant failed")


def _reject_embedded_source_payload(value) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str):
            if _SECRET_VALUE.search(item):
                raise ValueError("public artifact contains an environment secret")
            if _JAVA_EXCERPT.search(item):
                raise ValueError("public artifact contains a Java source excerpt")
            encoded = item.encode("utf-8")
            if any(marker in encoded for marker in _SOURCE_MARKERS):
                raise ValueError("public artifact string contains source/archive bytes")
            compact = "".join(item.split())
            decoded_values = []
            if len(compact) >= 24 and len(compact) % 4 == 0:
                try:
                    decoded_values.append(base64.b64decode(compact, validate=True))
                except (binascii.Error, ValueError):
                    pass
            if len(compact) >= 32 and len(compact) % 2 == 0:
                try:
                    decoded_values.append(bytes.fromhex(compact))
                except ValueError:
                    pass
            if any(
                marker in decoded
                for decoded in decoded_values
                for marker in _SOURCE_MARKERS
            ):
                raise ValueError(
                    "public artifact contains encoded source/archive bytes"
                )


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.stat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
