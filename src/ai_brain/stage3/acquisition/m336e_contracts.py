"""Strict public contract v2 and real-producer compatibility gate."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition import m336d_contracts as _v1_contracts
from ai_brain.stage3.acquisition.m336d_contracts import (
    PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
    PublicArtifactRole,
    PublicArtifactTypeContract,
    PublicArtifactValidation,
    PublicFinalArtifactContractRegistry,
    RecursiveFieldContract,
    canonical_public_json,
)

M336E_PUBLIC_CONTRACT_SCHEMA_VERSION = 2
M336E_PUBLIC_CONTRACT_VERSION = "m336e.public-artifact-contract.v2"


def _field(name: str, value_type: str, **kwargs) -> RecursiveFieldContract:
    return RecursiveFieldContract(name, value_type, **kwargs)


_STRING_ITEM = _field("item", "string")
_HASH = _field("hash", "string", pattern=r"[0-9a-f]{64}")
_ROOT_COUNT_PAIR = _field(
    "root_count",
    "array",
    min_items=2,
    max_items=2,
    tuple_fields=(_STRING_ITEM, _field("count", "integer", minimum=0, maximum=63)),
)
_VARIANT = _field(
    "variant",
    "string",
    enum_values=("SUCCESS", "BLOCKED", "REVIEW_REQUIRED"),
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
        "analysis_eligibility_decision",
        "string",
        enum_values=("ELIGIBLE_FOR_ANALYSIS", "INELIGIBLE"),
    ),
    _field(
        "source_retention_decision",
        "string",
        enum_values=("ALLOWED_SEALED_VAULT_ONLY", "REVIEW_REQUIRED"),
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
        enum_values=("ALLOWED", "NOT_APPLICABLE"),
    ),
    _field(
        "scm_correspondence_decision",
        "string",
        enum_values=("COMPLETE", "PARTIAL_OR_INCOMPLETE"),
    ),
    _field(
        "scoped_license_decision",
        "string",
        enum_values=("RESOLVED", "PARTIALLY_RESOLVED", "REVIEW_REQUIRED"),
    ),
    _field("eligible_source_entry_count", "integer", minimum=0),
    _field("legal_document_count", "integer", minimum=0),
    _field("unknown_legal_document_role_count", "integer", minimum=0),
    _field("decision_hash", "string", pattern=r"[0-9a-f]{64}"),
)


def _contract(name, pattern, role, fields) -> PublicArtifactTypeContract:
    body = {
        "artifact_type": name,
        "path_pattern": pattern,
        "role": role,
        "media_type": "application/json",
        "schema_version": M336E_PUBLIC_CONTRACT_SCHEMA_VERSION,
        "fields": fields,
        "expected_magic_hex": None,
        "minimum_bytes": None,
        "maximum_bytes": None,
    }
    return PublicArtifactTypeContract(**body, contract_hash=content_hash(body))


M336E_ACQUISITION_RECEIPTS_CONTRACT = _contract(
    "acquisition-receipts",
    r"h20/acquisition_receipts\.json",
    PublicArtifactRole.ACQUISITION_RECEIPTS,
    (
        _field("schema_version", "integer", minimum=2, maximum=2),
        _field("f20_sha", "string", pattern=r"[0-9a-f]{40}"),
        _field("acquisition_run_id", "string"),
        _field("global_acquisition_count", "integer", minimum=1, maximum=1),
        _field("candidate_count", "integer", minimum=1),
        _field("host_audit_hash", "string", pattern=r"[0-9a-f]{64}"),
        _field(
            "variant",
            "string",
            enum_values=("SUCCESS", "BLOCKED", "REVIEW_REQUIRED"),
        ),
        _field(
            "receipts",
            "array",
            min_items=1,
            max_items=96,
            unique_items=True,
            item_contract=_field(
                "receipt", "object", object_fields=_ACQUISITION_RECEIPT_FIELDS
            ),
        ),
        _field("report_hash", "string", pattern=r"[0-9a-f]{64}"),
    ),
)

M336E_QUALIFICATION_SUMMARY_CONTRACT = _contract(
    "m336e-qualification-summary",
    r"h20/qualification_summary\.json",
    PublicArtifactRole.QUALIFICATION,
    (
        _field("schema_version", "integer", minimum=2, maximum=2),
        _field("f20_sha", "string", pattern=r"[0-9a-f]{40}"),
        _VARIANT,
        _field("candidate_count", "integer", minimum=1, maximum=96),
        _field("analysis_eligible_root_count", "integer", minimum=0, maximum=96),
        _field("analysis_eligible_file_count", "integer", minimum=0),
        _field("legal_document_count", "integer", minimum=0),
        _field("unresolved_legal_document_count", "integer", minimum=0),
        _field("freshness_overlap_count", "integer", minimum=0, maximum=0),
        _field("raw_publication_root_count", "integer", minimum=0, maximum=0),
        _field("excerpt_publication_root_count", "integer", minimum=0, maximum=0),
        _field("derived_pack_publication_root_count", "integer", minimum=0),
        _field("metrics_publication_root_count", "integer", minimum=0),
        _field(
            "candidate_decisions",
            "array",
            min_items=1,
            max_items=96,
            unique_items=True,
            item_contract=_field(
                "candidate_decision",
                "object",
                object_fields=_QUALIFICATION_DECISION_FIELDS,
            ),
        ),
        _field("qualification_manifest_hash", "string", pattern=r"[0-9a-f]{64}"),
        _field("report_hash", "string", pattern=r"[0-9a-f]{64}"),
    ),
)

M336E_VAULT_SUMMARY_CONTRACT = _contract(
    "m336e-portable-vault-summary",
    r"h20/portable_vault_summary\.json",
    PublicArtifactRole.VAULT_HASH_MANIFEST,
    (
        _field("schema_version", "integer", minimum=2, maximum=2),
        _VARIANT,
        _field("file_count", "integer", minimum=1),
        _field("portable_tree_hash", "string", pattern=r"[0-9a-f]{64}"),
        _field("portable_manifest_hash", "string", pattern=r"[0-9a-f]{64}"),
        _field("physical_difference_count", "integer", minimum=0, maximum=0),
        _field("canonical_manifest_difference_count", "integer", minimum=0, maximum=0),
        _field("portable_tree_hash_difference_count", "integer", minimum=0, maximum=0),
        _field("report_hash", "string", pattern=r"[0-9a-f]{64}"),
    ),
)

M336E_SELECTABILITY_SUMMARY_CONTRACT = _contract(
    "m336e-selectability-summary",
    r"h20/selectability_summary\.json",
    PublicArtifactRole.SELECTOR,
    (
        _field("schema_version", "integer", minimum=2, maximum=2),
        _VARIANT,
        _field("target_file_count", "integer", minimum=180, maximum=180),
        _field("maximum_files_per_root", "integer", minimum=63, maximum=63),
        _field("analysis_eligible_file_count", "integer", minimum=0),
        _field("parser_valid_file_count", "integer", minimum=0),
        _field("callable_file_count", "integer", minimum=0),
        _field("production_supported_file_count", "integer", minimum=0),
        _field("selectable_file_count", "integer", minimum=0),
        _field("selectable_root_count", "integer", minimum=0),
        _field("balanced_capacity", "integer", minimum=0),
        _field("census_hash", "string", pattern=r"[0-9a-f]{64}"),
        _field("feasibility_proof_hash", "string", pattern=r"[0-9a-f]{64}"),
        _field("report_hash", "string", pattern=r"[0-9a-f]{64}"),
    ),
)

M336E_SELECTOR_RECEIPT_CONTRACT = _contract(
    "m336e-selector-receipt",
    r"h20/selector_receipt\.json",
    PublicArtifactRole.SELECTOR,
    (
        _field("schema_version", "integer", minimum=2, maximum=2),
        _VARIANT,
        _field("selector_version", "string"),
        _field("selector_invocation_count", "integer", minimum=0, maximum=1),
        _field("selector_rerun_count", "integer", minimum=0, maximum=0),
        _field("selected_file_count", "integer", minimum=0, maximum=180),
        _field("selected_root_count", "integer", minimum=0),
        _field("maximum_one_root_count", "integer", minimum=0, maximum=63),
        _field("evaluator_read_count", "integer", minimum=0, maximum=0),
        _field("golden_read_count", "integer", minimum=0, maximum=0),
        _field("trust_metric_read_count", "integer", minimum=0, maximum=0),
        _field("selected_manifest_hash", "string", pattern=r"[0-9a-f]{64}"),
        _field(
            "root_distribution",
            "array",
            unique_items=True,
            item_contract=_ROOT_COUNT_PAIR,
        ),
        _field("receipt_hash", "string", pattern=r"[0-9a-f]{64}"),
    ),
)

M336E_REGISTRY_APPEND_CONTRACT = _contract(
    "m336e-disclosure-registry-append",
    r"h20/disclosure_registry_append_receipt\.json",
    PublicArtifactRole.ACQUISITION_RECEIPTS,
    (
        _field("schema_version", "integer", minimum=2, maximum=2),
        _VARIANT,
        _field("previous_registry_manifest_hash", "string", pattern=r"[0-9a-f]{64}"),
        _field("previous_entry_count", "integer", minimum=30),
        _field(
            "appended_entry_hashes",
            "array",
            min_items=1,
            max_items=96,
            unique_items=True,
            sorted_items=True,
            item_contract=_HASH,
        ),
        _field("appended_entry_count", "integer", minimum=1, maximum=96),
        _field("resulting_entry_count", "integer", minimum=31),
        _field("resulting_manifest_hash", "string", pattern=r"[0-9a-f]{64}"),
        _field("acquisition_run_id", "string"),
        _field("f20_sha", "string", pattern=r"[0-9a-f]{40}"),
        _field("receipt_hash", "string", pattern=r"[0-9a-f]{64}"),
    ),
)

M336E_PROTOCOL_LEDGER_CONTRACT = _contract(
    "m336e-protocol-ledger-receipt",
    r"h20/protocol_ledger_receipt\.json",
    PublicArtifactRole.SEAL,
    (
        _field("schema_version", "integer", minimum=2, maximum=2),
        _VARIANT,
        _field("protocol_version", "string"),
        _field("ledger_bytes_sha256", "string", pattern=r"[0-9a-f]{64}"),
        _field("final_event_hash", "string", pattern=r"[0-9a-f]{64}"),
        _field("global_acquisition_count", "integer", minimum=0, maximum=1),
        _field("selectability_census_count", "integer", minimum=0, maximum=1),
        _field("selector_invocation_count", "integer", minimum=0, maximum=1),
        _field("selector_rerun_count", "integer", minimum=0, maximum=0),
        _field("production_seal_count", "integer", minimum=0, maximum=2),
        _field("evaluator_start_count", "integer", minimum=0, maximum=1),
        _field("receipt_hash", "string", pattern=r"[0-9a-f]{64}"),
    ),
)

M336E_PRODUCTION_SUMMARY_CONTRACT = _contract(
    "m336e-production-summary",
    r"h20/production_summary\.json",
    PublicArtifactRole.PRODUCTION,
    (
        _field("schema_version", "integer", minimum=2, maximum=2),
        _VARIANT,
        _field("windows_production_hash", "string", pattern=r"[0-9a-f]{64}"),
        _field("karina_production_hash", "string", pattern=r"[0-9a-f]{64}"),
        _field("platform_difference_count", "integer", minimum=0, maximum=0),
        _field("proposal_count", "integer", minimum=0),
        _field("trusted_count", "integer", minimum=0),
        _field("post_trust_pack_failure_count", "integer", minimum=0, maximum=0),
        _field("evaluator_read_count", "integer", minimum=0, maximum=0),
        _field("golden_read_count", "integer", minimum=0, maximum=0),
        _field("network_access_count", "integer", minimum=0, maximum=0),
        _field("report_hash", "string", pattern=r"[0-9a-f]{64}"),
    ),
)

M336E_PACK_RECEIPT_CONTRACT = _contract(
    "m336e-candidate-pack-receipt",
    r"h20/candidate_pack_receipt\.json",
    PublicArtifactRole.CANDIDATE_PACK,
    (
        _field("schema_version", "integer", minimum=2, maximum=2),
        _VARIANT,
        _field("candidate_pack_hash", "string", pattern=r"[0-9a-f]{64}"),
        _field("candidate_tree_hash", "string", pattern=r"[0-9a-f]{64}"),
        _field("compiled", "boolean"),
        _field(
            "replay_status",
            "string",
            enum_values=("PASS", "BLOCKED", "REVIEW_REQUIRED"),
        ),
        _field("receipt_hash", "string", pattern=r"[0-9a-f]{64}"),
    ),
)

M336E_H20_SEAL_CONTRACT = _contract(
    "m336e-h20-seal",
    r"h20/h20_seal\.json",
    PublicArtifactRole.SEAL,
    (
        _field("schema_version", "integer", minimum=2, maximum=2),
        _VARIANT,
        _field("f20_sha", "string", pattern=r"[0-9a-f]{40}"),
        _field("public_payload_file_count", "integer", minimum=1),
        _field("public_tree_hash", "string", pattern=r"[0-9a-f]{64}"),
        _field("producer_contract_failure_count", "integer", minimum=0, maximum=0),
        _field("source_leak_count", "integer", minimum=0, maximum=0),
        _field("seal_hash", "string", pattern=r"[0-9a-f]{64}"),
    ),
)

M336E_EVALUATION_CONTRACT = _contract(
    "m336e-independent-evaluation",
    r"e20/evaluation\.json",
    PublicArtifactRole.EVALUATION,
    (
        _field("schema_version", "integer", minimum=2, maximum=2),
        _VARIANT,
        _field(
            "production_reference_spdx_agreement", "string", pattern=r"[01]\.[0-9]{6}"
        ),
        _field(
            "false_automatic_license_identity_count", "integer", minimum=0, maximum=0
        ),
        _field("location_precision", "string", pattern=r"[01]\.[0-9]{6}"),
        _field("location_recall", "string", pattern=r"[01]\.[0-9]{6}"),
        _field("semantic_precision", "string", pattern=r"[01]\.[0-9]{6}"),
        _field("semantic_recall", "string", pattern=r"[01]\.[0-9]{6}"),
        _field("trust_precision", "string", pattern=r"[01]\.[0-9]{6}"),
        _field("trust_coverage", "string", pattern=r"[01]\.[0-9]{6}"),
        _field("field_evidence_exactness", "string", pattern=r"[01]\.[0-9]{6}"),
        _field("resolution_agreement", "string", pattern=r"[01]\.[0-9]{6}"),
        _field("wrong_trusted_count", "integer", minimum=0, maximum=0),
        _field(
            "runtime_status",
            "string",
            enum_values=("PASS", "BLOCKED", "REVIEW_REQUIRED"),
        ),
        _field("runtime_network_access_count", "integer", minimum=0, maximum=0),
        _field("report_hash", "string", pattern=r"[0-9a-f]{64}"),
    ),
)

M336E_READINESS_CONTRACT = _contract(
    "m336e-readiness",
    r"e20/readiness\.json",
    PublicArtifactRole.READINESS,
    (
        _field("schema_version", "integer", minimum=2, maximum=2),
        _VARIANT,
        _field("mandatory_criterion_count", "integer", minimum=1),
        _field("passed_criterion_count", "integer", minimum=0),
        _field("failed_criterion_count", "integer", minimum=0),
        _field(
            "outcome", "string", enum_values=("OUTCOME_A", "OUTCOME_B", "OUTCOME_C")
        ),
        _field("gate_hash", "string", pattern=r"[0-9a-f]{64}"),
    ),
)

M336E_PUBLIC_CONTRACTS = (
    M336E_ACQUISITION_RECEIPTS_CONTRACT,
    M336E_QUALIFICATION_SUMMARY_CONTRACT,
    M336E_VAULT_SUMMARY_CONTRACT,
    M336E_SELECTABILITY_SUMMARY_CONTRACT,
    M336E_SELECTOR_RECEIPT_CONTRACT,
    M336E_REGISTRY_APPEND_CONTRACT,
    M336E_PROTOCOL_LEDGER_CONTRACT,
    M336E_PRODUCTION_SUMMARY_CONTRACT,
    M336E_PACK_RECEIPT_CONTRACT,
    M336E_H20_SEAL_CONTRACT,
    M336E_EVALUATION_CONTRACT,
    M336E_READINESS_CONTRACT,
)


class M336EPublicFinalArtifactContractRegistryV2(PublicFinalArtifactContractRegistry):
    """A v2 registry; the frozen v1 registry is retained only as an adapter."""

    def __init__(self, contracts=M336E_PUBLIC_CONTRACTS) -> None:
        self._contracts = tuple(contracts)
        patterns = tuple(item.path_pattern for item in self._contracts)
        if len(patterns) != len(set(patterns)):
            raise ValueError("duplicate M-33.6e public artifact contract pattern")
        if any(
            item.schema_version != M336E_PUBLIC_CONTRACT_SCHEMA_VERSION
            for item in self._contracts
        ):
            raise ValueError("M-33.6e contract registry contains a non-v2 contract")
        self.registry_hash = content_hash(
            (M336E_PUBLIC_CONTRACT_VERSION, self._contracts)
        )

    def validate(
        self,
        relative_path: str,
        raw: bytes,
        *,
        expected_sha256: str | None = None,
    ) -> PublicArtifactValidation:
        """Validate v2 without routing through immutable v1 type invariants."""

        del expected_sha256
        contract = self.match(relative_path)
        if contract.media_type != "application/json":
            raise ValueError("M-33.6e public contract currently requires JSON")
        if any(marker in raw for marker in _v1_contracts._SOURCE_MARKERS):
            raise ValueError(
                "public artifact contains forbidden raw source/archive bytes"
            )
        text = raw.decode("utf-8", errors="strict")
        if any(marker in text for marker in _v1_contracts._SECRET_MARKERS):
            raise ValueError("public artifact contains credential material")
        if _v1_contracts._SECRET_VALUE.search(text):
            raise ValueError("public artifact contains an environment secret")
        if _v1_contracts._JAVA_EXCERPT.search(text):
            raise ValueError("public artifact contains a Java source excerpt")
        if _v1_contracts._contains_absolute_path(text):
            raise ValueError("public artifact contains a local absolute path")
        value = _v1_contracts._strict_json(raw)
        _v1_contracts._reject_embedded_source_payload(value)
        _v1_contracts._validate_object(value, contract.fields, contract.artifact_type)
        _validate_m336e_cross_field_invariants(value, contract.artifact_type)
        body = {
            "relative_path": relative_path,
            "artifact_type": contract.artifact_type,
            "role": contract.role,
            "byte_size": len(raw),
            "sha256": bytes_hash(raw),
            "status": "PASS",
        }
        return PublicArtifactValidation(**body, validation_hash=content_hash(body))


M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY = (
    M336EPublicFinalArtifactContractRegistryV2()
)
M336D_PUBLIC_CONTRACT_V1_LEGACY_ADAPTER = PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY


def _validate_m336e_cross_field_invariants(value: dict, artifact_type: str) -> None:
    hash_field = {
        "acquisition-receipts": "report_hash",
        "m336e-qualification-summary": "report_hash",
        "m336e-portable-vault-summary": "report_hash",
        "m336e-selectability-summary": "report_hash",
        "m336e-selector-receipt": "receipt_hash",
        "m336e-disclosure-registry-append": "receipt_hash",
        "m336e-protocol-ledger-receipt": "receipt_hash",
        "m336e-production-summary": "report_hash",
        "m336e-candidate-pack-receipt": "receipt_hash",
        "m336e-h20-seal": "seal_hash",
        "m336e-independent-evaluation": "report_hash",
        "m336e-readiness": "gate_hash",
    }[artifact_type]
    body = dict(value)
    claimed = body.pop(hash_field)
    if content_hash(body) != claimed:
        raise ValueError(f"{artifact_type} content hash invariant failed")
    if artifact_type == "acquisition-receipts":
        rows = value["receipts"]
        if value["candidate_count"] != len(rows) or [
            item["family_id"] for item in rows
        ] != sorted(item["family_id"] for item in rows):
            raise ValueError("acquisition receipt denominator/order mismatch")
    elif artifact_type == "m336e-qualification-summary":
        decisions = value["candidate_decisions"]
        if any(
            value[field] > value["candidate_count"]
            for field in (
                "analysis_eligible_root_count",
                "derived_pack_publication_root_count",
                "metrics_publication_root_count",
            )
        ):
            raise ValueError("qualification root denominator mismatch")
        if len(decisions) != value["candidate_count"] or [
            item["family_id"] for item in decisions
        ] != sorted(item["family_id"] for item in decisions):
            raise ValueError("qualification decision denominator/order mismatch")
        for item in decisions:
            decision_body = dict(item)
            claimed = decision_body.pop("decision_hash")
            if content_hash(decision_body) != claimed:
                raise ValueError("qualification candidate decision hash mismatch")
    elif artifact_type == "m336e-selector-receipt":
        distribution = value["root_distribution"]
        if (
            value["selected_root_count"] != len(distribution)
            or value["selected_file_count"] != sum(row[1] for row in distribution)
            or value["maximum_one_root_count"]
            != (max((row[1] for row in distribution), default=0))
        ):
            raise ValueError("selector receipt distribution mismatch")
    elif artifact_type == "m336e-disclosure-registry-append":
        if (
            value["appended_entry_count"] != len(value["appended_entry_hashes"])
            or value["resulting_entry_count"]
            != value["previous_entry_count"] + value["appended_entry_count"]
        ):
            raise ValueError("registry append denominator mismatch")
    elif artifact_type == "m336e-readiness" and (
        value["passed_criterion_count"] + value["failed_criterion_count"]
        != value["mandatory_criterion_count"]
    ):
        raise ValueError("readiness criterion denominator mismatch")


def produce_m336e_acquisition_receipts(
    legacy_value: dict,
    *,
    f20_sha: str,
    variant: str,
) -> dict:
    """Upgrade the real acquisition producer shape without widening v1."""

    if variant not in {"SUCCESS", "BLOCKED", "REVIEW_REQUIRED"}:
        raise ValueError("unknown acquisition producer variant")
    body = {
        "schema_version": M336E_PUBLIC_CONTRACT_SCHEMA_VERSION,
        "f20_sha": f20_sha,
        "acquisition_run_id": legacy_value["acquisition_run_id"],
        "global_acquisition_count": legacy_value["global_acquisition_count"],
        "candidate_count": legacy_value["candidate_count"],
        "host_audit_hash": legacy_value["host_audit_hash"],
        "variant": variant,
        "receipts": tuple(legacy_value["receipts"]),
    }
    return {**body, "report_hash": content_hash(body)}


def produce_m336e_qualification_summary(
    variant: str,
    *,
    f20_sha: str = "1" * 40,
    qualification: dict | None = None,
    census: dict | None = None,
    overlap: dict | None = None,
) -> dict:
    if qualification is None:
        eligible = variant == "SUCCESS"
        decisions = []
        for index in range(48):
            decision_body = {
                "family_id": f"candidate-{index:02d}",
                "organization_id": f"organization-{index:02d}",
                "coordinate": f"org.example:candidate-{index:02d}:1.0",
                "source_authenticity_decision": (
                    "AUTHENTIC" if eligible else "REVIEW_REQUIRED"
                ),
                "analysis_eligibility_decision": (
                    "ELIGIBLE_FOR_ANALYSIS" if eligible else "INELIGIBLE"
                ),
                "source_retention_decision": "ALLOWED_SEALED_VAULT_ONLY",
                "raw_source_publication_decision": "DENIED",
                "source_excerpt_publication_decision": "DENIED",
                "derived_pack_publication_decision": (
                    "ALLOWED" if eligible and index < 8 else "NOT_APPLICABLE"
                ),
                "metrics_publication_decision": (
                    "ALLOWED" if eligible and index < 8 else "NOT_APPLICABLE"
                ),
                "scm_correspondence_decision": (
                    "COMPLETE" if eligible else "PARTIAL_OR_INCOMPLETE"
                ),
                "scoped_license_decision": (
                    "RESOLVED" if eligible else "REVIEW_REQUIRED"
                ),
                "eligible_source_entry_count": 45 if eligible and index < 8 else 0,
                "legal_document_count": 2,
                "unknown_legal_document_role_count": 0 if eligible else 1,
            }
            decisions.append(
                {**decision_body, "decision_hash": content_hash(decision_body)}
            )
        values = {
            "candidate_count": 48,
            "analysis_eligible_root_count": 8 if variant == "SUCCESS" else 0,
            "analysis_eligible_file_count": 360 if variant == "SUCCESS" else 0,
            "legal_document_count": 96,
            "unresolved_legal_document_count": 0 if eligible else 48,
            "freshness_overlap_count": 0,
            "raw_publication_root_count": 0,
            "excerpt_publication_root_count": 0,
            "derived_pack_publication_root_count": 8 if variant == "SUCCESS" else 0,
            "metrics_publication_root_count": 8 if variant == "SUCCESS" else 0,
            "candidate_decisions": tuple(decisions),
            "qualification_manifest_hash": "2" * 64,
        }
    else:
        if census is None:
            raise ValueError("real qualification producer requires a census")
        source_decisions = tuple(
            qualification.get("decisions", qualification.get("candidates", ()))
        )
        if not source_decisions:
            raise ValueError("real qualification producer has no candidate decisions")
        fresh_shape = "decisions" in qualification
        decisions = []
        for item in source_decisions:
            if fresh_shape:
                decision_body = {
                    "family_id": item["family_id"],
                    "organization_id": item["organization_id"],
                    "coordinate": item["coordinate"],
                    "source_authenticity_decision": item[
                        "source_authenticity_decision"
                    ],
                    "analysis_eligibility_decision": item[
                        "knowledge_acquisition_eligibility_decision"
                    ],
                    "source_retention_decision": item["source_retention_decision"],
                    "raw_source_publication_decision": item[
                        "raw_source_publication_decision"
                    ],
                    "source_excerpt_publication_decision": item[
                        "source_excerpt_publication_decision"
                    ],
                    "derived_pack_publication_decision": item[
                        "derived_pack_publication_decision"
                    ],
                    "metrics_publication_decision": item[
                        "metrics_publication_decision"
                    ],
                    "scm_correspondence_decision": item["scm_correspondence_decision"],
                    "scoped_license_decision": item["scoped_license_decision"],
                    "eligible_source_entry_count": item[
                        "candidate_eligible_source_set_count"
                    ],
                    "legal_document_count": item["legal_document_count"],
                    "unknown_legal_document_role_count": item[
                        "unknown_legal_document_role_count"
                    ],
                }
            else:
                candidate_eligible = bool(item["analysis_eligible"])
                decision_body = {
                    "family_id": item["family_id"],
                    "organization_id": item["family_id"],
                    "coordinate": f"disclosed:{item['family_id']}:historical",
                    "source_authenticity_decision": (
                        "AUTHENTIC"
                        if item["source_jar_sha256"] != "0" * 64
                        else "REVIEW_REQUIRED"
                    ),
                    "analysis_eligibility_decision": (
                        "ELIGIBLE_FOR_ANALYSIS" if candidate_eligible else "INELIGIBLE"
                    ),
                    "source_retention_decision": "ALLOWED_SEALED_VAULT_ONLY",
                    "raw_source_publication_decision": "DENIED",
                    "source_excerpt_publication_decision": "DENIED",
                    "derived_pack_publication_decision": (
                        "ALLOWED" if candidate_eligible else "NOT_APPLICABLE"
                    ),
                    "metrics_publication_decision": (
                        "ALLOWED" if candidate_eligible else "NOT_APPLICABLE"
                    ),
                    "scm_correspondence_decision": (
                        "COMPLETE"
                        if item["correspondence_complete_file_count"]
                        == item["java_file_count"]
                        else "PARTIAL_OR_INCOMPLETE"
                    ),
                    "scoped_license_decision": (
                        "RESOLVED" if candidate_eligible else "REVIEW_REQUIRED"
                    ),
                    "eligible_source_entry_count": (
                        item["correspondence_complete_file_count"]
                        if candidate_eligible
                        else 0
                    ),
                    "legal_document_count": item["legal_document_count"],
                    "unknown_legal_document_role_count": item[
                        "unknown_legal_document_role_count"
                    ],
                }
            decisions.append(
                {**decision_body, "decision_hash": content_hash(decision_body)}
            )
        decisions = tuple(sorted(decisions, key=lambda item: item["family_id"]))
        values = {
            "candidate_count": qualification["candidate_count"],
            "analysis_eligible_root_count": qualification.get(
                "analysis_eligible_root_count",
                sum(
                    item["analysis_eligibility_decision"] == "ELIGIBLE_FOR_ANALYSIS"
                    for item in decisions
                ),
            ),
            "analysis_eligible_file_count": census["analysis_eligible_file_count"],
            "legal_document_count": sum(
                item["legal_document_count"] for item in decisions
            ),
            "unresolved_legal_document_count": sum(
                item["unknown_legal_document_role_count"] for item in decisions
            ),
            "freshness_overlap_count": (
                0 if overlap is None else overlap["selected_root_overlap_count"]
            ),
            "raw_publication_root_count": 0,
            "excerpt_publication_root_count": 0,
            "derived_pack_publication_root_count": sum(
                item["derived_pack_publication_decision"] == "ALLOWED"
                for item in decisions
            ),
            "metrics_publication_root_count": sum(
                item["metrics_publication_decision"] == "ALLOWED" for item in decisions
            ),
            "candidate_decisions": decisions,
            "qualification_manifest_hash": qualification["report_hash"],
        }
    body = {
        "schema_version": 2,
        "f20_sha": f20_sha,
        "variant": variant,
        **values,
    }
    return {**body, "report_hash": content_hash(body)}


def produce_m336e_portable_vault_summary(
    variant: str,
    *,
    manifest: dict | None = None,
    comparison: dict | None = None,
) -> dict:
    values = (
        {
            "file_count": 500,
            "portable_tree_hash": "3" * 64,
            "portable_manifest_hash": "4" * 64,
            "physical_difference_count": 0,
            "canonical_manifest_difference_count": 0,
            "portable_tree_hash_difference_count": 0,
        }
        if manifest is None or comparison is None
        else {
            "file_count": manifest["file_count"],
            "portable_tree_hash": manifest["portable_tree_hash"],
            "portable_manifest_hash": manifest["manifest_hash"],
            "physical_difference_count": comparison["physical_difference_count"],
            "canonical_manifest_difference_count": comparison[
                "canonical_manifest_difference_count"
            ],
            "portable_tree_hash_difference_count": comparison[
                "portable_tree_hash_difference_count"
            ],
        }
    )
    body = {
        "schema_version": 2,
        "variant": variant,
        **values,
    }
    return {**body, "report_hash": content_hash(body)}


def produce_m336e_selectability_summary(
    variant: str, *, census: dict | None = None, proof: dict | None = None
) -> dict:
    success = variant == "SUCCESS"
    values = (
        {
            "analysis_eligible_file_count": 360 if success else 0,
            "parser_valid_file_count": 350 if success else 0,
            "callable_file_count": 320 if success else 0,
            "production_supported_file_count": 300 if success else 0,
            "selectable_file_count": 300 if success else 0,
            "selectable_root_count": 8 if success else 0,
            "balanced_capacity": 300 if success else 0,
            "census_hash": "5" * 64,
            "feasibility_proof_hash": "6" * 64,
        }
        if census is None or proof is None
        else {
            "analysis_eligible_file_count": census["analysis_eligible_file_count"],
            "parser_valid_file_count": census["parser_valid_file_count"],
            "callable_file_count": census["callable_file_count"],
            "production_supported_file_count": census[
                "production_supported_file_count"
            ],
            "selectable_file_count": census["selectable_file_count"],
            "selectable_root_count": census["selectable_root_count"],
            "balanced_capacity": proof["balanced_capacity"],
            "census_hash": census["census_hash"],
            "feasibility_proof_hash": proof["proof_hash"],
        }
    )
    body = {
        "schema_version": 2,
        "variant": variant,
        "target_file_count": 180,
        "maximum_files_per_root": 63,
        **values,
    }
    return {**body, "report_hash": content_hash(body)}


def produce_m336e_selector_receipt(
    variant: str, *, selector: dict | None = None
) -> dict:
    success = variant == "SUCCESS"
    if selector is None:
        distribution = (
            (("alpha", 45), ("beta", 45), ("delta", 45), ("gamma", 45))
            if success
            else ()
        )
        values = {
            "selector_version": "m336e.production-supported-selector.v1",
            "selector_invocation_count": 1 if success else 0,
            "selector_rerun_count": 0,
            "selected_file_count": 180 if success else 0,
            "selected_root_count": 4 if success else 0,
            "maximum_one_root_count": 45 if success else 0,
            "evaluator_read_count": 0,
            "golden_read_count": 0,
            "trust_metric_read_count": 0,
            "selected_manifest_hash": "7" * 64,
            "root_distribution": distribution,
        }
    else:
        values = {
            name: selector[name]
            for name in (
                "selector_version",
                "selector_invocation_count",
                "selector_rerun_count",
                "selected_file_count",
                "selected_root_count",
                "maximum_one_root_count",
                "evaluator_read_count",
                "golden_read_count",
                "trust_metric_read_count",
                "selected_manifest_hash",
                "root_distribution",
            )
        }
    body = {
        "schema_version": 2,
        "variant": variant,
        **values,
    }
    return {**body, "receipt_hash": content_hash(body)}


def produce_m336e_registry_append_receipt(
    variant: str, *, append_receipt: dict | None = None
) -> dict:
    if append_receipt is None:
        appended = tuple(sorted(("8" * 64, "9" * 64)))
        values = {
            "previous_registry_manifest_hash": "a" * 64,
            "previous_entry_count": 30,
            "appended_entry_hashes": appended,
            "appended_entry_count": len(appended),
            "resulting_entry_count": 30 + len(appended),
            "resulting_manifest_hash": "b" * 64,
            "acquisition_run_id": "m336e.contract-fixture.v1",
            "f20_sha": "1" * 40,
        }
    else:
        values = {
            name: append_receipt[name]
            for name in (
                "previous_registry_manifest_hash",
                "previous_entry_count",
                "appended_entry_hashes",
                "appended_entry_count",
                "resulting_entry_count",
                "resulting_manifest_hash",
                "acquisition_run_id",
                "f20_sha",
            )
        }
    body = {"schema_version": 2, "variant": variant, **values}
    return {**body, "receipt_hash": content_hash(body)}


def produce_m336e_protocol_ledger_receipt(
    variant: str, *, ledger_receipt: dict | None = None
) -> dict:
    success = variant == "SUCCESS"
    values = (
        {
            "protocol_version": "m336e.run-protocol.v1",
            "ledger_bytes_sha256": "c" * 64,
            "final_event_hash": "d" * 64,
            "global_acquisition_count": 1 if success else 0,
            "selectability_census_count": 1 if success else 0,
            "selector_invocation_count": 1 if success else 0,
            "selector_rerun_count": 0,
            "production_seal_count": 2 if success else 0,
            "evaluator_start_count": 1 if success else 0,
        }
        if ledger_receipt is None
        else {
            name: ledger_receipt[name]
            for name in (
                "protocol_version",
                "ledger_bytes_sha256",
                "final_event_hash",
                "global_acquisition_count",
                "selectability_census_count",
                "selector_invocation_count",
                "selector_rerun_count",
                "production_seal_count",
                "evaluator_start_count",
            )
        }
    )
    body = {"schema_version": 2, "variant": variant, **values}
    return {**body, "receipt_hash": content_hash(body)}


def produce_m336e_production_summary(
    variant: str,
    *,
    windows: dict | None = None,
    karina: dict | None = None,
    comparison: dict | None = None,
    production_counts: dict | None = None,
    process_audit: dict | None = None,
) -> dict:
    success = variant == "SUCCESS"
    if any(
        value is None
        for value in (windows, karina, comparison, production_counts, process_audit)
    ):
        values = {
            "windows_production_hash": "e" * 64,
            "karina_production_hash": "e" * 64,
            "platform_difference_count": 0,
            "proposal_count": 800 if success else 0,
            "trusted_count": 700 if success else 0,
            "post_trust_pack_failure_count": 0,
            "evaluator_read_count": 0,
            "golden_read_count": 0,
            "network_access_count": 0,
        }
    else:
        values = {
            "windows_production_hash": windows["production_output_hash"],
            "karina_production_hash": karina["production_output_hash"],
            "platform_difference_count": comparison[
                "platform_independent_difference_count"
            ],
            "proposal_count": production_counts["proposal_count"],
            "trusted_count": production_counts["trusted_count"],
            "post_trust_pack_failure_count": production_counts[
                "post_trust_pack_failures"
            ],
            "evaluator_read_count": windows["production_evaluator_dependency_count"],
            "golden_read_count": windows["production_golden_read_count"],
            "network_access_count": process_audit["socket_attempts"],
        }
    body = {
        "schema_version": 2,
        "variant": variant,
        **values,
    }
    return {**body, "report_hash": content_hash(body)}


def produce_m336e_candidate_pack_receipt(
    variant: str, *, production_summary: dict | None = None
) -> dict:
    values = (
        {
            "candidate_pack_hash": "f" * 64,
            "candidate_tree_hash": "0" * 64,
            "compiled": variant == "SUCCESS",
            "replay_status": "PASS" if variant == "SUCCESS" else variant,
        }
        if production_summary is None
        else {
            "candidate_pack_hash": production_summary["candidate_pack_hash"],
            "candidate_tree_hash": production_summary["candidate_tree_hash"],
            "compiled": production_summary["status"] == "PASS",
            "replay_status": production_summary["candidate_replay_status"],
        }
    )
    body = {
        "schema_version": 2,
        "variant": variant,
        **values,
    }
    return {**body, "receipt_hash": content_hash(body)}


def produce_m336e_h20_seal(
    variant: str,
    *,
    f20_sha: str = "1" * 40,
    public_payload_file_count: int = 12,
    public_tree_hash: str = "1" * 64,
    producer_contract_failure_count: int = 0,
    source_leak_count: int = 0,
) -> dict:
    body = {
        "schema_version": 2,
        "variant": variant,
        "f20_sha": f20_sha,
        "public_payload_file_count": public_payload_file_count,
        "public_tree_hash": public_tree_hash,
        "producer_contract_failure_count": producer_contract_failure_count,
        "source_leak_count": source_leak_count,
    }
    return {**body, "seal_hash": content_hash(body)}


def produce_m336e_independent_evaluation(
    variant: str, *, evaluation: dict | None = None
) -> dict:
    value = "1.000000" if variant == "SUCCESS" else "0.000000"
    values = (
        {
            "production_reference_spdx_agreement": value,
            "false_automatic_license_identity_count": 0,
            "location_precision": value,
            "location_recall": value,
            "semantic_precision": value,
            "semantic_recall": value,
            "trust_precision": value,
            "trust_coverage": value,
            "field_evidence_exactness": value,
            "resolution_agreement": value,
            "wrong_trusted_count": 0,
            "runtime_status": "PASS" if variant == "SUCCESS" else variant,
            "runtime_network_access_count": 0,
        }
        if evaluation is None
        else {
            "production_reference_spdx_agreement": evaluation[
                "production_reference_license_agreement"
            ],
            "false_automatic_license_identity_count": evaluation[
                "false_automatic_license_identity_count"
            ],
            "location_precision": evaluation["location_precision"],
            "location_recall": evaluation["location_recall"],
            "semantic_precision": evaluation["semantic_precision"],
            "semantic_recall": evaluation["semantic_recall"],
            "trust_precision": evaluation["trust_precision"],
            "trust_coverage": evaluation["trust_coverage"],
            "field_evidence_exactness": evaluation["field_evidence_exactness"],
            "resolution_agreement": evaluation["resolution_agreement"],
            "wrong_trusted_count": evaluation["wrong_trusted_count"],
            "runtime_status": evaluation["runtime_status"],
            "runtime_network_access_count": evaluation["runtime_network_access_count"],
        }
    )
    body = {
        "schema_version": 2,
        "variant": variant,
        **values,
    }
    return {**body, "report_hash": content_hash(body)}


def produce_m336e_readiness(
    variant: str, *, criteria: tuple[tuple[str, bool], ...] | None = None
) -> dict:
    outcome = {
        "SUCCESS": "OUTCOME_A",
        "BLOCKED": "OUTCOME_C",
        "REVIEW_REQUIRED": "OUTCOME_B",
    }[variant]
    if criteria is None:
        mandatory = 55
        passed = 55 if variant == "SUCCESS" else 0
    else:
        if not criteria or len({name for name, _passed in criteria}) != len(criteria):
            raise ValueError("readiness criteria are empty or duplicated")
        mandatory = len(criteria)
        passed = sum(value for _name, value in criteria)
        derived = "SUCCESS" if passed == mandatory else "BLOCKED"
        if variant != derived:
            raise ValueError("readiness variant differs from its criteria")
    body = {
        "schema_version": 2,
        "variant": variant,
        "mandatory_criterion_count": mandatory,
        "passed_criterion_count": passed,
        "failed_criterion_count": mandatory - passed,
        "outcome": outcome,
    }
    return {**body, "gate_hash": content_hash(body)}


@dataclass(frozen=True)
class PublicArtifactProducer:
    producer_id: str
    artifact_type: str
    relative_path: str
    schema_version: int
    success_variants: tuple[str, ...]
    blocked_variants: tuple[str, ...]
    review_required_variants: tuple[str, ...]
    produce: Callable[[str], dict]

    @property
    def declared_variants(self) -> tuple[str, ...]:
        return (
            *self.success_variants,
            *self.blocked_variants,
            *self.review_required_variants,
        )


def m336e_future_public_producers(legacy_acquisition_value: dict):
    """Declare every canonical H20/E20 JSON producer and all outcome variants."""

    variants = {
        "success_variants": ("SUCCESS",),
        "blocked_variants": ("BLOCKED",),
        "review_required_variants": ("REVIEW_REQUIRED",),
    }
    specifications = (
        (
            "m336e.acquisition-receipts.v2",
            "acquisition-receipts",
            "h20/acquisition_receipts.json",
            lambda variant: produce_m336e_acquisition_receipts(
                legacy_acquisition_value, f20_sha="1" * 40, variant=variant
            ),
        ),
        (
            "m336e.qualification-summary.v2",
            "m336e-qualification-summary",
            "h20/qualification_summary.json",
            produce_m336e_qualification_summary,
        ),
        (
            "m336e.portable-vault-summary.v2",
            "m336e-portable-vault-summary",
            "h20/portable_vault_summary.json",
            produce_m336e_portable_vault_summary,
        ),
        (
            "m336e.selectability-summary.v2",
            "m336e-selectability-summary",
            "h20/selectability_summary.json",
            produce_m336e_selectability_summary,
        ),
        (
            "m336e.selector-receipt.v2",
            "m336e-selector-receipt",
            "h20/selector_receipt.json",
            produce_m336e_selector_receipt,
        ),
        (
            "m336e.registry-append.v2",
            "m336e-disclosure-registry-append",
            "h20/disclosure_registry_append_receipt.json",
            produce_m336e_registry_append_receipt,
        ),
        (
            "m336e.protocol-ledger.v2",
            "m336e-protocol-ledger-receipt",
            "h20/protocol_ledger_receipt.json",
            produce_m336e_protocol_ledger_receipt,
        ),
        (
            "m336e.production-summary.v2",
            "m336e-production-summary",
            "h20/production_summary.json",
            produce_m336e_production_summary,
        ),
        (
            "m336e.candidate-pack-receipt.v2",
            "m336e-candidate-pack-receipt",
            "h20/candidate_pack_receipt.json",
            produce_m336e_candidate_pack_receipt,
        ),
        (
            "m336e.h20-seal.v2",
            "m336e-h20-seal",
            "h20/h20_seal.json",
            produce_m336e_h20_seal,
        ),
        (
            "m336e.independent-evaluation.v2",
            "m336e-independent-evaluation",
            "e20/evaluation.json",
            produce_m336e_independent_evaluation,
        ),
        (
            "m336e.readiness.v2",
            "m336e-readiness",
            "e20/readiness.json",
            produce_m336e_readiness,
        ),
    )
    return tuple(
        PublicArtifactProducer(
            producer_id=producer_id,
            artifact_type=artifact_type,
            relative_path=relative_path,
            schema_version=2,
            produce=produce,
            **variants,
        )
        for producer_id, artifact_type, relative_path, produce in specifications
    )


@dataclass(frozen=True)
class ProducedArtifactReceipt:
    schema_version: int
    producer_id: str
    producer_variant: str
    artifact_type: str
    relative_path: str
    produced_sha256: str
    byte_size: int
    matched_contract_hash: str
    canonical_roundtrip_equal: bool
    validation_hash: str
    receipt_hash: str


@dataclass(frozen=True)
class ProducerContractCompatibilityReport:
    schema_version: int
    contract_registry_hash: str
    public_producer_count: int
    covered_producer_count: int
    declared_producer_variant_count: int
    tested_producer_variant_count: int
    uncontracted_produced_artifact_count: int
    contract_type_without_producer_or_legacy_count: int
    ambiguous_path_contract_count: int
    receipts: tuple[ProducedArtifactReceipt, ...]
    status: str
    report_hash: str


class ProducerContractCompatibilityGate:
    def __init__(
        self,
        registry: M336EPublicFinalArtifactContractRegistryV2,
        producers,
        *,
        legacy_artifact_types=(),
    ) -> None:
        self.registry = registry
        self.producers = tuple(producers)
        self.legacy_artifact_types = frozenset(legacy_artifact_types)

    def run(self) -> ProducerContractCompatibilityReport:
        producer_ids = tuple(item.producer_id for item in self.producers)
        if len(set(producer_ids)) != len(producer_ids):
            raise ValueError("producer registry contains a duplicate producer ID")
        produced_types = {item.artifact_type for item in self.producers}
        contract_types = {item.artifact_type for item in self.registry.contracts}
        uncovered_contracts = (
            contract_types - produced_types - self.legacy_artifact_types
        )
        if uncovered_contracts:
            raise ValueError("contract type has no producer or read-only legacy role")
        receipts = []
        tested = 0
        for producer in self.producers:
            variants = producer.declared_variants
            if (
                producer.schema_version != M336E_PUBLIC_CONTRACT_SCHEMA_VERSION
                or not variants
                or len(set(variants)) != len(variants)
            ):
                raise ValueError("producer variant declaration is invalid")
            contract = self.registry.match(producer.relative_path)
            if contract.artifact_type != producer.artifact_type:
                raise ValueError(
                    "producer artifact type differs from its path contract"
                )
            for variant in variants:
                value = producer.produce(variant)
                if value.get("schema_version") != producer.schema_version:
                    raise ValueError("producer emitted a wrong schema version")
                raw = canonical_public_json(value)
                validation = self.registry.validate(producer.relative_path, raw)
                decoded = json.loads(raw.decode("utf-8"))
                roundtrip = canonical_public_json(decoded)
                if roundtrip != raw:
                    raise ValueError("producer artifact canonical round-trip differs")
                receipt_body = {
                    "schema_version": M336E_PUBLIC_CONTRACT_SCHEMA_VERSION,
                    "producer_id": producer.producer_id,
                    "producer_variant": variant,
                    "artifact_type": producer.artifact_type,
                    "relative_path": producer.relative_path,
                    "produced_sha256": bytes_hash(raw),
                    "byte_size": len(raw),
                    "matched_contract_hash": contract.contract_hash,
                    "canonical_roundtrip_equal": True,
                    "validation_hash": validation.validation_hash,
                }
                receipts.append(
                    ProducedArtifactReceipt(
                        **receipt_body, receipt_hash=content_hash(receipt_body)
                    )
                )
                tested += 1
        ordered = tuple(
            sorted(
                receipts,
                key=lambda item: (
                    item.producer_id.encode("utf-8"),
                    item.producer_variant.encode("utf-8"),
                ),
            )
        )
        declared = sum(len(item.declared_variants) for item in self.producers)
        body = {
            "schema_version": M336E_PUBLIC_CONTRACT_SCHEMA_VERSION,
            "contract_registry_hash": self.registry.registry_hash,
            "public_producer_count": len(self.producers),
            "covered_producer_count": len({item.producer_id for item in receipts}),
            "declared_producer_variant_count": declared,
            "tested_producer_variant_count": tested,
            "uncontracted_produced_artifact_count": 0,
            "contract_type_without_producer_or_legacy_count": 0,
            "ambiguous_path_contract_count": 0,
            "receipts": ordered,
            "status": "PASS",
        }
        return ProducerContractCompatibilityReport(
            **body, report_hash=content_hash(body)
        )
