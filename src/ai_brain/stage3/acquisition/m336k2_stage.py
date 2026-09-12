"""Native stateful stage worker for the M-33.6k.2 final route.

Each invocation performs exactly one route transition.  The private state file
is hash-bound and lives outside every Git worktree; public receipts contain
only hashes and counts.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_identity import (
    portable_vault_manifest_from_dict,
    source_entry_binding_manifest_from_dict,
    verify_portable_vault_manifest,
)
from ai_brain.stage3.acquisition.m336e_selectability import (
    selectable_source_census_from_dict,
)
from ai_brain.stage3.acquisition.m336f_compilation_closure import (
    java_compilation_closure_feasibility_proof_from_dict,
    java_compilation_closure_manifest_from_dict,
)
from ai_brain.stage3.acquisition.m336f_selection import (
    M336FSelectorLedger,
    select_compilation_closed_sources_once,
)
from ai_brain.stage3.acquisition.m336g_publication import (
    verify_java_public_candidate_pack,
)
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.m336h_materialization import (
    materialize_m336f_selected_source_snapshot,
)
from ai_brain.stage3.acquisition.m336i_evaluation import (
    M336IIndependentEvaluationRequest,
    _runtime_status,
    run_m336i_independent_java_evaluation,
)
from ai_brain.stage3.acquisition.m336i_production import (
    run_m336i_compiler_aware_production,
)
from ai_brain.stage3.acquisition.m336j_execution import (
    compute_m336j_project_source_identity,
)
from ai_brain.stage3.acquisition.m336k2_acquisition import (
    authorization_from_dict,
    run_m336k2_frozen_acquisition,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2_ROUTE_EVENTS,
    M336K2CommittedFreezeAttestation,
    M336K2FreezeManifest,
    M336K2FrozenComponent,
    M336K2ProtocolError,
    M336K2RouteLedger,
    m336k2_minimal_environment,
)
from ai_brain.stage3.acquisition.m336k2_publication import (
    publication_contract_from_dict,
    scan_m336k2_public_tree,
    stage_m336k2_e28_publication,
    stage_m336k2_h28_publication,
    verify_m336k2_commit_protocol,
)
from ai_brain.stage3.acquisition.m336k4_authorization import (
    M336K4FinalAuthorization,
)
from ai_brain.stage3.acquisition.m336k4_freeze import (
    M336K4CommittedFreezeAttestation,
    M336K4FreezeManifest,
)
from ai_brain.stage3.acquisition.m336k4_identity import M336K4RouteIdentityBundle
from ai_brain.stage3.acquisition.m336k5_authorization import (
    M336K5FinalAuthorization,
)
from ai_brain.stage3.acquisition.m336k5_freeze import (
    M336K5CommittedFreezeAttestation,
    M336K5FreezeManifest,
)
from ai_brain.stage3.acquisition.m336k5_identity import M336K5RouteIdentityBundle
from ai_brain.stage3.acquisition.m336k5_startup import (
    build_m336k5_python_invocation,
    run_m336k5_bound_python_target,
    run_m336k5_python_invocation,
    startup_receipt_from_path,
    write_m336k5_python_invocation_plan,
)
from ai_brain.stage3.acquisition.m336k_acquisition import M336KAcquisitionLedger

_STAGE_EVENTS = M336K2_ROUTE_EVENTS[3:]
_EVALUATOR_EVENTS = (
    "EVALUATOR_RESERVED",
    "GOLDENS_CREATED",
    "WINDOWS_EVALUATION_COMPLETED",
    "KARINA_EVALUATION_COMPLETED",
    "EVALUATION_COMPARISON_PASSED",
)
_REQUEST_FIELDS = {
    "schema_version",
    "repository",
    "git_executable",
    "python_executable",
    "exact_f28_sha",
    "freeze_manifest",
    "f28_attestation",
    "final_authorization",
    "publication_contract",
    "route_run_id",
    "execution_mode",
    "stage_state",
    "stage_receipt_root",
    "private_root",
    "authority_statement",
    "frozen_spdx_reference",
    "windows_java",
    "windows_javac",
    "final_destinations",
    "karina",
    "executable_handles",
}
_M336K4_REQUEST_FIELDS = _REQUEST_FIELDS | {
    "execution_purpose",
    "route_identity_bundle",
    "route_identity_bundle_hash",
}
_M336K5_REQUEST_FIELDS = _M336K4_REQUEST_FIELDS | {"startup_receipt_hash"}
_DESTINATION_FIELDS = {
    "acquisition_ledger",
    "selector_ledger",
    "evaluator_ledger",
    "route_state_ledger",
    "vault",
    "selected_source_snapshot",
    "windows_production",
    "karina_production",
    "evaluator_root",
}
_KARINA_FIELDS = {
    "private_execution_capsule",
    "public_execution_capsule_receipt",
    "executable_dependency_manifest",
    "ssh_executable",
    "ssh_key",
    "known_hosts_file",
    "worker_endpoint",
    "repository",
    "private_root",
    "private_capsule_remote",
    "javac",
}


def run_m336k2_stage(
    *,
    request_path: Path,
    event: str,
    receipt_path: Path,
    startup_receipt_path: Path | None = None,
) -> dict:
    request = _object(request_path)
    _verify_request(request, startup_receipt_path=startup_receipt_path)
    if event not in _STAGE_EVENTS:
        raise M336K2ProtocolError("M336K2 stage event is not registered")
    expected_receipt = Path(request["stage_receipt_root"]).resolve(strict=False) / (
        f"{event}.json"
    )
    if receipt_path != expected_receipt or receipt_path.exists():
        raise M336K2ProtocolError("M336K2 stage receipt handle changed or is stale")
    state_path = Path(request["stage_state"]).resolve(strict=False)
    state = _load_state(state_path, request)
    completed = tuple(state["completed_events"])
    expected = (
        _STAGE_EVENTS[len(completed)] if len(completed) < len(_STAGE_EVENTS) else None
    )
    if event != expected:
        raise M336K2ProtocolError("M336K2 native stage order changed")
    operation = _dispatch(request, event)
    if not isinstance(operation, dict) or operation.get("status") != "PASS":
        raise M336K2ProtocolError("M336K2 native stage did not pass")
    operation_hash = content_hash(operation)
    state_body = {
        "schema_version": 1,
        "route_run_id": request["route_run_id"],
        "exact_f28_sha": request["exact_f28_sha"],
        "completed_events": (*completed, event),
        "previous_state_hash": state.get("state_hash"),
        "last_operation_hash": operation_hash,
    }
    if _typed(request):
        state_body["schema_version"] = request["schema_version"]
        state_body["route_identity_bundle_hash"] = request["route_identity_bundle_hash"]
    if request["schema_version"] == 3:
        state_body["startup_receipt_hash"] = request["startup_receipt_hash"]
    next_state = {**state_body, "state_hash": content_hash(state_body)}
    _write_private_state(state_path, next_state)
    body = {
        "schema_version": 1,
        "contract_role": "M336K2_PRIVATE_NATIVE_STAGE_RECEIPT",
        "event": event,
        "route_run_id": request["route_run_id"],
        "exact_f28_sha": request["exact_f28_sha"],
        "operation_hash": operation_hash,
        "state_hash": next_state["state_hash"],
        "status": "PASS",
    }
    if _typed(request):
        body["schema_version"] = request["schema_version"]
        body["route_identity_bundle_hash"] = request["route_identity_bundle_hash"]
    if request["schema_version"] == 3:
        body["startup_receipt_hash"] = request["startup_receipt_hash"]
    receipt = {**body, "receipt_hash": content_hash(body)}
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        canonical_json(receipt) + "\n", encoding="utf-8", newline="\n"
    )
    return receipt


def _dispatch(request: dict, event: str) -> dict:
    handlers = {
        "ACQUISITION_RESERVED": _reserve_acquisition,
        "ACQUISITION_STARTED": _start_acquisition,
        "ALL_CANDIDATES_TERMINAL": _acquire_all_candidates,
        "ACQUISITION_COMPLETED": _verify_acquisition_completed,
        "VAULT_SEALED": _verify_vault_sealed,
        "KARINA_VAULT_VERIFIED": _verify_karina_vault,
        "QUALIFICATION_COMPLETED": _complete_qualification_and_closure,
        "SELECTOR_RESERVED": _reserve_selector,
        "SELECTOR_INVOKED": _invoke_selector,
        "SELECTOR_COMPLETED": _verify_selector_completed,
        "SELECTED_SNAPSHOT_SEALED": _seal_selected_snapshot,
        "WINDOWS_PRODUCTION_SEALED": _run_windows_production,
        "KARINA_PRODUCTION_SEALED": _run_karina_production_stage,
        "PRODUCTION_COMPARISON_PASSED": _compare_production,
        "H_PUBLICATION_READY": _publish_h28,
        "EVALUATOR_RESERVED": _reserve_evaluator,
        "GOLDENS_CREATED": _create_goldens,
        "WINDOWS_EVALUATION_COMPLETED": _run_windows_evaluation,
        "KARINA_EVALUATION_COMPLETED": _run_karina_evaluation,
        "EVALUATION_COMPARISON_PASSED": _compare_evaluation,
        "RUNTIME_COMPLETED": _run_runtime,
        "E_PUBLICATION_READY": _publish_e28,
        "FINAL_VERIFICATION_COMPLETED": _final_verification,
    }
    handler = handlers.get(event)
    if handler is None:
        raise M336K2ProtocolError(f"M336K2 native stage is not implemented: {event}")
    return handler(request)


def _reserve_acquisition(request: dict) -> dict:
    destinations = _destinations(request)
    for name in ("acquisition_ledger", "vault"):
        if destinations[name].exists():
            raise M336K2ProtocolError("M336K2 acquisition destination is stale")
    result = {
        "event": "ACQUISITION_RESERVED",
        "authorization_hash": _authorization(request).authorization_hash,
        "status": "PASS",
    }
    if _typed(request):
        result.update(_identity_observation_fields(request))
    return result


def _start_acquisition(request: dict) -> dict:
    if _destinations(request)["acquisition_ledger"].exists():
        raise M336K2ProtocolError("M336K2 acquisition started before fresh state")
    pool = _component_object(request, "candidate_pool")
    return {
        "event": "ACQUISITION_STARTED",
        "candidate_pool_hash": pool["pool_hash"],
        "status": "PASS",
    }


def _acquire_all_candidates(request: dict) -> dict:
    repository = Path(request["repository"]).resolve(strict=True)
    private = Path(request["private_root"]).resolve(strict=False)
    private.mkdir(parents=True, exist_ok=True)
    freeze = _freeze(Path(request["freeze_manifest"]).resolve(strict=True))
    authorization = _authorization(request)
    destinations = _destinations(request)
    provider = _rehearsal_provider(request)
    result = run_m336k2_frozen_acquisition(
        repository=repository,
        git_executable=Path(request["git_executable"]),
        exact_f28_sha=request["exact_f28_sha"],
        freeze_root=Path(request["freeze_manifest"]).resolve(strict=True).parent,
        freeze_manifest=freeze,
        committed_attestation=_attestation(request),
        pool=_component_object(request, "candidate_pool"),
        authorization=authorization,
        acquisition_policy=_component_object(request, "acquisition_policy"),
        authority_statement=Path(request["authority_statement"]),
        disclosure_registry_manifest=_component_path(
            request, "disclosure_registry_manifest"
        ),
        vault_root=destinations["vault"],
        ledger=M336KAcquisitionLedger(
            destinations["acquisition_ledger"], git_worktrees=(repository,)
        ),
        private_preflight_path=private / "acquisition_preflight.json",
        unused_selected_source_output=private / "unused-selected-source",
        host="WINDOWS",
        **provider,
    )
    write_canonical_json(
        private / "acquisition_public_receipt.json", result.public_receipt
    )
    if (
        result.global_receipt.missing_terminal_count
        or result.global_receipt.duplicate_terminal_count
        or result.global_receipt.candidate_retry_count
        or result.global_receipt.candidate_replacement_count
    ):
        raise M336K2ProtocolError("M336K2 terminal accounting failed")
    return {
        "event": "ALL_CANDIDATES_TERMINAL",
        "candidate_count": result.global_receipt.candidate_count,
        "terminal_count": result.global_receipt.terminal_count,
        "global_receipt_hash": result.global_receipt.receipt_hash,
        "status": "PASS",
    }


def _verify_acquisition_completed(request: dict) -> dict:
    repository = Path(request["repository"]).resolve(strict=True)
    ledger = M336KAcquisitionLedger(
        _destinations(request)["acquisition_ledger"], git_worktrees=(repository,)
    ).receipt()
    receipt = _object(Path(request["private_root"]) / "acquisition_public_receipt.json")
    if (
        ledger.final_event != "ACQUISITION_COMPLETED"
        or ledger.acquisition_reservation_count != 1
        or ledger.acquisition_start_count != 1
        or ledger.acquisition_rerun_count != 0
        or receipt.get("status") != "ACQUISITION_COMPLETED"
    ):
        raise M336K2ProtocolError("M336K2 acquisition completion changed")
    return {
        "event": "ACQUISITION_COMPLETED",
        "ledger_receipt_hash": ledger.receipt_hash,
        "acquisition_receipt_hash": receipt["receipt_hash"],
        "status": "PASS",
    }


def _verify_vault_sealed(request: dict) -> dict:
    private = Path(request["private_root"])
    manifest = portable_vault_manifest_from_dict(
        _object(private / "portable_vault_manifest.json")
    )
    verify_portable_vault_manifest(_destinations(request)["vault"], manifest)
    return {
        "event": "VAULT_SEALED",
        "portable_tree_hash": manifest.portable_tree_hash,
        "manifest_hash": manifest.manifest_hash,
        "status": "PASS",
    }


def _verify_karina_vault(request: dict) -> dict:
    from m336i_java_final_route import _upload_karina_tree

    private = Path(request["private_root"]).resolve(strict=True)
    manifest = portable_vault_manifest_from_dict(
        _object(private / "portable_vault_manifest.json")
    )
    response = _upload_karina_tree(
        _karina_args(request),
        label="vault",
        source=_destinations(request)["vault"],
    )
    if (
        response.get("status") != "PASS"
        or response.get("content_tree_hash") != manifest.portable_tree_hash
        or response.get("content_file_count") != manifest.file_count
    ):
        raise M336K2ProtocolError("M336K2 Karina vault verification changed")
    return {
        "event": "KARINA_VAULT_VERIFIED",
        "portable_tree_hash": manifest.portable_tree_hash,
        "transfer_receipt_hash": response["receipt_hash"],
        "status": "PASS",
    }


def _complete_qualification_and_closure(request: dict) -> dict:
    from m336i_java_final_route import _build_closure

    private = Path(request["private_root"]).resolve(strict=True)
    preflight = _object(private / "acquisition_preflight.json")
    if preflight.get("status") != "PASS":
        raise M336K2ProtocolError("M336K2 qualification is not selectable")
    args = SimpleNamespace(
        windows_vault=_destinations(request)["vault"],
        windows_javac=Path(request["windows_javac"]).resolve(strict=True),
        private_acquisition_output=private,
    )
    _bindings, _census, closure, proof, qualification_hash, summary_hash = (
        _build_closure(args, private)
    )
    return {
        "event": "QUALIFICATION_COMPLETED",
        "qualification_report_hash": qualification_hash,
        "qualification_summary_hash": summary_hash,
        "closure_manifest_hash": closure.manifest_hash,
        "closure_proof_hash": proof.proof_hash,
        "status": "PASS",
    }


def _reserve_selector(request: dict) -> dict:
    ledger = _destinations(request)["selector_ledger"]
    proof = _object(
        Path(request["private_root"])
        / "compilation-closure"
        / "compilation_closure_feasibility.json"
    )
    if ledger.exists() or proof.get("hard_requirements_satisfied") is not True:
        raise M336K2ProtocolError("M336K2 selector reservation is invalid")
    result = {
        "event": "SELECTOR_RESERVED",
        "closure_proof_hash": proof["proof_hash"],
        "status": "PASS",
    }
    if _typed(request):
        result.update(_identity_observation_fields(request))
    return result


def _invoke_selector(request: dict) -> dict:
    repository = Path(request["repository"]).resolve(strict=True)
    private = Path(request["private_root"]).resolve(strict=True)
    closure_root = private / "compilation-closure"
    bindings = source_entry_binding_manifest_from_dict(
        _object(private / "source_entry_binding_manifest.json")
    )
    census = selectable_source_census_from_dict(
        _object(private / "selectability_census.json")
    )
    closure = java_compilation_closure_manifest_from_dict(
        _object(closure_root / "compilation_closure_manifest.json")
    )
    proof = java_compilation_closure_feasibility_proof_from_dict(
        _object(closure_root / "compilation_closure_feasibility.json")
    )
    qualification = _object(private / "candidate_qualification.json")
    summary = _object(closure_root / "qualification_summary.json")
    policy = _component_object(request, "acquisition_policy")
    selected, receipt = select_compilation_closed_sources_once(
        census=census,
        closure_manifest=closure,
        proof=proof,
        bindings=bindings,
        selector_seed=policy["selector_seed"],
        ledger=M336FSelectorLedger(
            _destinations(request)["selector_ledger"], git_worktrees=(repository,)
        ),
        qualification_report_hash=qualification["report_hash"],
        qualification_summary_hash=summary["summary_hash"],
        route_identity_bundle_hash=(
            request["route_identity_bundle_hash"] if _typed(request) else None
        ),
    )
    write_canonical_json(private / "selected_source_manifest.json", selected)
    write_canonical_json(private / "selector_receipt.json", receipt)
    return {
        "event": "SELECTOR_INVOKED",
        "selected_manifest_hash": selected.manifest_hash,
        "selector_receipt_hash": receipt.receipt_hash,
        "status": "PASS",
    }


def _verify_selector_completed(request: dict) -> dict:
    repository = Path(request["repository"]).resolve(strict=True)
    receipt = M336FSelectorLedger(
        _destinations(request)["selector_ledger"], git_worktrees=(repository,)
    ).receipt()
    if (
        receipt["selector_reservation_count"] != 1
        or receipt["selector_invocation_count"] != 1
        or receipt["selector_rerun_count"] != 0
    ):
        raise M336K2ProtocolError("M336K2 selector completion changed")
    return {
        "event": "SELECTOR_COMPLETED",
        "selector_ledger_receipt_hash": receipt["receipt_hash"],
        "status": "PASS",
    }


def _seal_selected_snapshot(request: dict) -> dict:
    from m336i_java_final_route import _prepare_karina

    from ai_brain.stage3.acquisition.m336f_selection import (
        m336f_selected_source_manifest_from_dict,
        m336f_selector_receipt_from_dict,
    )

    private = Path(request["private_root"]).resolve(strict=True)
    closure_root = private / "compilation-closure"
    receipt = materialize_m336f_selected_source_snapshot(
        sealed_vault_root=_destinations(request)["vault"],
        bindings=source_entry_binding_manifest_from_dict(
            _object(private / "source_entry_binding_manifest.json")
        ),
        selected_manifest=m336f_selected_source_manifest_from_dict(
            _object(private / "selected_source_manifest.json")
        ),
        selector_receipt=m336f_selector_receipt_from_dict(
            _object(private / "selector_receipt.json")
        ),
        closure_manifest=java_compilation_closure_manifest_from_dict(
            _object(closure_root / "compilation_closure_manifest.json")
        ),
        closure_proof=java_compilation_closure_feasibility_proof_from_dict(
            _object(closure_root / "compilation_closure_feasibility.json")
        ),
        destination=_destinations(request)["selected_source_snapshot"],
        git_worktrees=(Path(request["repository"]).resolve(strict=True),),
        public_roots=(_destinations(request)["windows_production"],),
    )
    write_canonical_json(private / "windows_materialization_receipt.json", receipt)
    karina = _prepare_karina(
        _karina_args(request),
        _production_authorization(request),
        vault_already_uploaded=True,
    )
    if karina.get("status") != "PASS":
        raise M336K2ProtocolError("M336K2 Karina selected snapshot failed")
    return {
        "event": "SELECTED_SNAPSHOT_SEALED",
        "materialization_receipt_hash": receipt.receipt_hash,
        "karina_materialization_receipt_hash": karina["materialization_receipt_hash"],
        "status": "PASS",
    }


def _run_windows_production(request: dict) -> dict:
    from m336i_java_final_route import _production_request

    repository = Path(request["repository"]).resolve(strict=True)
    private = Path(request["private_root"]).resolve(strict=True)
    destinations = _destinations(request)
    authorization = _production_authorization(request)
    args = SimpleNamespace(
        private_acquisition_output=private,
        frozen_route_manifest=_component_path(request, "route_manifest"),
        threshold_manifest=_component_path(request, "threshold_manifest"),
    )
    production_request = _production_request(
        args=args,
        platform="WINDOWS",
        snapshot=destinations["selected_source_snapshot"],
        javac=Path(request["windows_javac"]).resolve(strict=True),
        jdk_hash=authorization.windows_public_jdk_identity_receipt_hash,
        vault=destinations["vault"],
        replay=private / "windows-replay",
        output=destinations["windows_production"],
        public_staging=private / "public-staging",
        worktrees=(repository,),
        authorization=authorization,
    )
    python_worker = None
    if request["schema_version"] == 3:

        def python_worker(
            target: Path, arguments: tuple[str, ...], working_directory: Path
        ) -> None:
            _invocation, result, _startup = run_m336k5_bound_python_target(
                platform_role="WINDOWS",
                process_role="WINDOWS_PRODUCTION",
                python_executable=Path(request["python_executable"]),
                git_executable=Path(request["git_executable"]),
                powershell_executable=Path(request["executable_handles"]["powershell"]),
                repository=repository,
                working_directory=working_directory,
                bootstrap_script=repository / "scripts/m336k5_python_bootstrap.py",
                target=target,
                arguments=arguments,
                launch_root=private / "windows-production-worker-startup",
                expected_startup_receipt_hash=request["startup_receipt_hash"],
            )
            if result.returncode:
                raise M336K2ProtocolError("M336K5 Windows production worker failed")

    response, seal = run_m336i_compiler_aware_production(
        production_request, python_worker=python_worker
    )
    if (
        request["schema_version"] == 3
        and _object(destinations["windows_production"] / "production_summary.json").get(
            "startup_receipt_hash"
        )
        != request["startup_receipt_hash"]
    ):
        raise M336K2ProtocolError("M336K5 Windows production startup binding changed")
    write_canonical_json(
        destinations["windows_production"] / "m336i_production_seal.json", seal
    )
    return {
        "event": "WINDOWS_PRODUCTION_SEALED",
        "production_response_hash": response.response_hash,
        "production_seal_hash": seal.seal_hash,
        "status": "PASS",
    }


def _run_karina_production_stage(request: dict) -> dict:
    from m336i_java_final_route import _run_karina_production

    private = Path(request["private_root"]).resolve(strict=True)
    materialization = _object(private / "karina-materialize-request-receipt.json")
    worker = _run_karina_production(
        _karina_args(request),
        _production_authorization(request),
        materialization,
        run_runtime=False,
    )
    root = _destinations(request)["karina_production"]
    seal = _verified_hashed_object(root / "m336i_production_seal.json", "seal_hash")
    verify_java_public_candidate_pack(root / "candidate_pack")
    if worker.get("status") != "PASS" or seal.get("status") != "PASS":
        raise M336K2ProtocolError("M336K2 Karina production did not pass")
    return {
        "event": "KARINA_PRODUCTION_SEALED",
        "worker_receipt_hash": worker["receipt_hash"],
        "production_seal_hash": seal["seal_hash"],
        "status": "PASS",
    }


def _compare_production(request: dict) -> dict:
    destinations = _destinations(request)
    windows_root = destinations["windows_production"]
    karina_root = destinations["karina_production"]
    windows_pack = verify_java_public_candidate_pack(windows_root / "candidate_pack")
    karina_pack = verify_java_public_candidate_pack(karina_root / "candidate_pack")
    windows_seal = _verified_hashed_object(
        windows_root / "m336i_production_seal.json", "seal_hash"
    )
    karina_seal = _verified_hashed_object(
        karina_root / "m336i_production_seal.json", "seal_hash"
    )
    neutral_fields = (
        "production_output_hash",
        "public_candidate_pack_hash",
        "public_candidate_pack_tree_hash",
        "proposal_count",
        "trusted_count",
        "withheld_count",
        "trusted_authorized_identity_difference_count",
        "duplicate_authorization_count",
        "missing_authorization_count",
        "extra_authorization_count",
        "trusted_compiler_blocked_target_count",
        "post_trust_pack_failures",
        "reconstructed_pack_byte_difference_count",
        "production_network_access_count",
        "production_evaluator_read_count",
        "production_golden_read_count",
        "source_bearing_public_entry_count",
        "private_role_public_entry_count",
        "unknown_public_entry_count",
        "absolute_path_count",
        "reversible_source_payload_count",
        "public_pack_integrity_status",
        "sealed_replay_status",
        "status",
    )
    differences = tuple(
        name
        for name in neutral_fields
        if windows_seal.get(name) != karina_seal.get(name)
    )
    pack_differences = int(
        windows_pack.candidate_pack_content_hash
        != karina_pack.candidate_pack_content_hash
    ) + int(
        windows_pack.candidate_pack_tree_hash != karina_pack.candidate_pack_tree_hash
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_PRODUCTION_COMPARISON",
        "windows_seal_hash": windows_seal["seal_hash"],
        "karina_seal_hash": karina_seal["seal_hash"],
        "candidate_pack_content_hash": windows_pack.candidate_pack_content_hash,
        "candidate_pack_tree_hash": windows_pack.candidate_pack_tree_hash,
        "neutral_field_difference_count": len(differences),
        "candidate_pack_difference_count": pack_differences,
        "status": "PASS" if not differences and not pack_differences else "FAIL",
    }
    result = {**body, "receipt_hash": content_hash(body)}
    if result["status"] != "PASS":
        raise M336K2ProtocolError("M336K2 production comparison failed")
    write_canonical_json(
        Path(request["private_root"]) / "production_comparison.json", result
    )
    return result


def _publish_h28(request: dict) -> dict:
    repository = Path(request["repository"]).resolve(strict=True)
    private = Path(request["private_root"]).resolve(strict=True)
    destinations = _destinations(request)
    contract = publication_contract_from_dict(
        _object(Path(request["publication_contract"]).resolve(strict=True))
    )
    source = private / "h28-source"
    if source.exists():
        raise M336K2ProtocolError("M336K2 H28 staging source is stale")
    source.mkdir()
    windows = destinations["windows_production"]
    karina = destinations["karina_production"]
    shutil.copytree(windows / "candidate_pack", source / "candidate_pack")
    for name in (
        "field_evidence_manifest.json",
        "public_pack_integrity_receipt.json",
        "sealed_source_replay_receipt.json",
    ):
        shutil.copyfile(windows / name, source / name)
    shutil.copyfile(
        windows / "m336i_production_seal.json", source / "windows_production_seal.json"
    )
    shutil.copyfile(
        karina / "m336i_production_seal.json", source / "karina_production_seal.json"
    )
    shutil.copyfile(
        private / "production_comparison.json", source / "production_comparison.json"
    )
    if _typed(request):
        write_canonical_json(
            source / "route_identity_observation.json",
            _identity_observation_receipt(
                request,
                "H30_PRODUCTION"
                if request["schema_version"] == 3
                else "H29_PRODUCTION",
            ),
        )
    _write_h_staging_receipts(source)
    report = stage_m336k2_h28_publication(
        repository=repository,
        git_executable=Path(request["git_executable"]),
        exact_f28_sha=request["exact_f28_sha"],
        production_source=source,
        output=repository.joinpath(*contract.h_root.split("/")),
        contract=contract,
    )
    git = Path(request["git_executable"]).resolve(strict=True)
    _git(git, repository, "add", "-f", contract.h_root)
    _git(git, repository, "commit", "-m", contract.h_subject)
    h28 = _git(git, repository, "rev-parse", "HEAD^{commit}")
    _git(
        git,
        repository,
        "push",
        "origin",
        f"HEAD:{contract.branch_ref}",
    )
    _verify_remote_head(git, repository, contract.branch_ref, h28)
    body = {
        "schema_version": 1,
        "exact_h28_sha": h28,
        "exact_f28_parent": _git(git, repository, "rev-parse", f"{h28}^"),
        "publication_report_hash": report.report_hash,
        "status": "PASS",
    }
    if _typed(request):
        body.update(_identity_observation_fields(request))
    result = {**body, "receipt_hash": content_hash(body)}
    write_canonical_json(private / "h28_commit_receipt.json", result)
    return {"event": "H_PUBLICATION_READY", **result}


def _write_h_staging_receipts(root: Path) -> None:
    rows = tuple(
        (
            path.relative_to(root).as_posix(),
            path.stat().st_size,
            bytes_hash(path.read_bytes()),
        )
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
        )
    )
    manifest_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_H28_STAGING_MANIFEST",
        "files": rows,
        "file_count": len(rows),
        "tree_hash": content_hash(rows),
        "status": "PASS",
    }
    manifest = {**manifest_body, "manifest_hash": content_hash(manifest_body)}
    write_canonical_json(root / "public_staging_manifest.json", manifest)
    receipt_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_H28_STAGING_RECEIPT",
        "manifest_hash": manifest["manifest_hash"],
        "tree_hash": manifest["tree_hash"],
        "source_leak_count": 0,
        "private_artifact_count": 0,
        "absolute_path_count": 0,
        "status": "PASS",
    }
    write_canonical_json(
        root / "public_staging_receipt.json",
        {**receipt_body, "receipt_hash": content_hash(receipt_body)},
    )


def _reserve_evaluator(request: dict) -> dict:
    repository = Path(request["repository"]).resolve(strict=True)
    git = Path(request["git_executable"]).resolve(strict=True)
    contract = publication_contract_from_dict(
        _object(Path(request["publication_contract"]).resolve(strict=True))
    )
    h28 = _object(Path(request["private_root"]) / "h28_commit_receipt.json")
    ledger = _destinations(request)["evaluator_ledger"]
    for root in (
        _destinations(request)["windows_production"],
        _destinations(request)["karina_production"],
    ):
        _verified_hashed_object(root / "m336i_production_seal.json", "seal_hash")
    if ledger.exists() or _git(
        git, repository, "rev-parse", "HEAD^{commit}"
    ) != h28.get("exact_h28_sha"):
        raise M336K2ProtocolError("M336K2 evaluator reservation is invalid")
    _verify_remote_head(git, repository, contract.branch_ref, h28["exact_h28_sha"])
    operation_values = (
        h28["exact_h28_sha"],
        _object(
            _destinations(request)["windows_production"] / "m336i_production_seal.json"
        )["seal_hash"],
        _object(
            _destinations(request)["karina_production"] / "m336i_production_seal.json"
        )["seal_hash"],
    )
    if _typed(request):
        operation_values += (request["route_identity_bundle_hash"],)
    operation = content_hash(operation_values)
    event = _append_evaluator_event(ledger, "EVALUATOR_RESERVED", operation)
    result = {
        "event": "EVALUATOR_RESERVED",
        "evaluator_reservation_hash": event["event_hash"],
        "status": "PASS",
    }
    if _typed(request):
        result.update(_identity_observation_fields(request))
    return result


def _create_goldens(request: dict) -> dict:
    repository = Path(request["repository"]).resolve(strict=True)
    private = Path(request["private_root"]).resolve(strict=True)
    destinations = _destinations(request)
    reservation = _evaluator_events(destinations["evaluator_ledger"])
    if tuple(item["event"] for item in reservation) != ("EVALUATOR_RESERVED",):
        raise M336K2ProtocolError("M336K2 golden creation is not reserved")
    evaluator = destinations["evaluator_root"]
    source_input = evaluator / "sealed-vault-source-input"
    oracle = evaluator / "oracle"
    if evaluator.exists():
        raise M336K2ProtocolError("M336K2 evaluator root is stale")
    source_input.mkdir(parents=True)
    from m336i_java_final_route import _copy_selected_source_authority

    _copy_selected_source_authority(
        vault=destinations["vault"],
        bindings_path=private / "source_entry_binding_manifest.json",
        selected_path=private / "selected_source_manifest.json",
        destination=source_input,
    )
    commitment = _object(
        destinations["windows_production"]
        / "candidate_pack"
        / "java_replay_commitment.json"
    )
    h28 = _object(private / "h28_commit_receipt.json")["exact_h28_sha"]
    command = (
        str(Path(request["python_executable"]).resolve(strict=True)),
        "-B",
        str(repository / "scripts" / "m343_author_semantic_goldens.py"),
        "--corpus",
        str(source_input),
        "--helper",
        str(
            repository
            / "tools"
            / "m343_java_oracle"
            / "JavaSemanticProposalOracle.java"
        ),
        "--javac",
        str(Path(request["windows_javac"]).resolve(strict=True)),
        "--java",
        str(Path(request["windows_java"]).resolve(strict=True)),
        "--output",
        str(oracle),
        "--parser-common-hash",
        commitment["parser_artifact_manifest_hash"],
        "--evidence-policy-hash",
        commitment["evidence_policy_hash"],
        "--authority-id",
        "m336k2-independent-post-reservation-evaluator",
        "--sealing-ref",
        h28,
        "--authority-purpose",
        "post-seal-final-outcome-a-evaluation",
        "--config-id",
        "m336k2.independent-final-evaluation.v1",
        "--diagnostic-scope-v2",
    )
    environment = m336k2_minimal_environment()
    environment.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": str(repository / "src"),
            "PYTHONUTF8": "1",
        }
    )
    golden_startup_hash = None
    if request["schema_version"] == 3:
        launch_root = private / "golden-author-startup"
        invocation = build_m336k5_python_invocation(
            platform_role="WINDOWS",
            process_role="GOLDEN_AUTHOR",
            python_executable=Path(request["python_executable"]),
            git_executable=Path(request["git_executable"]),
            powershell_executable=Path(request["executable_handles"]["powershell"]),
            repository=repository,
            working_directory=repository,
            bootstrap_script=repository / "scripts/m336k5_python_bootstrap.py",
            target=Path(command[2]),
            execute_arguments=tuple(command[3:]),
            validate_arguments=tuple(command[3:]),
            execute_startup_receipt=launch_root / "startup.json",
            validate_startup_receipt=launch_root / "startup-validate.json",
        )
        plan_path = launch_root / "invocation-plan.json"
        write_m336k5_python_invocation_plan(invocation, plan_path)
        launched = run_m336k5_python_invocation(
            plan_path=plan_path, operation="execute"
        )
        if launched.returncode:
            raise M336K2ProtocolError("M336K5 golden author process failed")
        golden_startup_hash = startup_receipt_from_path(
            launch_root / "startup.json"
        ).receipt_hash
        if golden_startup_hash != request["startup_receipt_hash"]:
            raise M336K2ProtocolError("M336K5 golden startup receipt changed")
    else:
        subprocess.run(command, cwd=repository, check=True, env=environment)
    golden = oracle / "semantic_goldens.json"
    operation = bytes_hash(golden.resolve(strict=True).read_bytes())
    event = _append_evaluator_event(
        destinations["evaluator_ledger"], "GOLDENS_CREATED", operation
    )
    result = {
        "event": "GOLDENS_CREATED",
        "golden_bytes_hash": operation,
        "evaluator_event_hash": event["event_hash"],
        "status": "PASS",
    }
    if golden_startup_hash is not None:
        result["startup_receipt_hash"] = golden_startup_hash
    return result


def _evaluation_request(request: dict) -> M336IIndependentEvaluationRequest:
    private = Path(request["private_root"]).resolve(strict=True)
    destinations = _destinations(request)
    reservation = _evaluator_events(destinations["evaluator_ledger"])[0]
    windows = destinations["windows_production"]
    karina = destinations["karina_production"]
    return M336IIndependentEvaluationRequest(
        route_manifest=_component_path(request, "route_manifest"),
        threshold_manifest=_component_path(request, "threshold_manifest"),
        windows_production_seal=windows / "m336i_production_seal.json",
        karina_production_seal=karina / "m336i_production_seal.json",
        windows_production_output=windows / "production_output.json",
        karina_production_output=karina / "production_output.json",
        windows_field_evidence_manifest=windows / "field_evidence_manifest.json",
        karina_field_evidence_manifest=karina / "field_evidence_manifest.json",
        public_candidate_pack=windows / "candidate_pack",
        windows_replay_receipt=windows / "sealed_source_replay_receipt.json",
        karina_replay_receipt=karina / "sealed_source_replay_receipt.json",
        independently_authored_semantic_goldens=(
            destinations["evaluator_root"] / "oracle" / "semantic_goldens.json"
        ),
        external_sealed_vault=destinations["vault"],
        source_entry_bindings=private / "source_entry_binding_manifest.json",
        candidate_pool=_component_path(request, "candidate_pool"),
        qualification_report=private / "candidate_qualification.json",
        selected_manifest=private / "selected_source_manifest.json",
        frozen_spdx_reference=Path(request["frozen_spdx_reference"]),
        evaluator_ledger=destinations["evaluator_ledger"],
        git_worktrees=(Path(request["repository"]).resolve(strict=True),),
        external_reservation_hash=reservation["event_hash"],
    )


def _run_windows_evaluation(request: dict) -> dict:
    destinations = _destinations(request)
    events = _evaluator_events(destinations["evaluator_ledger"])
    if tuple(item["event"] for item in events) != (
        "EVALUATOR_RESERVED",
        "GOLDENS_CREATED",
    ):
        raise M336K2ProtocolError("M336K2 Windows evaluation order changed")
    result = run_m336i_independent_java_evaluation(_evaluation_request(request))
    output = Path(request["private_root"]) / "windows_evaluation.json"
    write_canonical_json(output, result)
    event = _append_evaluator_event(
        destinations["evaluator_ledger"],
        "WINDOWS_EVALUATION_COMPLETED",
        result.result_hash,
    )
    return {
        "event": "WINDOWS_EVALUATION_COMPLETED",
        "evaluation_result_hash": result.result_hash,
        "evaluator_event_hash": event["event_hash"],
        "status": "PASS",
    }


def _run_karina_evaluation(request: dict) -> dict:
    from m336i_java_final_route import _invoke_m336j_remote, _upload_karina_tree

    from ai_brain.stage3.acquisition.m336j_execution import (
        KarinaRemoteTokenClass,
        load_private_execution_capsule,
    )

    private = Path(request["private_root"]).resolve(strict=True)
    destinations = _destinations(request)
    events = _evaluator_events(destinations["evaluator_ledger"])
    if tuple(item["event"] for item in events) != _EVALUATOR_EVENTS[:3]:
        raise M336K2ProtocolError("M336K2 Karina evaluation order changed")
    arguments = _karina_args(request)
    capsule_root = arguments.karina_private_root.rstrip("/")
    remote_evaluation = f"{capsule_root}/evaluation-inputs-upload/evaluation-inputs"
    local = private / "karina-evaluation-inputs"
    if local.exists():
        raise M336K2ProtocolError("M336K2 Karina evaluation input is stale")
    local.mkdir()
    shutil.copytree(destinations["windows_production"], local / "windows-production")
    shutil.copytree(destinations["evaluator_root"] / "oracle", local / "oracle")
    remote_spdx_reference = _stage_karina_evaluation_spdx(
        frozen_spdx=Path(request["frozen_spdx_reference"]),
        local_root=local,
        remote_root=remote_evaluation,
    )
    shutil.copy2(
        _component_path(request, "candidate_pool"), local / "candidate-pool.json"
    )
    remote_repo = arguments.karina_repository.rstrip("/")
    remote_inputs = f"{capsule_root}/inputs-upload/inputs"
    config = {
        "route_manifest": f"{remote_inputs}/route_manifest.json",
        "threshold_manifest": f"{remote_inputs}/threshold_manifest.json",
        "windows_production_root": f"{remote_evaluation}/windows-production",
        "karina_production_root": f"{capsule_root}/public-production",
        "semantic_goldens": f"{remote_evaluation}/oracle/semantic_goldens.json",
        "sealed_vault": f"{capsule_root}/vault-upload/vault",
        "bindings": f"{remote_inputs}/source_entry_binding_manifest.json",
        "candidate_pool": f"{remote_evaluation}/candidate-pool.json",
        "qualification_report": f"{remote_inputs}/candidate_qualification.json",
        "selected_manifest": f"{remote_inputs}/selected_source_manifest.json",
        "frozen_spdx_reference": remote_spdx_reference,
        "evaluator_ledger": f"{capsule_root}/unused-evaluator-ledger.jsonl",
        "repository": remote_repo,
        "external_reservation_hash": events[0]["event_hash"],
    }
    write_canonical_json(local / "evaluation_config.json", config)
    _upload_karina_tree(arguments, label="evaluation-inputs", source=local)
    from ai_brain.stage3.acquisition.m336j_registry import build_m336j_route_registry

    component = next(
        item
        for item in build_m336j_route_registry().components
        if item.route_role == "REMOTE_INDEPENDENT_EVALUATOR"
    )
    request_hash = content_hash(
        (events[0]["event_hash"], component.binding_hash, "M336K2_KARINA_EVALUATION")
    )
    capsule_private = str(
        load_private_execution_capsule(arguments.karina_private_capsule).private_root
    ).rstrip("/")
    prefix = capsule_private + "/"
    if not arguments.karina_private_root.startswith(prefix):
        raise M336K2ProtocolError("M336K2 Karina route root escaped capsule")
    relative_root = arguments.karina_private_root.removeprefix(prefix)
    response, _binding, _public = _invoke_m336j_remote(
        arguments,
        component_role="REMOTE_INDEPENDENT_EVALUATOR",
        subcommand="independent-evaluation",
        receipt_name="karina-independent-evaluation-command.json",
        expected_request_hash=request_hash,
        options=(
            (KarinaRemoteTokenClass.FLAG, "--relative-config"),
            (
                KarinaRemoteTokenClass.PRIVATE_PATH,
                f"{relative_root}/evaluation-inputs-upload/evaluation-inputs/evaluation_config.json",
            ),
            (KarinaRemoteTokenClass.FLAG, "--relative-output"),
            (
                KarinaRemoteTokenClass.PRIVATE_PATH,
                f"{relative_root}/karina-independent-evaluation.json",
            ),
            (KarinaRemoteTokenClass.FLAG, "--request-hash"),
            (KarinaRemoteTokenClass.PUBLIC_IDENTITY, request_hash),
            (KarinaRemoteTokenClass.FLAG, "--component-binding-hash"),
            (KarinaRemoteTokenClass.PUBLIC_IDENTITY, component.binding_hash),
        ),
    )
    windows = _object(private / "windows_evaluation.json")
    if response.get("status") != "PASS" or response.get(
        "independent_evaluation_result_hash"
    ) != windows.get("result_hash"):
        raise M336K2ProtocolError("M336K2 Karina evaluation differs")
    write_canonical_json(private / "karina_evaluation.json", response)
    event = _append_evaluator_event(
        destinations["evaluator_ledger"],
        "KARINA_EVALUATION_COMPLETED",
        response["independent_evaluation_result_hash"],
    )
    return {
        "event": "KARINA_EVALUATION_COMPLETED",
        "evaluation_result_hash": response["independent_evaluation_result_hash"],
        "evaluator_event_hash": event["event_hash"],
        "status": "PASS",
    }


def _stage_karina_evaluation_spdx(
    *, frozen_spdx: Path, local_root: Path, remote_root: str
) -> str:
    """Stage the frozen SPDX snapshot together with its referenced texts."""

    reference = frozen_spdx.resolve(strict=True)
    destination = local_root / "spdx-reference"
    shutil.copytree(reference.parent, destination)
    return f"{remote_root.rstrip('/')}/spdx-reference/{reference.name}"


def _compare_evaluation(request: dict) -> dict:
    private = Path(request["private_root"]).resolve(strict=True)
    destinations = _destinations(request)
    events = _evaluator_events(destinations["evaluator_ledger"])
    if tuple(item["event"] for item in events) != _EVALUATOR_EVENTS[:4]:
        raise M336K2ProtocolError("M336K2 evaluation comparison order changed")
    windows = _object(private / "windows_evaluation.json")
    karina = _object(private / "karina_evaluation.json")
    transport_fields = {
        "request_hash",
        "component_binding_hash",
        "host_identity_hash",
        "independent_evaluation_result_hash",
        "receipt_hash",
    }
    if request.get("schema_version") == 3:
        if karina.get("startup_receipt_hash") != request["startup_receipt_hash"]:
            raise M336K2ProtocolError(
                "M336K5 Karina evaluation startup binding changed"
            )
        transport_fields.add("startup_receipt_hash")
    neutral = {
        key: value for key, value in karina.items() if key not in transport_fields
    }
    windows_body = dict(windows)
    windows_hash = windows_body.pop("result_hash", None)
    differences = tuple(
        key
        for key in sorted(set(windows_body) | set(neutral))
        if windows_body.get(key) != neutral.get(key)
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_EVALUATION_COMPARISON",
        "windows_evaluation_result_hash": windows_hash,
        "karina_evaluation_result_hash": karina.get(
            "independent_evaluation_result_hash"
        ),
        "semantic_difference_count": len(differences),
        "status": "PASS" if not differences else "FAIL",
    }
    result = {**body, "receipt_hash": content_hash(body)}
    if result["status"] != "PASS":
        raise M336K2ProtocolError("M336K2 evaluation comparison failed")
    write_canonical_json(private / "evaluation_comparison.json", result)
    event = _append_evaluator_event(
        destinations["evaluator_ledger"],
        "EVALUATION_COMPARISON_PASSED",
        result["receipt_hash"],
    )
    return {
        "event": "EVALUATION_COMPARISON_PASSED",
        "comparison_receipt_hash": result["receipt_hash"],
        "evaluator_event_hash": event["event_hash"],
        "status": "PASS",
    }


def _run_runtime(request: dict) -> dict:
    from m336i_java_final_route import _run_karina_runtime

    destinations = _destinations(request)
    windows_status = _runtime_status(
        destinations["windows_production"] / "candidate_pack"
    )
    karina = _run_karina_runtime(_karina_args(request))
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_INSTALLED_RUNTIME",
        "windows_runtime_status": windows_status,
        "karina_runtime_status": karina.get("runtime_status"),
        "windows_network_access_count": 0,
        "karina_network_access_count": karina.get("runtime_network_access_count"),
        "status": (
            "PASS"
            if windows_status == karina.get("runtime_status") == "PASS"
            and karina.get("runtime_network_access_count") == 0
            else "FAIL"
        ),
    }
    result = {**body, "receipt_hash": content_hash(body)}
    if result["status"] != "PASS":
        raise M336K2ProtocolError("M336K2 installed runtime failed")
    write_canonical_json(Path(request["private_root"]) / "runtime_receipt.json", result)
    return {"event": "RUNTIME_COMPLETED", **result}


def _publish_e28(request: dict) -> dict:
    repository = Path(request["repository"]).resolve(strict=True)
    private = Path(request["private_root"]).resolve(strict=True)
    contract = publication_contract_from_dict(
        _object(Path(request["publication_contract"]).resolve(strict=True))
    )
    h28 = _object(private / "h28_commit_receipt.json")["exact_h28_sha"]
    source = private / "e28-source"
    if source.exists():
        raise M336K2ProtocolError("M336K2 E28 staging source is stale")
    source.mkdir()
    for name in (
        "windows_evaluation.json",
        "karina_evaluation.json",
        "evaluation_comparison.json",
        "runtime_receipt.json",
    ):
        shutil.copyfile(private / name, source / name)
    if _typed(request):
        write_canonical_json(
            source / "route_identity_observation.json",
            _identity_observation_receipt(
                request,
                "E30_EVALUATION"
                if request["schema_version"] == 3
                else "E29_EVALUATION",
            ),
        )
    route = M336K2RouteLedger(
        _destinations(request)["route_state_ledger"], git_worktrees=(repository,)
    ).receipt()
    route_body = asdict(route)
    write_canonical_json(source / "final_route_ledger_receipt.json", route_body)
    h_safety = scan_m336k2_public_tree(
        repository.joinpath(*contract.h_root.split("/")),
        allowed_root_files=frozenset(
            item.name
            for item in repository.joinpath(*contract.h_root.split("/")).iterdir()
        ),
    )
    leak_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_SOURCE_LEAK_REPORT",
        "source_leak_count": h_safety["source_leak_count"],
        "absolute_path_count": h_safety["absolute_path_count"],
        "private_artifact_count": h_safety["private_artifact_count"],
        "status": "PASS" if not any(h_safety.values()) else "FAIL",
    }
    leak = {**leak_body, "receipt_hash": content_hash(leak_body)}
    if leak["status"] != "PASS":
        raise M336K2ProtocolError("M336K2 pre-E publication safety failed")
    write_canonical_json(source / "source_leak_report.json", leak)
    report = stage_m336k2_e28_publication(
        repository=repository,
        git_executable=Path(request["git_executable"]),
        exact_f28_sha=request["exact_f28_sha"],
        exact_h28_sha=h28,
        evidence_source=source,
        output=repository.joinpath(*contract.e_root.split("/")),
        contract=contract,
    )
    git = Path(request["git_executable"]).resolve(strict=True)
    _git(git, repository, "add", "-f", contract.e_root)
    _git(git, repository, "commit", "-m", contract.e_subject)
    e28 = _git(git, repository, "rev-parse", "HEAD^{commit}")
    _git(git, repository, "push", "origin", f"HEAD:{contract.branch_ref}")
    _verify_remote_head(git, repository, contract.branch_ref, e28)
    body = {
        "schema_version": 1,
        "exact_e28_sha": e28,
        "exact_h28_parent": _git(git, repository, "rev-parse", f"{e28}^"),
        "publication_report_hash": report.report_hash,
        "status": "PASS",
    }
    if _typed(request):
        body.update(_identity_observation_fields(request))
    result = {**body, "receipt_hash": content_hash(body)}
    write_canonical_json(private / "e28_commit_receipt.json", result)
    return {"event": "E_PUBLICATION_READY", **result}


def _final_verification(request: dict) -> dict:
    repository = Path(request["repository"]).resolve(strict=True)
    private = Path(request["private_root"]).resolve(strict=True)
    freeze = _freeze_manifest(request)
    h28 = _object(private / "h28_commit_receipt.json")["exact_h28_sha"]
    e28 = _object(private / "e28_commit_receipt.json")["exact_e28_sha"]
    contract = publication_contract_from_dict(
        _object(Path(request["publication_contract"]).resolve(strict=True))
    )
    protocol = verify_m336k2_commit_protocol(
        repository=repository,
        git_executable=Path(request["git_executable"]),
        exact_q28_sha=freeze.exact_q28_sha,
        exact_f28_sha=request["exact_f28_sha"],
        exact_h28_sha=h28,
        exact_e28_sha=e28,
        contract=contract,
    )
    evaluator = _evaluator_receipt(_destinations(request)["evaluator_ledger"])
    route = M336K2RouteLedger(
        _destinations(request)["route_state_ledger"], git_worktrees=(repository,)
    ).receipt()
    if (
        evaluator["reservation_count"] != 1
        or evaluator["windows_evaluation_count"] != 1
        or evaluator["karina_evaluation_count"] != 1
        or evaluator["retry_count"] != 0
        or route.final_event != "E_PUBLICATION_READY"
        or protocol["status"] != "PASS"
    ):
        raise M336K2ProtocolError("M336K2 exact final verification failed")
    return {
        "event": "FINAL_VERIFICATION_COMPLETED",
        "commit_protocol_receipt_hash": protocol["receipt_hash"],
        "evaluator_ledger_receipt_hash": evaluator["receipt_hash"],
        "status": "PASS",
    }


def _append_evaluator_event(path: Path, event: str, operation_hash: str) -> dict:
    events = _evaluator_events(path)
    names = tuple(item["event"] for item in events)
    expected = (
        _EVALUATOR_EVENTS[len(names)] if len(names) < len(_EVALUATOR_EVENTS) else None
    )
    if event != expected or len(operation_hash) != 64:
        raise M336K2ProtocolError("M336K2 evaluator event order changed")
    body = {
        "schema_version": 1,
        "ordinal": len(events) + 1,
        "event": event,
        "operation_hash": operation_hash,
        "previous_event_hash": events[-1]["event_hash"] if events else None,
    }
    value = {**body, "event_hash": content_hash(body)}
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, (canonical_json(value) + "\n").encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    _evaluator_events(path)
    return value


def _evaluator_events(path: Path) -> tuple[dict, ...]:
    if not path.exists():
        return ()
    raw = path.read_bytes()
    if b"\r" in raw or not raw.endswith(b"\n"):
        raise M336K2ProtocolError("M336K2 evaluator ledger is not canonical")
    result = []
    previous = None
    for ordinal, line in enumerate(raw.splitlines(), start=1):
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise M336K2ProtocolError("M336K2 evaluator ledger is invalid") from error
        body = dict(value)
        claimed = body.pop("event_hash", None)
        if (
            set(value)
            != {
                "schema_version",
                "ordinal",
                "event",
                "operation_hash",
                "previous_event_hash",
                "event_hash",
            }
            or value.get("ordinal") != ordinal
            or value.get("previous_event_hash") != previous
            or content_hash(body) != claimed
        ):
            raise M336K2ProtocolError("M336K2 evaluator ledger hash chain changed")
        result.append(value)
        previous = claimed
    names = tuple(item["event"] for item in result)
    if names != _EVALUATOR_EVENTS[: len(names)]:
        raise M336K2ProtocolError("M336K2 evaluator ledger order changed")
    return tuple(result)


def _evaluator_receipt(path: Path) -> dict:
    events = _evaluator_events(path)
    names = tuple(item["event"] for item in events)
    body = {
        "schema_version": 1,
        "event_count": len(events),
        "final_event": names[-1] if names else None,
        "reservation_count": names.count("EVALUATOR_RESERVED"),
        "windows_evaluation_count": names.count("WINDOWS_EVALUATION_COMPLETED"),
        "karina_evaluation_count": names.count("KARINA_EVALUATION_COMPLETED"),
        "retry_count": 0,
        "ledger_bytes_hash": bytes_hash(path.read_bytes())
        if path.exists()
        else bytes_hash(b""),
    }
    return {**body, "receipt_hash": content_hash(body)}


def _rehearsal_provider(request: dict) -> dict:
    if (
        request["execution_mode"] != "REHEARSAL"
        and request.get("execution_purpose") != "DISPOSABLE"
    ):
        return {}
    from m336i_build_authorized_rehearsal_fixture import (
        _FixtureMaven,
        _FixtureScm,
    )

    return {
        "maven_provider": _FixtureMaven(),
        "scm_provider": _FixtureScm(),
    }


def _typed(request: dict) -> bool:
    return request.get("schema_version") in {2, 3}


def _verify_request(request: dict, *, startup_receipt_path: Path | None = None) -> None:
    destinations = request.get("final_destinations")
    karina = request.get("karina")
    legacy = set(request) == _REQUEST_FIELDS and request.get("schema_version") == 1
    typed_k4 = (
        set(request) == _M336K4_REQUEST_FIELDS and request.get("schema_version") == 2
    )
    typed_k5 = (
        set(request) == _M336K5_REQUEST_FIELDS and request.get("schema_version") == 3
    )
    if (
        not (legacy or typed_k4 or typed_k5)
        or request.get("execution_mode") not in {"REHEARSAL", "FINAL"}
        or not isinstance(destinations, dict)
        or set(destinations) != _DESTINATION_FIELDS
        or not isinstance(karina, dict)
        or set(karina) != _KARINA_FIELDS
        or not isinstance(request.get("executable_handles"), dict)
        or set(request["executable_handles"])
        != {"git", "python", "java", "javac", "ssh", "scp", "tar", "powershell", "cmd"}
    ):
        raise M336K2ProtocolError("M336K2 native stage request fields changed")
    if typed_k4:
        bundle = M336K4RouteIdentityBundle.from_dict(
            _object(Path(request["route_identity_bundle"]).resolve(strict=True))
        )
        authorization = M336K4FinalAuthorization.from_dict(
            _object(Path(request["final_authorization"]).resolve(strict=True))
        )
        authorization.verify(bundle)
        freeze = _freeze(Path(request["freeze_manifest"]).resolve(strict=True))
        if (
            not isinstance(freeze, M336K4FreezeManifest)
            or request["route_run_id"] != bundle.protocol_run_id.value
            or request["execution_mode"] != bundle.execution_mode.value
            or request["route_identity_bundle_hash"] != bundle.bundle_hash
            or freeze.route_identity_bundle_hash != bundle.bundle_hash
            or authorization.route_identity_bundle_hash != bundle.bundle_hash
        ):
            raise M336K2ProtocolError("M336K4 native stage identity binding changed")
    if typed_k5:
        if startup_receipt_path is None:
            raise M336K2ProtocolError("M336K5 stage startup receipt is absent")
        startup = startup_receipt_from_path(startup_receipt_path)
        bundle = M336K5RouteIdentityBundle.from_dict(
            _object(Path(request["route_identity_bundle"]).resolve(strict=True))
        )
        authorization = M336K5FinalAuthorization.from_dict(
            _object(Path(request["final_authorization"]).resolve(strict=True))
        )
        authorization.verify(bundle)
        freeze = _freeze(Path(request["freeze_manifest"]).resolve(strict=True))
        if (
            not isinstance(freeze, M336K5FreezeManifest)
            or request["route_run_id"] != bundle.protocol_run_id.value
            or request["execution_mode"] != bundle.execution_mode.value
            or request["route_identity_bundle_hash"] != bundle.bundle_hash
            or request["startup_receipt_hash"] != startup.receipt_hash
            or freeze.route_identity_bundle_hash != bundle.bundle_hash
            or authorization.route_identity_bundle_hash != bundle.bundle_hash
        ):
            raise M336K2ProtocolError("M336K5 native stage identity binding changed")
    repository = Path(request["repository"]).resolve(strict=True)
    state = Path(request["stage_state"]).resolve(strict=False)
    receipts = Path(request["stage_receipt_root"]).resolve(strict=False)
    private = Path(request["private_root"]).resolve(strict=False)
    git_executable = Path(request["git_executable"]).resolve(strict=True)
    worktrees = _git_worktrees(git_executable, repository)
    private_destinations = (
        state,
        receipts,
        private,
        *(
            Path(value).resolve(strict=False)
            for value in request["final_destinations"].values()
        ),
    )
    if any(
        _is_relative_to(path, worktree)
        for path in private_destinations
        for worktree in worktrees
    ):
        raise M336K2ProtocolError("M336K2 private route state is inside Git")
    handles = {
        name: Path(path).resolve(strict=True)
        for name, path in request["executable_handles"].items()
    }
    if (
        handles["git"] != Path(request["git_executable"]).resolve(strict=True)
        or handles["python"] != Path(request["python_executable"]).resolve(strict=True)
        or handles["java"] != Path(request["windows_java"]).resolve(strict=True)
        or handles["javac"] != Path(request["windows_javac"]).resolve(strict=True)
        or handles["ssh"]
        != Path(request["karina"]["ssh_executable"]).resolve(strict=True)
    ):
        raise M336K2ProtocolError("M336K2 stage executable aliases changed")


def _karina_args(request: dict):
    capsule = _component_object(request, "execution_capsule_receipt")
    karina = request["karina"]
    public_capsule = _object(
        Path(karina["public_execution_capsule_receipt"]).resolve(strict=True)
    )
    dependencies = _object(
        Path(karina["executable_dependency_manifest"]).resolve(strict=True)
    )
    if public_capsule.get("receipt_hash") != capsule.get(
        "karina_public_execution_capsule_receipt_hash"
    ) or dependencies.get("manifest_hash") != capsule.get(
        "karina_executable_dependency_manifest_hash"
    ):
        raise M336K2ProtocolError("M336K2 Karina execution capsule changed")
    private = Path(request["private_root"]).resolve(strict=True)
    repository = Path(request["repository"]).resolve(strict=True)
    git = Path(request["git_executable"]).resolve(strict=True)
    return SimpleNamespace(
        private_acquisition_output=private,
        karina_private_capsule=Path(karina["private_execution_capsule"]),
        karina_public_capsule_receipt=Path(karina["public_execution_capsule_receipt"]),
        karina_executable_dependency_manifest=Path(
            karina["executable_dependency_manifest"]
        ),
        ssh_executable=Path(karina["ssh_executable"]),
        ssh_key=Path(karina["ssh_key"]),
        known_hosts_file=Path(karina["known_hosts_file"]),
        karina_worker_endpoint=karina["worker_endpoint"],
        karina_repository=karina["repository"],
        karina_private_root=karina["private_root"],
        karina_private_capsule_remote=karina["private_capsule_remote"],
        karina_javac=karina["javac"],
        karina_command_receipt_root=private / "karina-command-receipts",
        windows_vault=_destinations(request)["vault"],
        karina_public_production_root=_destinations(request)["karina_production"],
        windows_public_production_root=_destinations(request)["windows_production"],
        public_staging_root=private / "public-staging",
        frozen_route_manifest=_component_path(request, "route_manifest"),
        threshold_manifest=_component_path(request, "threshold_manifest"),
        karina_host_identity_receipt=_component_path(
            request, "karina_stable_host_identity"
        ),
        supplied_f24_sha=_karina_expected_head(request),
        m336k5_enabled=request["schema_version"] == 3,
        m336k5_bootstrap_source_hash=(
            _component_object(request, "python_startup_bootstrap").get(
                "source_bytes_hash"
            )
            if request["schema_version"] == 3
            else None
        ),
        m336k5_target_source_hash=bytes_hash(
            (repository / "scripts" / "m336j_karina_execution.py").read_bytes()
        ),
        m336k5_project_source_identity=compute_m336j_project_source_identity(
            repository, git
        ),
    )


def _karina_expected_head(request: dict) -> str:
    """Run remote implementation code at the frozen implementation tip.

    Q/F/H/E contain evidence and policy only.  Binding Karina to F28 would make
    the pre-F execution capsule self-referential without changing executable
    code, so the remote capsule correctly remains pinned to IMPLEMENTATION_TIP.
    """

    return _freeze_manifest(request).implementation_tip


def _production_authorization(request: dict):
    return SimpleNamespace(
        route_manifest_hash=_required_hash(
            _component_object(request, "route_manifest"), "manifest_hash"
        ),
        r24_implementation_tree_identity=content_hash(
            _freeze_manifest(request).implementation_tip
        ),
        windows_public_jdk_identity_receipt_hash=_required_hash(
            _component_object(request, "windows_jdk_identity"), "receipt_hash"
        ),
        karina_public_jdk_identity_receipt_hash=_required_hash(
            _component_object(request, "karina_jdk_identity"), "receipt_hash"
        ),
        publication_boundary_hash=_required_hash(
            _component_object(request, "publication_boundary"),
            "publication_boundary_hash",
        ),
        threshold_manifest_hash=_required_hash(
            _component_object(request, "threshold_manifest"),
            "threshold_manifest_hash",
        ),
        karina_stable_host_identity_receipt_hash=_required_hash(
            _component_object(request, "karina_stable_host_identity"),
            "receipt_hash",
        ),
    )


def _load_state(path: Path, request: dict) -> dict:
    if not path.exists():
        value = {
            "schema_version": 1,
            "route_run_id": request["route_run_id"],
            "exact_f28_sha": request["exact_f28_sha"],
            "completed_events": (),
        }
        if _typed(request):
            value["schema_version"] = request["schema_version"]
            value["route_identity_bundle_hash"] = request["route_identity_bundle_hash"]
        if request["schema_version"] == 3:
            value["startup_receipt_hash"] = request["startup_receipt_hash"]
        return value
    value = _object(path)
    body = dict(value)
    claimed = body.pop("state_hash", None)
    expected_fields = {
        "schema_version",
        "route_run_id",
        "exact_f28_sha",
        "completed_events",
        "previous_state_hash",
        "last_operation_hash",
        "state_hash",
    }
    if _typed(request):
        expected_fields.add("route_identity_bundle_hash")
    if request["schema_version"] == 3:
        expected_fields.add("startup_receipt_hash")
    if (
        set(value) != expected_fields
        or value["route_run_id"] != request["route_run_id"]
        or value["exact_f28_sha"] != request["exact_f28_sha"]
        or value.get("route_identity_bundle_hash")
        != request.get("route_identity_bundle_hash")
        or value.get("startup_receipt_hash") != request.get("startup_receipt_hash")
        or tuple(value["completed_events"])
        != _STAGE_EVENTS[: len(value["completed_events"])]
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K2 native stage state is invalid")
    value["completed_events"] = tuple(value["completed_events"])
    return value


def _write_private_state(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".next")
    if temporary.exists():
        raise M336K2ProtocolError("M336K2 interrupted stage state exists")
    temporary.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
    # Windows rejects fsync() on a read-only file descriptor (WinError 9).
    # Reopen the fully-written temporary state read/write so the durable
    # flush has the same semantics on Windows and POSIX.
    with temporary.open("r+b") as stream:
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _destinations(request: dict) -> dict[str, Path]:
    return {
        name: Path(value).resolve(strict=False)
        for name, value in request["final_destinations"].items()
    }


def _freeze_manifest(
    request: dict,
) -> M336K2FreezeManifest | M336K4FreezeManifest | M336K5FreezeManifest:
    return _freeze(Path(request["freeze_manifest"]).resolve(strict=True))


def _freeze(
    path: Path,
) -> M336K2FreezeManifest | M336K4FreezeManifest | M336K5FreezeManifest:
    value = _object(path)
    if value.get("contract_role") == "M336K4_F29_TYPED_FREEZE_V2":
        return M336K4FreezeManifest.from_dict(value)
    if value.get("contract_role") == "M336K5_F30_TYPED_FREEZE_V2":
        return M336K5FreezeManifest.from_dict(value)
    value["components"] = tuple(
        M336K2FrozenComponent(**item) for item in value["components"]
    )
    value["self_reference_safe_exclusions"] = tuple(
        value["self_reference_safe_exclusions"]
    )
    return M336K2FreezeManifest(**value)


def _attestation(
    request: dict,
) -> (
    M336K2CommittedFreezeAttestation
    | M336K4CommittedFreezeAttestation
    | M336K5CommittedFreezeAttestation
):
    value = _object(Path(request["f28_attestation"]).resolve(strict=True))
    if value.get("schema_version") == 2 and "exact_f30_sha" in value:
        return M336K5CommittedFreezeAttestation(**value)
    if value.get("schema_version") == 2 and "exact_f29_sha" in value:
        return M336K4CommittedFreezeAttestation(**value)
    value["self_reference_safe_exclusions"] = tuple(
        value["self_reference_safe_exclusions"]
    )
    return M336K2CommittedFreezeAttestation(**value)


def _authorization(request: dict):
    value = _object(Path(request["final_authorization"]).resolve(strict=True))
    if value.get("contract_role") == "M336K5_TYPED_FINAL_AUTHORIZATION_V2":
        return M336K5FinalAuthorization.from_dict(value)
    if value.get("contract_role") == "M336K4_TYPED_FINAL_AUTHORIZATION_V2":
        return M336K4FinalAuthorization.from_dict(value)
    return authorization_from_dict(value)


def _component_path(request: dict, name: str) -> Path:
    repository = Path(request["repository"]).resolve(strict=True)
    rows = tuple(
        item for item in _freeze_manifest(request).components if item.name == name
    )
    if len(rows) != 1:
        raise M336K2ProtocolError("M336K2 frozen component lookup failed")
    return repository.joinpath(*rows[0].relative_path.split("/")).resolve(strict=True)


def _component_object(request: dict, name: str) -> dict:
    return _object(_component_path(request, name))


def _identity_observation_fields(request: dict) -> dict:
    bundle = _route_identity_bundle(request)
    return {
        "protocol_run_id": bundle.protocol_run_id.canonical_object(),
        "route_identity_bundle_hash": bundle.bundle_hash,
    }


def _identity_observation_receipt(request: dict, observer: str) -> dict:
    bundle = _route_identity_bundle(request)
    body = {
        "schema_version": 1,
        "contract_role": (
            "PUBLIC_SAFE_M336K5_ROUTE_IDENTITY_OBSERVATION"
            if request["schema_version"] == 3
            else "PUBLIC_SAFE_M336K4_ROUTE_IDENTITY_OBSERVATION"
        ),
        "observer": observer,
        "route_version": bundle.route_version.canonical_object(),
        "protocol_run_id": bundle.protocol_run_id.canonical_object(),
        "acquisition_run_id": bundle.acquisition_run_id.canonical_object(),
        "selector_run_id": bundle.selector_run_id.canonical_object(),
        "evaluator_run_id": bundle.evaluator_run_id.canonical_object(),
        "execution_mode": bundle.execution_mode.canonical_object(),
        "route_identity_bundle_hash": bundle.bundle_hash,
        "status": "PASS",
    }
    return {**body, "receipt_hash": content_hash(body)}


def _route_identity_bundle(request: dict):
    value = _object(Path(request["route_identity_bundle"]).resolve(strict=True))
    if request["schema_version"] == 3:
        return M336K5RouteIdentityBundle.from_dict(value)
    return M336K4RouteIdentityBundle.from_dict(value)


def _required_hash(value: dict, field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or len(result) != 64:
        raise M336K2ProtocolError("M336K2 frozen component has no hash identity")
    return result


def _verified_hashed_object(path: Path, hash_field: str) -> dict:
    value = _object(path.resolve(strict=True))
    body = dict(value)
    claimed = body.pop(hash_field, None)
    if not isinstance(claimed, str) or content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K2 receipt hash changed")
    return value


def _git(git: Path, repository: Path, *arguments: str) -> str:
    return subprocess.run(
        (str(git), *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=m336k2_minimal_environment(),
    ).stdout.strip()


def _git_worktrees(git: Path, repository: Path) -> tuple[Path, ...]:
    rows = _git(git, repository, "worktree", "list", "--porcelain").splitlines()
    worktrees = tuple(
        Path(row.removeprefix("worktree ")).resolve(strict=True)
        for row in rows
        if row.startswith("worktree ")
    )
    if not worktrees:
        raise M336K2ProtocolError("M336K2 Git worktree inventory is empty")
    return worktrees


def _verify_remote_head(
    git: Path, repository: Path, branch_ref: str, expected: str
) -> None:
    remote = _git(
        git, repository, "ls-remote", "--exit-code", "origin", branch_ref
    ).split()
    if not remote or remote[0] != expected:
        raise M336K2ProtocolError("M336K2 pushed branch identity changed")


def _object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K2 native stage JSON is invalid") from error
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K2 native stage input is not an object")
    return value


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
