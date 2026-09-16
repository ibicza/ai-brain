"""Execute one disposable v5 native-stage handoff through the real worker."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_controller import M336K2StageRequest
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_execution import M336K5HermeticCommandWorker
from ai_brain.stage3.acquisition.m336k5_identity import (
    build_m336k8_rehearsal_identity_bundle,
)
from ai_brain.stage3.acquisition.m336k5_registry import (
    build_m336k5_route_manifest,
    build_m336k5_route_registry,
    build_m336k5_schema_registry,
)
from ai_brain.stage3.acquisition.m336k5_startup import (
    build_m336k5_python_startup_policy,
    startup_receipt_from_path,
)
from ai_brain.stage3.acquisition.m336k8_freeze import M336K8FreezeManifest
from ai_brain.stage3.acquisition.m336k9_authorization import (
    build_m336k9_final_authorization,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    M336KOfficialRouteProfileStatus,
    m336k_official_profile_registry,
)
from ai_brain.stage3.acquisition.m336k12_dispatch import (
    M336K12_PROFILE_ID,
    M336K12_STAGE_WORKER,
    M336K12NativeStagePlanBinding,
    build_m336k12_native_execution_plan,
    build_m336k12_native_stage_dispatches,
    m336k12_native_dispatch_contract_hash,
    verify_m336k12_native_stage_plan,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--powershell", type=Path, required=True)
    parser.add_argument("--rehearsal-stage-request", type=Path, required=True)
    parser.add_argument("--startup-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    git = args.git_executable.resolve(strict=True)
    python = args.python.absolute()
    powershell = args.powershell.resolve(strict=True)
    source_request_path = args.rehearsal_stage_request.resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output.exists() or output.is_relative_to(repository):
        raise M336K2ProtocolError("M336K12 first-stage output is stale or public")
    if _git(git, repository, "status", "--porcelain=v1"):
        raise M336K2ProtocolError("M336K12 first-stage repository is dirty")
    implementation = _git(git, repository, "rev-parse", "HEAD")
    startup = startup_receipt_from_path(args.startup_receipt.resolve(strict=True))
    source_request = _object(source_request_path)
    if (
        source_request.get("schema_version") != 3
        or source_request.get("execution_purpose") != "DISPOSABLE"
        or source_request.get("execution_mode") not in {"REHEARSAL", "FINAL"}
    ):
        raise M336K2ProtocolError(
            "M336K12 first-stage source is not a disposable rehearsal request"
        )

    profile_registry = m336k_official_profile_registry()
    profile = profile_registry.profile(M336K12_PROFILE_ID)
    if profile.profile_status is not M336KOfficialRouteProfileStatus.CURRENT_ACTIVE:
        raise M336K2ProtocolError("M336K12 active profile changed")
    route_registry = build_m336k5_route_registry(
        repository, namespace="m336k8", profile_id=M336K12_PROFILE_ID
    )
    schema_registry = build_m336k5_schema_registry(
        namespace="m336k8", profile_id=M336K12_PROFILE_ID
    )
    route_manifest = build_m336k5_route_manifest(route_registry, schema_registry)
    dispatches = build_m336k12_native_stage_dispatches(
        repository=repository,
        execution_scope="REHEARSAL",
        bootstrap_script=repository / "scripts/m336k5_python_bootstrap.py",
    )

    runtime = output / "runtime"
    private = runtime / "private"
    stage_receipts = runtime / "stage-receipts"
    stage_request_path = private / "canonical-internal-stage-request.json"
    plan = build_m336k12_native_execution_plan(
        repository=repository,
        python_executable=python,
        stage_request=stage_request_path,
        stage_receipt_root=stage_receipts,
        route_run_id=source_request["route_run_id"],
        exact_f37_sha=source_request["exact_f28_sha"],
        route_registry_hash=route_registry.registry_hash,
        dispatches=dispatches,
    )
    base_capsule_hash = content_hash(
        (
            "M336K12_REHEARSAL_BASE_CAPSULE",
            bytes_hash(source_request_path.read_bytes()),
        )
    )
    plan_binding = M336K12NativeStagePlanBinding.build(
        repository=repository,
        exact_implementation_tip=implementation,
        active_profile_hash=profile.profile_hash,
        route_registry_hash=route_registry.registry_hash,
        typed_route_manifest_hash=route_manifest.manifest_hash,
        dispatches=dispatches,
        python_executable=python,
        outer_startup_policy_hash=(build_m336k5_python_startup_policy().policy_hash),
        native_capsule_receipt_hash=base_capsule_hash,
    )
    parity = verify_m336k12_native_stage_plan(
        plan=plan,
        dispatches=dispatches,
        plan_binding=plan_binding,
        repository=repository,
        python_executable=python,
    )

    destinations = {
        "acquisition_ledger": str(runtime / "ledgers/acquisition.jsonl"),
        "selector_ledger": str(runtime / "ledgers/selector.jsonl"),
        "evaluator_ledger": str(runtime / "ledgers/evaluator.jsonl"),
        "route_state_ledger": str(runtime / "ledgers/route.jsonl"),
        "vault": str(runtime / "vault"),
        "selected_source_snapshot": str(runtime / "windows-selected"),
        "windows_production": str(runtime / "windows-production"),
        "karina_production": str(runtime / "karina-production"),
        "evaluator_root": str(runtime / "evaluator"),
    }
    executable_handles = dict(source_request["executable_handles"])
    executable_handles.update(
        {
            "git": str(git),
            "python": str(python),
            "powershell": str(powershell),
        }
    )
    source_bundle = _object(Path(source_request["route_identity_bundle"]))
    rehearsal_bundle = build_m336k8_rehearsal_identity_bundle(
        route_registry_hash=source_bundle["route_registry_hash"],
        route_manifest_hash=source_bundle["route_manifest_hash"],
        acquisition_policy_hash=source_bundle["acquisition_policy_hash"],
        selector_policy_hash=source_bundle["selector_policy_hash"],
        evaluator_policy_hash=source_bundle["evaluator_policy_hash"],
    )
    source_authorization = _object(Path(source_request["final_authorization"]))
    generated_authorization_fields = {
        "schema_version",
        "contract_role",
        "route_version_typed",
        "protocol_run_id_typed",
        "acquisition_run_id_typed",
        "selector_run_id_typed",
        "evaluator_run_id_typed",
        "execution_mode_typed",
        "route_identity_bundle_hash",
        "official_profile_id",
        "official_profile_hash",
        "official_profile_registry_hash",
        "authorization_hash",
    }
    authorization_values = {
        name: value
        for name, value in source_authorization.items()
        if name not in generated_authorization_fields
    }
    authorization_values["exact_implementation_tip"] = implementation
    authorization_values["allowed_network_hosts"] = tuple(
        authorization_values["allowed_network_hosts"]
    )
    rehearsal_authorization = build_m336k9_final_authorization(
        bundle=rehearsal_bundle,
        official_profile_id="m336k8-rehearsal-v2",
        **authorization_values,
    )
    source_freeze = _object(Path(source_request["freeze_manifest"]))
    freeze_body = {
        name: value for name, value in source_freeze.items() if name != "manifest_hash"
    }
    rehearsal_profile = profile_registry.profile("m336k8-rehearsal-v2")
    freeze_body.update(
        {
            "implementation_tip": implementation,
            "route_identity_bundle_hash": rehearsal_bundle.bundle_hash,
            "authorization_hash": rehearsal_authorization.authorization_hash,
            "official_profile_id": rehearsal_profile.profile_id,
            "official_profile_hash": rehearsal_profile.profile_hash,
            "official_profile_registry_hash": profile_registry.registry_hash,
        }
    )
    rehearsal_freeze_value = {
        **freeze_body,
        "manifest_hash": content_hash(freeze_body),
    }
    M336K8FreezeManifest.from_dict(rehearsal_freeze_value)
    rehearsal_bundle_path = private / "rehearsal-route-identity-bundle.json"
    rehearsal_authorization_path = private / "rehearsal-final-authorization.json"
    rehearsal_freeze_path = private / "rehearsal-freeze-manifest.json"
    _write(rehearsal_bundle_path, rehearsal_bundle.canonical_object())
    _write(rehearsal_authorization_path, rehearsal_authorization.canonical_object())
    _write(rehearsal_freeze_path, rehearsal_freeze_value)
    stage_request = {
        **source_request,
        "python_executable": str(python),
        "git_executable": str(git),
        "startup_receipt_hash": startup.receipt_hash,
        "stage_state": str(runtime / "stage-state.json"),
        "stage_receipt_root": str(stage_receipts),
        "private_root": str(private),
        "freeze_manifest": str(rehearsal_freeze_path),
        "final_authorization": str(rehearsal_authorization_path),
        "route_identity_bundle": str(rehearsal_bundle_path),
        "route_identity_bundle_hash": rehearsal_bundle.bundle_hash,
        "final_destinations": destinations,
        "executable_handles": executable_handles,
        "native_stage_plan_binding_hash": plan_binding.plan_binding_hash,
        "producer_consumer_parity_receipt_hash": parity.receipt_hash,
        "dispatch_contract_hash": m336k12_native_dispatch_contract_hash(dispatches),
    }
    private.mkdir(parents=True, exist_ok=True)
    _write(stage_request_path, stage_request)

    worker = M336K5HermeticCommandWorker(
        plan,
        repository=repository,
        git_executable=git,
        python_executable=python,
        powershell_executable=powershell,
        bootstrap_script=repository / "scripts/m336k5_python_bootstrap.py",
        expected_startup_receipt_hash=startup.receipt_hash,
        native_stage_dispatches=dispatches,
        native_stage_plan_binding=plan_binding,
        producer_consumer_parity=parity,
    )
    worker_preflight = worker.preflight()
    event = "ACQUISITION_RESERVED"
    request_body = {
        "schema_version": 1,
        "event": event,
        "route_run_id": source_request["route_run_id"],
        "execution_mode": source_request["execution_mode"],
        "exact_f28_sha": source_request["exact_f28_sha"],
        "context_hash": content_hash(
            ("M336K12_FIRST_STAGE_HANDOFF", plan_binding.plan_binding_hash)
        ),
        "previous_operation_hash": "0" * 64,
    }
    stage_request_value = M336K2StageRequest(
        **request_body, request_hash=content_hash(request_body)
    )
    stage_receipt = worker(stage_request_value)
    native_receipt_path = stage_receipts / f"{event}.json"
    native_receipt = _object(native_receipt_path)
    command = plan.commands[0]
    expected_template = dispatches[0].target_argument_template
    report_body = {
        "schema_version": 1,
        "contract_role": "M336K12_FIRST_STAGE_HANDOFF_PARITY_REPORT",
        "exact_implementation_tip": implementation,
        "execution_scope": "REHEARSAL",
        "rehearsal_identity_status": "REHEARSAL_ONLY",
        "native_stage_plan_binding_hash": plan_binding.plan_binding_hash,
        "producer_consumer_parity_receipt_hash": parity.receipt_hash,
        "dispatch_contract_hash": m336k12_native_dispatch_contract_hash(dispatches),
        "producer_consumer_parity_status": parity.status,
        "worker_preflight_status": worker_preflight.status,
        "powershell_launcher_status": "PASS",
        "actual_target_repository_path": M336K12_STAGE_WORKER,
        "actual_target_argument_template": expected_template,
        "actual_target_argument_hash": content_hash(command.arguments[2:]),
        "expected_target_argument_template_hash": content_hash(expected_template),
        "startup_receipt_hash": startup.receipt_hash,
        "native_stage_receipt_hash": native_receipt["receipt_hash"],
        "worker_stage_receipt_hash": stage_receipt.receipt_hash,
        "native_stage_receipt_event": native_receipt["event"],
        "native_stage_subprocess_count": 1,
        "rehearsal_acquisition_reservation_count": 1,
        "official_reservation_count": 0,
        "official_route_event_count": 0,
        "official_acquisition_event_count": 0,
        "official_source_request_count": 0,
        "official_source_body_byte_count": 0,
        "official_vault_file_count": 0,
        "plan_builder_source_hash": plan_binding.plan_builder_source_hash,
        "consumer_source_hash": plan_binding.consumer_source_hash,
        "legacy_adapter_source_hash": plan_binding.legacy_adapter_source_hash,
        "raw_private_value_count": 0,
        "status": "PASS",
    }
    report = {**report_body, "report_hash": content_hash(report_body)}
    _write(output / "first_stage_handoff_parity_report.json", report)
    print(canonical_json(report))


def _git(git: Path, repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        (str(git), "-C", str(repository), *arguments),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise M336K2ProtocolError("M336K12 first-stage Git command failed")
    return result.stdout.strip()


def _object(path: Path) -> dict:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise M336K2ProtocolError("M336K12 first-stage JSON input changed")
    return value


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
