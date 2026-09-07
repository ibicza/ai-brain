"""Typed, count-neutral contracts for the M-33.6h native Java route."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash

M336H_CONTRACT_VERSION = "m336h.native-java-route-contracts.v1"


def _schema(name: str, fields: tuple[str, ...]) -> dict[str, object]:
    return {
        "contract_version": M336H_CONTRACT_VERSION,
        "name": name,
        "fields": fields,
        "additional_properties": False,
    }


SCHEMAS: dict[str, dict[str, object]] = {
    "empty": _schema("Empty", ()),
    "metadata_pool": _schema("FrozenMetadataPool", ("pool_hash", "candidate_count")),
    "acquisition_input": _schema(
        "AcquisitionInput", ("provider_id", "pool_hash", "policy_hash")
    ),
    "acquisition_receipt": _schema(
        "AcquisitionReceipt",
        ("provider_id", "reservation_count", "invocation_count", "status"),
    ),
    "authority_receipt": _schema(
        "AuthorityReceipt", ("authority_hash", "verification_status")
    ),
    "binding_manifest": _schema(
        "SourceEntryBindingManifest", ("manifest_hash", "binding_count")
    ),
    "selectability_census": _schema(
        "SelectableSourceCensus", ("census_hash", "file_count")
    ),
    "closure_manifest": _schema(
        "JavaCompilationClosureManifest", ("manifest_hash", "source_file_count")
    ),
    "closure_proof": _schema(
        "JavaCompilationClosureFeasibilityProof",
        ("proof_hash", "closure_manifest_hash", "witness_source_units"),
    ),
    "selector_ledger": _schema(
        "M336FSelectorLedger", ("reservation_count", "invocation_count")
    ),
    "selected_manifest": _schema(
        "M336FSelectedSourceManifest",
        (
            "manifest_hash",
            "closure_manifest_hash",
            "feasibility_proof_hash",
            "binding_manifest_hash",
            "files",
        ),
    ),
    "selector_receipt": _schema(
        "M336FSelectorReceipt",
        ("receipt_hash", "selector_version", "selected_manifest_hash"),
    ),
    "materialization_receipt": _schema(
        "M336HMaterializedSourceSnapshotReceipt",
        ("selected_manifest_hash", "file_count", "snapshot_tree_hash", "status"),
    ),
    "production_request": _schema(
        "M336HCompilerAwareProductionRequest",
        (
            "route_manifest_hash",
            "implementation_identity",
            "platform_role",
            "source_snapshot_private_handle",
            "javac_private_handle",
            "public_jdk_identity_receipt_hash",
            "source_entry_bindings",
            "selected_manifest",
            "selector_receipt",
            "closure_manifest",
            "closure_feasibility_proof",
            "sealed_vault",
            "private_replay_root",
            "public_production_destination",
            "publication_boundary_contract_hash",
            "threshold_manifest_hash",
        ),
    ),
    "production_response": _schema(
        "M336HCompilerAwareProductionResponse",
        (
            "request_hash",
            "compiler_aware_mode",
            "selected_manifest_hash",
            "binding_manifest_hash",
            "production_output_hash",
            "candidate_pack_hash",
            "status",
        ),
    ),
    "pack_receipt": _schema(
        "JavaPublicCandidatePackReceipt",
        ("candidate_pack_content_hash", "candidate_pack_tree_hash", "status"),
    ),
    "replay_receipt": _schema(
        "JavaSealedSourceReplayReceipt",
        (
            "public_replay_commitment_hash",
            "reconstructed_pack_byte_difference_count",
            "status",
        ),
    ),
    "production_seal": _schema(
        "M336HCountNeutralProductionSeal",
        (
            "platform_role",
            "proposal_count",
            "trusted_count",
            "withheld_count",
            "structural_invariants_satisfied",
            "status",
        ),
    ),
    "evaluation_request": _schema(
        "M336HIndependentJavaEvaluationRequest",
        (
            "route_manifest",
            "threshold_manifest",
            "windows_production_seal",
            "karina_production_seal",
            "public_candidate_pack",
            "public_replay_commitment",
            "sealed_source_replay_receipts",
            "independent_reference_material",
            "evaluator_reservation_ledger",
        ),
    ),
    "evaluation_result": _schema(
        "M336HIndependentJavaEvaluationResult",
        (
            "request_hash",
            "platform_neutral_difference_count",
            "structural_invariants_satisfied",
            "status",
        ),
    ),
    "staging_receipt": _schema(
        "PublicStagingValidationReceipt",
        ("staging_manifest_hash", "post_scan_modified_file_count", "status"),
    ),
    "leak_receipt": _schema("SourceLeakReceipt", ("fresh_source_leak_count", "status")),
    "readiness": _schema(
        "M336HFinalJavaRouteReadiness",
        (
            "route_manifest_hash",
            "resolved_component_count",
            "unresolved_component_count",
            "incompatible_route_edge_count",
            "incompatible_schema_edge_count",
            "status",
        ),
    ),
}

SCHEMA_HASHES = {name: content_hash(value) for name, value in SCHEMAS.items()}


def strict_json_loads(raw: str | bytes) -> object:
    """Decode JSON while rejecting duplicate object keys."""

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("M336H JSON contains a duplicate key")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=unique)


def strict_json_file(path: Path) -> object:
    raw = path.resolve(strict=True).read_bytes()
    if b"\r" in raw or not raw.endswith(b"\n"):
        raise ValueError("M336H JSON must use canonical LF framing")
    value = strict_json_loads(raw)
    if (canonical_json(value) + "\n").encode("utf-8") != raw:
        raise ValueError("M336H JSON bytes are not canonical")
    return value


def write_canonical_json(path: Path, value: object) -> bytes:
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    raw = (canonical_json(value) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def require_exact_fields(value: object, fields: set[str], *, label: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} fields differ from the frozen schema")
    return value
