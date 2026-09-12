"""Frozen-input production validation and actual authorization sealing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.java_jdk_provider import (
    verify_m336_jdk_provider_evidence,
)
from ai_brain.stage3.acquisition.m336e_identity import (
    source_entry_binding_manifest_from_dict,
)
from ai_brain.stage3.acquisition.m336f_compilation_closure import (
    java_compilation_closure_feasibility_proof_from_dict,
    java_compilation_closure_manifest_from_dict,
    verify_java_compilation_closure_feasibility_proof,
)
from ai_brain.stage3.acquisition.m336f_selection import (
    m336f_selected_source_manifest_from_dict,
    m336f_selector_receipt_from_dict,
    verify_m336f_selection,
)
from ai_brain.stage3.acquisition.m336h_contracts import strict_json_file
from ai_brain.stage3.acquisition.m336h_production import (
    M336HCompilerAwareProductionRequest,
    M336HCompilerAwareProductionResponse,
    M336HPythonWorker,
    production_response_from_dict,
    run_m336h_compiler_aware_production,
    validate_m336h_compiler_aware_production_request,
)


@dataclass(frozen=True)
class M336ICompilerAwareProductionRequest:
    production_request: M336HCompilerAwareProductionRequest
    frozen_route_manifest: Path
    frozen_implementation_identity: str
    frozen_publication_boundary_hash: str
    frozen_threshold_manifest: Path
    public_staging_root: Path
    git_worktrees: tuple[Path, ...]


@dataclass(frozen=True)
class M336IProductionSeal:
    schema_version: int
    contract_role: str
    route_manifest_hash: str
    implementation_identity: str
    platform_role: str
    production_request_hash: str
    production_response_hash: str
    selected_manifest_hash: str
    binding_manifest_hash: str
    compiler_identity_hash: str
    compiler_report_hash: str
    production_output_hash: str
    public_candidate_pack_hash: str
    public_candidate_pack_tree_hash: str
    public_replay_commitment_hash: str
    sealed_source_replay_receipt_hash: str
    proposal_count: int
    trusted_count: int
    withheld_count: int
    authorization_count: int
    trusted_authorized_identity_difference_count: int
    duplicate_authorization_count: int
    missing_authorization_count: int
    extra_authorization_count: int
    trusted_compiler_blocked_target_count: int
    post_trust_pack_failures: int
    reconstructed_pack_byte_difference_count: int
    production_network_access_count: int
    production_evaluator_read_count: int
    production_golden_read_count: int
    source_bearing_public_entry_count: int
    private_role_public_entry_count: int
    unknown_public_entry_count: int
    absolute_path_count: int
    reversible_source_payload_count: int
    public_pack_integrity_status: str
    sealed_replay_status: str
    status: str
    seal_hash: str


def run_m336i_compiler_aware_production(
    request: M336ICompilerAwareProductionRequest,
    *,
    python_worker: M336HPythonWorker | None = None,
) -> tuple[M336HCompilerAwareProductionResponse, M336IProductionSeal]:
    validate_m336i_production_request(request)
    if python_worker is None:
        response = run_m336h_compiler_aware_production(request.production_request)
    else:
        response = run_m336h_compiler_aware_production(
            request.production_request, python_worker=python_worker
        )
    seal = build_m336i_production_seal(
        production_root=request.production_request.public_production_destination,
        response=response,
    )
    return response, seal


def validate_m336i_production_request(
    request: M336ICompilerAwareProductionRequest,
) -> None:
    validate_m336i_production_authority(request)
    base = request.production_request
    bindings = source_entry_binding_manifest_from_dict(
        _object(base.source_entry_bindings)
    )
    selected = m336f_selected_source_manifest_from_dict(_object(base.selected_manifest))
    selector = m336f_selector_receipt_from_dict(_object(base.selector_receipt))
    closure = java_compilation_closure_manifest_from_dict(
        _object(base.closure_manifest)
    )
    proof = java_compilation_closure_feasibility_proof_from_dict(
        _object(base.closure_feasibility_proof)
    )
    verify_java_compilation_closure_feasibility_proof(proof)
    verify_m336f_selection(selected, selector, proof)
    if (
        selected.binding_manifest_hash != bindings.manifest_hash
        or selected.closure_manifest_hash != closure.manifest_hash
        or selected.feasibility_proof_hash != proof.proof_hash
    ):
        raise ValueError("M336I production objects do not form one M336F selection")
    private_paths = (
        base.source_snapshot_private_handle,
        base.sealed_vault,
        base.private_replay_root,
    )
    public_paths = (
        base.public_production_destination,
        request.public_staging_root,
    )
    roots = tuple(Path(item).resolve(strict=True) for item in request.git_worktrees)
    all_paths = tuple(
        Path(item).resolve(strict=False) for item in (*private_paths, *public_paths)
    )
    if any(any(_overlap(path, root) for root in roots) for path in all_paths):
        raise ValueError("M336I production path overlaps a Git worktree")
    if any(_overlap(left, right) for left in private_paths for right in public_paths):
        raise ValueError("M336I private and public production destinations overlap")


def validate_m336i_production_authority(
    request: M336ICompilerAwareProductionRequest,
) -> None:
    if not isinstance(request, M336ICompilerAwareProductionRequest):
        raise TypeError("M336I production request must be typed")
    base = request.production_request
    validate_m336h_compiler_aware_production_request(base)
    route = _object(request.frozen_route_manifest)
    threshold = _object(request.frozen_threshold_manifest)
    expected = {
        "route_manifest_hash": route.get("manifest_hash"),
        "implementation_identity": request.frozen_implementation_identity,
        "publication_boundary_contract_hash": request.frozen_publication_boundary_hash,
        "threshold_manifest_hash": threshold.get("threshold_manifest_hash"),
    }
    if any(getattr(base, name) != value for name, value in expected.items()):
        raise ValueError("M336I production request differs from frozen authority")
    _verify_hash(route, "manifest_hash")
    _verify_hash(threshold, "threshold_manifest_hash")
    java_name = (
        "java.exe"
        if base.javac_private_handle.name.casefold().endswith(".exe")
        else "java"
    )
    _private_jdk, public_jdk = verify_m336_jdk_provider_evidence(
        platform=base.platform_role.casefold(),
        java=base.javac_private_handle.with_name(java_name),
        javac=base.javac_private_handle,
    )
    if public_jdk.receipt_hash != base.public_jdk_identity_receipt_hash:
        raise ValueError("M336I production JDK identity differs from frozen authority")


def build_m336i_production_seal(
    *,
    production_root: Path,
    response: M336HCompilerAwareProductionResponse,
) -> M336IProductionSeal:
    production_response_from_dict(asdict(response))
    counts = _object(production_root / "production_counts.json")
    output = _object(production_root / "production_output.json")
    authorization = _object(production_root / "production_authorization_manifest.json")
    integrity = _object(production_root / "public_pack_integrity_receipt.json")
    replay = _object(production_root / "sealed_source_replay_receipt.json")
    process = _object(production_root / "production_process_audit.json")
    summary = _object(production_root / "production_summary.json")
    authorization_body = dict(authorization)
    claimed = authorization_body.pop("manifest_hash", None)
    rows = tuple(authorization.get("authorizations", ()))
    ids = tuple(item["trusted_proposal_id"] for item in rows)
    trusted_ids = tuple(
        sorted(
            item["proposal_id"]
            for item in output["candidate_rows"]
            if item["production_trust_state"] == "trusted"
        )
    )
    authorized = set(ids)
    trusted = set(trusted_ids)
    duplicate = len(ids) - len(authorized)
    missing = len(trusted - authorized)
    extra = len(authorized - trusted)
    differences = len(trusted.symmetric_difference(authorized))
    if (
        content_hash(authorization_body) != claimed
        or authorization.get("authorization_count") != len(rows)
        or tuple(sorted(ids)) != ids
        or any(
            set(item)
            != {
                "trusted_proposal_id",
                "trusted_proposal_hash",
                "authorization_hash",
            }
            for item in rows
        )
    ):
        raise ValueError("M336I production authorization manifest is invalid")
    passed = (
        counts["proposal_count"] == counts["trusted_count"] + counts["withheld_count"]
        and len(rows) == counts["trusted_count"]
        and duplicate == missing == extra == differences == 0
        and counts["trusted_compiler_blocked_target_count"] == 0
        and counts["post_trust_pack_failures"] == 0
        and integrity["status"] == "PASS"
        and replay["status"] == "PASS"
        and replay["reconstructed_pack_byte_difference_count"] == 0
        and process["socket_attempts"] == 0
        and summary["production_golden_read_count"] == 0
        and integrity["source_bearing_entry_count"] == 0
        and integrity["private_role_entry_count"] == 0
        and integrity["unknown_entry_count"] == 0
        and integrity["absolute_path_count"] == 0
        and integrity["reversible_source_payload_count"] == 0
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336I_PRODUCTION_SEAL",
        "route_manifest_hash": response.route_manifest_hash,
        "implementation_identity": response.implementation_identity,
        "platform_role": response.platform_role,
        "production_request_hash": response.request_hash,
        "production_response_hash": response.response_hash,
        "selected_manifest_hash": response.selected_manifest_hash,
        "binding_manifest_hash": response.binding_manifest_hash,
        "compiler_identity_hash": response.compiler_identity_hash,
        "compiler_report_hash": response.compiler_report_hash,
        "production_output_hash": response.production_output_hash,
        "public_candidate_pack_hash": response.candidate_pack_hash,
        "public_candidate_pack_tree_hash": response.candidate_pack_tree_hash,
        "public_replay_commitment_hash": response.public_replay_commitment_hash,
        "sealed_source_replay_receipt_hash": response.sealed_source_replay_receipt_hash,
        "proposal_count": counts["proposal_count"],
        "trusted_count": counts["trusted_count"],
        "withheld_count": counts["withheld_count"],
        "authorization_count": len(rows),
        "trusted_authorized_identity_difference_count": differences,
        "duplicate_authorization_count": duplicate,
        "missing_authorization_count": missing,
        "extra_authorization_count": extra,
        "trusted_compiler_blocked_target_count": counts[
            "trusted_compiler_blocked_target_count"
        ],
        "post_trust_pack_failures": counts["post_trust_pack_failures"],
        "reconstructed_pack_byte_difference_count": replay[
            "reconstructed_pack_byte_difference_count"
        ],
        "production_network_access_count": process["socket_attempts"],
        "production_evaluator_read_count": 0,
        "production_golden_read_count": summary["production_golden_read_count"],
        "source_bearing_public_entry_count": integrity["source_bearing_entry_count"],
        "private_role_public_entry_count": integrity["private_role_entry_count"],
        "unknown_public_entry_count": integrity["unknown_entry_count"],
        "absolute_path_count": integrity["absolute_path_count"],
        "reversible_source_payload_count": integrity["reversible_source_payload_count"],
        "public_pack_integrity_status": integrity["status"],
        "sealed_replay_status": replay["status"],
        "status": "PASS" if passed else "FAIL",
    }
    seal = M336IProductionSeal(**body, seal_hash=content_hash(body))
    if seal.status != "PASS":
        raise ValueError("M336I production seal failed")
    return seal


def _object(path: Path) -> dict:
    value = strict_json_file(path)
    if not isinstance(value, dict):
        raise TypeError("M336I production input must be an object")
    return value


def _verify_hash(value: dict, field: str) -> None:
    body = dict(value)
    claimed = body.pop(field, None)
    if content_hash(body) != claimed:
        raise ValueError(f"M336I production {field} does not match content")


def _overlap(left: Path, right: Path) -> bool:
    left = Path(left).resolve(strict=False)
    right = Path(right).resolve(strict=False)
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)
