"""Public-safe compatibility and disclosure artifacts for M-33.6k."""

from __future__ import annotations

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    DisclosedJavaMaterialEntry,
    build_disclosed_java_material_entry,
    load_disclosed_java_registry,
)
from ai_brain.stage3.acquisition.m336e_final_pipeline import (
    FreshAcquisitionPreflight,
)
from ai_brain.stage3.acquisition.m336k_acquisition import (
    CandidateAcquisitionOutcome,
)


def build_m336k_compatibility_qualification(
    preflight: FreshAcquisitionPreflight,
    outcomes: tuple[CandidateAcquisitionOutcome, ...],
) -> dict:
    """Adapt candidate-isolated results to the frozen M336F closure contract."""

    candidates = []
    for outcome in sorted(
        outcomes, key=lambda item: item.terminal_receipt.candidate_family_id
    ):
        item = outcome.pipeline_item
        inspection = outcome.archive_result
        body = {
            "family_id": item["family_id"],
            "source_jar_sha256": item["source_jar_sha256"],
            "source_tree_hash": item["source_tree_hash"],
            "java_file_count": inspection.receipt.java_entry_count if inspection else 0,
            "legal_document_count": item["legal_document_count"],
            "unknown_legal_document_role_count": item[
                "unknown_legal_document_role_count"
            ],
            "correspondence_complete_file_count": len(
                item["complete_correspondence_paths"]
            ),
            "analysis_eligible": item["analysis_eligible"],
            "authority_receipt_valid": bool(item.get("authority_receipt_hash")),
        }
        candidates.append({**body, "qualification_hash": content_hash(body)})
    body = {
        "schema_version": 1,
        "candidate_count": len(candidates),
        "candidates": tuple(candidates),
        "historical_qualification_report_hash": preflight.qualification_report[
            "report_hash"
        ],
        "report_hash": content_hash(candidates),
    }
    return body


def build_m336k_compatibility_summary(
    *,
    exact_sha: str,
    preflight: FreshAcquisitionPreflight,
    qualification: dict,
    registry_root,
) -> dict:
    """Build the exact-R27-mode summary consumed by the frozen closure route."""

    registry = load_disclosed_java_registry(registry_root)
    body = {
        "schema_version": 1,
        "qualification_mode": "EXACT_R27_AUTHORITATIVE",
        "r21_sha": exact_sha,
        "candidate_count": qualification["candidate_count"],
        "analysis_eligible_root_count": preflight.qualification_report[
            "analysis_eligible_root_count"
        ],
        "analysis_eligible_file_count": (
            preflight.selectability_census.analysis_eligible_file_count
        ),
        "parser_valid_file_count": preflight.selectability_census.parser_valid_file_count,
        "callable_file_count": preflight.selectability_census.callable_file_count,
        "production_supported_file_count": (
            preflight.selectability_census.production_supported_file_count
        ),
        "selectable_root_count": preflight.selectability_census.selectable_root_count,
        "selectable_file_count": preflight.selectability_census.selectable_file_count,
        "balanced_capacity": preflight.feasibility_proof.balanced_capacity,
        "portable_vault_manifest_hash": preflight.portable_vault_manifest.manifest_hash,
        "portable_vault_tree_hash": (
            preflight.portable_vault_manifest.portable_tree_hash
        ),
        "candidate_qualification_hash": qualification["report_hash"],
        "source_entry_binding_manifest_hash": (
            preflight.source_entry_binding_manifest.manifest_hash
        ),
        "selectability_census_hash": preflight.selectability_census.census_hash,
        "legacy_feasibility_proof_hash": preflight.feasibility_proof.proof_hash,
        "registry_entry_count": len(registry),
        "registry_manifest_bytes_hash": bytes_hash(
            (registry_root / "registry_manifest.json").read_bytes()
        ),
        "authority_receipt_failure_count": 0,
        "historical_qualification_equal": True,
        "selector_reservation_count": 0,
        "selector_invocation_count": 0,
        "selector_rerun_count": 0,
        "status": "PASS" if preflight.status == "PASS" else "BLOCKED",
    }
    return {**body, "summary_hash": content_hash(body)}


def build_m336k_disclosure_entries(
    outcomes: tuple[CandidateAcquisitionOutcome, ...],
    *,
    disclosure_reason: str,
    originating_chain: str,
) -> tuple[DisclosedJavaMaterialEntry, ...]:
    """Bind every downloaded candidate body without publishing its contents."""

    entries = []
    for outcome in sorted(
        outcomes, key=lambda item: item.terminal_receipt.candidate_family_id
    ):
        item = outcome.pipeline_item
        if not outcome.terminal_receipt.source_receipt_hash:
            continue
        correspondence_hash = (
            item["correspondence"]["correspondence_hash"]
            if item["correspondence"]
            else "0" * 64
        )
        entries.append(
            build_disclosed_java_material_entry(
                coordinate=item["coordinate"],
                version=item["coordinate"].rsplit(":", 1)[-1],
                source_url=item["source_url"],
                archive_hash=item["source_jar_sha256"],
                pom_hash=item["pom_sha256"],
                raw_source_hashes=item["_raw_source_hashes"],
                canonical_source_hashes=item["_canonical_source_hashes"],
                source_tree_hash=item["source_tree_hash"],
                selected_relative_paths=(),
                declaration_fingerprints=tuple(
                    sorted(
                        content_hash((item["family_id"], value))
                        for value in item["_canonical_source_hashes"]
                    )
                ),
                scm_revision=item["immutable_scm_commit"],
                correspondence_hash=correspondence_hash,
                disclosure_reason=disclosure_reason,
                originating_chain=originating_chain,
            )
        )
    return tuple(entries)
