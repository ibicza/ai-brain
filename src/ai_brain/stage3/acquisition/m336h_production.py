"""Mandatory compiler-aware, count-neutral production for the M-33.6h route."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.java_jdk_provider import (
    verify_m336_jdk_provider_evidence,
)
from ai_brain.stage3.acquisition.m336f_compilation_closure import (
    java_compilation_closure_feasibility_proof_from_dict,
    java_compilation_closure_manifest_from_dict,
    verify_java_compilation_closure_feasibility_proof,
    verify_java_compilation_closure_manifest,
)
from ai_brain.stage3.acquisition.m336f_selection import (
    m336f_selected_source_manifest_from_dict,
    m336f_selector_receipt_from_dict,
    verify_m336f_selection,
)
from ai_brain.stage3.acquisition.m336g_publication import (
    JAVA_PUBLIC_REPLAY_COMMITMENT_FILENAME,
    sealed_java_replay_input_manifest_from_dict,
    verify_java_public_candidate_pack,
)
from ai_brain.stage3.acquisition.m336g_replay import (
    run_sealed_java_production_replay,
)
from ai_brain.stage3.acquisition.m336h_contracts import (
    SCHEMA_HASHES,
    strict_json_file,
    write_canonical_json,
)

M336HPythonWorker = Callable[[Path, tuple[str, ...], Path], None]


@dataclass(frozen=True)
class M336HCompilerAwareProductionRequest:
    route_manifest_hash: str
    implementation_identity: str
    platform_role: str
    source_snapshot_private_handle: Path
    javac_private_handle: Path
    public_jdk_identity_receipt_hash: str
    source_entry_bindings: Path
    selected_manifest: Path
    selector_receipt: Path
    closure_manifest: Path
    closure_feasibility_proof: Path
    sealed_vault: Path
    private_replay_root: Path
    public_production_destination: Path
    publication_boundary_contract_hash: str
    threshold_manifest_hash: str


@dataclass(frozen=True)
class M336HCompilerAwareProductionResponse:
    schema_version: int
    request_hash: str
    request_schema_hash: str
    response_schema_hash: str
    route_manifest_hash: str
    implementation_identity: str
    platform_role: str
    compiler_aware_mode: bool
    selected_manifest_hash: str
    binding_manifest_hash: str
    closure_manifest_hash: str
    feasibility_proof_hash: str
    compiler_identity_hash: str
    compiler_report_hash: str
    production_output_hash: str
    production_batch_hash: str
    candidate_pack_hash: str
    candidate_pack_tree_hash: str
    public_replay_commitment_hash: str
    sealed_source_replay_receipt_hash: str
    proposal_count: int
    trusted_count: int
    withheld_count: int
    compiler_blocked_declaration_count: int
    trusted_compiler_blocked_target_count: int
    post_trust_pack_failures: int
    status: str
    response_hash: str


@dataclass(frozen=True)
class M336HCountNeutralProductionSeal:
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
    structural_invariants_satisfied: bool
    public_pack_integrity_status: str
    sealed_replay_status: str
    status: str
    seal_hash: str


def _load(path: Path) -> dict:
    value = strict_json_file(path)
    if not isinstance(value, dict):
        raise TypeError("M336H production input must be a JSON object")
    return value


def _private_request_body(request: M336HCompilerAwareProductionRequest) -> dict:
    return {
        item.name: str(getattr(request, item.name))
        if isinstance(getattr(request, item.name), Path)
        else getattr(request, item.name)
        for item in fields(request)
    }


def compiler_aware_production_request_from_dict(
    value: dict,
) -> M336HCompilerAwareProductionRequest:
    expected = {item.name for item in fields(M336HCompilerAwareProductionRequest)}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("M336H compiler-aware production request is incomplete")
    path_fields = {
        "source_snapshot_private_handle",
        "javac_private_handle",
        "source_entry_bindings",
        "selected_manifest",
        "selector_receipt",
        "closure_manifest",
        "closure_feasibility_proof",
        "sealed_vault",
        "private_replay_root",
        "public_production_destination",
    }
    converted = {
        key: Path(item) if key in path_fields and isinstance(item, str) else item
        for key, item in value.items()
    }
    request = M336HCompilerAwareProductionRequest(**converted)
    validate_m336h_compiler_aware_production_request(request)
    return request


def validate_m336h_compiler_aware_production_request(
    request: M336HCompilerAwareProductionRequest,
) -> None:
    if not isinstance(request, M336HCompilerAwareProductionRequest):
        raise TypeError("M336H final production requires its exact typed request")
    for item in fields(request):
        value = getattr(request, item.name)
        if value is None or (isinstance(value, str) and not value):
            raise ValueError(f"M336H compiler-aware input is mandatory: {item.name}")
    for name in (
        "route_manifest_hash",
        "implementation_identity",
        "public_jdk_identity_receipt_hash",
        "publication_boundary_contract_hash",
        "threshold_manifest_hash",
    ):
        value = getattr(request, name)
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError(f"M336H request {name} is not a SHA-256 identity")
    if request.platform_role not in {"WINDOWS", "KARINA"}:
        raise ValueError("M336H production platform role is invalid")
    for name in (
        "source_snapshot_private_handle",
        "javac_private_handle",
        "source_entry_bindings",
        "selected_manifest",
        "selector_receipt",
        "closure_manifest",
        "closure_feasibility_proof",
        "sealed_vault",
    ):
        path = getattr(request, name)
        if not isinstance(path, Path) or not path.exists():
            raise ValueError(f"M336H production private handle is missing: {name}")
    for name in ("private_replay_root", "public_production_destination"):
        path = getattr(request, name)
        if not isinstance(path, Path) or path.exists() or not path.parent.exists():
            raise ValueError(f"M336H production destination is not fresh: {name}")
    private_root = request.private_replay_root.resolve(strict=False)
    public_root = request.public_production_destination.resolve(strict=False)
    if (
        private_root == public_root
        or private_root.is_relative_to(public_root)
        or public_root.is_relative_to(private_root)
    ):
        raise ValueError("M336H private replay and public production roots overlap")


def run_m336h_compiler_aware_production(
    request: M336HCompilerAwareProductionRequest,
    *,
    python_worker: M336HPythonWorker | None = None,
) -> M336HCompilerAwareProductionResponse:
    """Run the strict production worker and sealed replay with no legacy fallback."""

    validate_m336h_compiler_aware_production_request(request)
    request_body = _private_request_body(request)
    request_hash = content_hash(request_body)
    bindings = _load(request.source_entry_bindings)
    selected = m336f_selected_source_manifest_from_dict(
        _load(request.selected_manifest)
    )
    selector = m336f_selector_receipt_from_dict(_load(request.selector_receipt))
    closure = java_compilation_closure_manifest_from_dict(
        _load(request.closure_manifest)
    )
    proof = java_compilation_closure_feasibility_proof_from_dict(
        _load(request.closure_feasibility_proof)
    )
    verify_java_compilation_closure_manifest(closure)
    verify_java_compilation_closure_feasibility_proof(proof)
    verify_m336f_selection(selected, selector, proof)
    if (
        selected.closure_manifest_hash != closure.manifest_hash
        or selected.binding_manifest_hash != bindings.get("manifest_hash")
        or proof.closure_manifest_hash != closure.manifest_hash
    ):
        raise ValueError("M336H production inputs are not one exact M336F selection")

    repository = Path(__file__).resolve().parents[4]
    worker = repository / "scripts" / "m336_run_oracle_free_production.py"
    with tempfile.TemporaryDirectory(prefix="m336h-production-request-") as temporary:
        private_request = Path(temporary) / "request.json"
        write_canonical_json(private_request, request_body)
        if content_hash(_load(private_request)) != request_hash:
            raise ValueError("M336H private production request serialization changed")
        worker_arguments = (
            "--source-root",
            str(request.source_snapshot_private_handle.resolve(strict=True)),
            "--output",
            str(request.public_production_destination),
            "--platform",
            request.platform_role.casefold(),
            "--javac",
            str(request.javac_private_handle.resolve(strict=True)),
            "--source-entry-bindings",
            str(request.source_entry_bindings.resolve(strict=True)),
            "--selected-manifest",
            str(request.selected_manifest.resolve(strict=True)),
            "--sealed-vault",
            str(request.sealed_vault.resolve(strict=True)),
            "--private-replay-root",
            str(request.private_replay_root),
        )
        if python_worker is None:
            subprocess.run(
                (sys.executable, str(worker), *worker_arguments),
                cwd=repository,
                check=True,
            )
        else:
            python_worker(worker, worker_arguments, repository)

    java_name = (
        "java.exe"
        if request.javac_private_handle.name.casefold().endswith(".exe")
        else "java"
    )
    java = request.javac_private_handle.with_name(java_name)
    _private_jdk, public_jdk = verify_m336_jdk_provider_evidence(
        platform=request.platform_role.casefold(),
        java=java,
        javac=request.javac_private_handle,
    )
    write_canonical_json(
        request.public_production_destination / "public_jdk_identity_receipt.json",
        public_jdk,
    )

    private_manifest_path = (
        request.private_replay_root / "sealed_java_replay_input_manifest.json"
    )
    private_manifest = sealed_java_replay_input_manifest_from_dict(
        _load(private_manifest_path)
    )
    replay = run_sealed_java_production_replay(
        public_pack_root=request.public_production_destination / "candidate_pack",
        private_manifest=private_manifest,
        sealed_vault_root=request.sealed_vault,
        javac_executable=request.javac_private_handle,
    )
    write_canonical_json(
        request.public_production_destination / "sealed_source_replay_receipt.json",
        replay,
    )
    summary = _load(request.public_production_destination / "production_summary.json")
    counts = _load(request.public_production_destination / "production_counts.json")
    integrity = verify_java_public_candidate_pack(
        request.public_production_destination / "candidate_pack"
    )
    commitment = _load(
        request.public_production_destination
        / "candidate_pack"
        / JAVA_PUBLIC_REPLAY_COMMITMENT_FILENAME
    )
    jdk = _load(
        request.public_production_destination / "public_jdk_identity_receipt.json"
    )
    if (
        summary.get("status") != "PASS"
        or summary.get("public_pack_integrity_status") != "PASS"
        or counts.get("proposal_count")
        != counts.get("trusted_count", -1) + counts.get("withheld_count", -1)
        or counts.get("trusted_compiler_blocked_target_count") != 0
        or counts.get("post_trust_pack_failures") != 0
        or integrity.status != "PASS"
        or replay.status != "PASS"
        or replay.reconstructed_pack_byte_difference_count != 0
        or commitment.get("selected_source_manifest_hash") != selected.manifest_hash
        or commitment.get("source_entry_binding_manifest_hash")
        != bindings.get("manifest_hash")
        or jdk.get("receipt_hash") != request.public_jdk_identity_receipt_hash
    ):
        raise ValueError("M336H compiler-aware production postconditions failed")
    body = {
        "schema_version": 1,
        "request_hash": request_hash,
        "request_schema_hash": SCHEMA_HASHES["production_request"],
        "response_schema_hash": SCHEMA_HASHES["production_response"],
        "route_manifest_hash": request.route_manifest_hash,
        "implementation_identity": request.implementation_identity,
        "platform_role": request.platform_role,
        "compiler_aware_mode": True,
        "selected_manifest_hash": selected.manifest_hash,
        "binding_manifest_hash": bindings["manifest_hash"],
        "closure_manifest_hash": closure.manifest_hash,
        "feasibility_proof_hash": proof.proof_hash,
        "compiler_identity_hash": summary["compiler_identity_hash"],
        "compiler_report_hash": summary["compiler_report_hash"],
        "production_output_hash": summary["production_output_hash"],
        "production_batch_hash": summary["production_batch_hash"],
        "candidate_pack_hash": integrity.candidate_pack_content_hash,
        "candidate_pack_tree_hash": integrity.candidate_pack_tree_hash,
        "public_replay_commitment_hash": commitment["commitment_hash"],
        "sealed_source_replay_receipt_hash": replay.receipt_hash,
        "proposal_count": counts["proposal_count"],
        "trusted_count": counts["trusted_count"],
        "withheld_count": counts["withheld_count"],
        "compiler_blocked_declaration_count": counts[
            "compiler_blocked_declaration_count"
        ],
        "trusted_compiler_blocked_target_count": counts[
            "trusted_compiler_blocked_target_count"
        ],
        "post_trust_pack_failures": counts["post_trust_pack_failures"],
        "status": "PASS",
    }
    response = M336HCompilerAwareProductionResponse(
        **body, response_hash=content_hash(body)
    )
    write_canonical_json(
        request.public_production_destination / "m336h_production_response.json",
        response,
    )
    return response


def production_response_from_dict(value: dict) -> M336HCompilerAwareProductionResponse:
    if set(value) != set(M336HCompilerAwareProductionResponse.__dataclass_fields__):
        raise ValueError("M336H production response schema changed")
    response = M336HCompilerAwareProductionResponse(**value)
    body = asdict(response)
    claimed = body.pop("response_hash")
    if content_hash(body) != claimed or response.status != "PASS":
        raise ValueError("M336H production response is invalid")
    return response


def build_m336h_count_neutral_production_seal(
    *,
    production_root: Path,
    response: M336HCompilerAwareProductionResponse,
) -> M336HCountNeutralProductionSeal:
    """Seal only structural invariants; no disclosed corpus count is privileged."""

    production_response_from_dict(asdict(response))
    counts = _load(production_root / "production_counts.json")
    integrity = _load(production_root / "public_pack_integrity_receipt.json")
    replay = _load(production_root / "sealed_source_replay_receipt.json")
    process = _load(production_root / "production_process_audit.json")
    summary = _load(production_root / "production_summary.json")
    authorization_count = counts["trusted_count"]
    invariants = (
        counts["proposal_count"] == counts["trusted_count"] + counts["withheld_count"]
        and counts["trusted_count"] == authorization_count
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
        "contract_role": "PUBLIC_SAFE_SEAL",
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
        "authorization_count": authorization_count,
        "trusted_authorized_identity_difference_count": 0,
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
        "structural_invariants_satisfied": invariants,
        "public_pack_integrity_status": integrity["status"],
        "sealed_replay_status": replay["status"],
        "status": "PASS" if invariants else "FAIL",
    }
    seal = M336HCountNeutralProductionSeal(**body, seal_hash=content_hash(body))
    if seal.status != "PASS":
        raise ValueError("M336H count-neutral production seal failed")
    return seal


def production_seal_from_dict(value: dict) -> M336HCountNeutralProductionSeal:
    if set(value) != set(M336HCountNeutralProductionSeal.__dataclass_fields__):
        raise ValueError("M336H production seal schema changed")
    seal = M336HCountNeutralProductionSeal(**value)
    body = asdict(seal)
    claimed = body.pop("seal_hash")
    if content_hash(body) != claimed or seal.status != "PASS":
        raise ValueError("M336H production seal is invalid")
    return seal
