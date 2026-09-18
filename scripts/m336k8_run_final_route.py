"""Validate or execute the canonical M-33.6k.8 final route."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_execution import (
    build_m336k2_native_execution_plan,
    executable_dependency_manifest_from_dict,
    execution_capsule_receipt_from_dict,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ProtocolError,
    M336K2RouteLedger,
)
from ai_brain.stage3.acquisition.m336k5_controller import (
    M336K5IdentityCheckingWorker,
    run_m336k5_final_controller,
    verify_m336k5_route_ledger_identity,
)
from ai_brain.stage3.acquisition.m336k5_execution import M336K5HermeticCommandWorker
from ai_brain.stage3.acquisition.m336k5_resources import (
    M336K5ResourceMonitor,
    release_m336k5_storage_reservation,
)
from ai_brain.stage3.acquisition.m336k7_contracts import (
    M336K7StorageReservationReleaseReceipt,
)
from ai_brain.stage3.acquisition.m336k7_request import (
    verify_m336k7_released_resource_state,
    verify_m336k7_reservation_release,
)
from ai_brain.stage3.acquisition.m336k8_contracts import (
    require_m336k8_execution_authority,
)
from ai_brain.stage3.acquisition.m336k8_request import (
    build_m336k8_internal_stage_request,
    load_m336k8_preledger_receipt,
    validate_m336k8_final_invocation,
)
from ai_brain.stage3.acquisition.m336k11_execution import (
    M336K11EffectiveEnvironmentBinding,
    M336K11HermeticExecutableDependencyManifest,
    M336K11NativeExecutionCapsuleReceipt,
    build_m336k11_native_execution_plan,
)
from ai_brain.stage3.acquisition.m336k12_dispatch import (
    M336K12DisposableDispatchClosure,
    M336K12NativeStageDispatch,
    build_m336k12_native_execution_plan,
    verify_m336k12_native_stage_plan,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--validation-receipt", type=Path)
    parser.add_argument("--startup-receipt", type=Path, required=True)
    parser.add_argument("--post-freeze-validation-receipt", type=Path)
    parser.add_argument("--reservation-release-receipt", type=Path)
    parser.add_argument("--native-dispatch-rehearsal", type=Path)
    args = parser.parse_args()
    request_path = args.request.resolve(strict=True)
    startup_receipt_path = args.startup_receipt.resolve(strict=True)
    if args.validate_only:
        if (
            args.post_freeze_validation_receipt is not None
            or args.reservation_release_receipt is not None
        ):
            raise M336K2ProtocolError(
                "M336K8 validate-only release inputs are forbidden"
            )
        validated = validate_m336k8_final_invocation(
            request_path, startup_receipt_path=startup_receipt_path
        )
        rehearsal_closure = _load_rehearsal_dispatch_closure(
            args.native_dispatch_rehearsal,
            validated=validated,
        )
    else:
        if (
            args.post_freeze_validation_receipt is None
            or args.reservation_release_receipt is None
        ):
            raise M336K2ProtocolError("M336K8 execution release inputs are absent")
        release_path = args.reservation_release_receipt.resolve(strict=False)
        if release_path.exists():
            raise M336K2ProtocolError("M336K8 reservation release output is stale")
        release_path.parent.mkdir(parents=True, exist_ok=True)
        _claim_execution_lock(release_path, request_path)
        prior = load_m336k8_preledger_receipt(
            args.post_freeze_validation_receipt.resolve(strict=True)
        )
        validated = validate_m336k8_final_invocation(
            request_path, startup_receipt_path=startup_receipt_path
        )
        if validated.receipt != prior:
            raise M336K2ProtocolError(
                "M336K8 execution differs from post-freeze validation"
            )
        rehearsal_closure = _load_rehearsal_dispatch_closure(
            args.native_dispatch_rehearsal,
            validated=validated,
        )
        if validated.request.purpose == "QUALIFICATION":
            raise M336K2ProtocolError("M336K8 qualification request is not executable")
        require_m336k8_execution_authority(
            post_freeze_validation_accepted=True,
            operation="RELEASE_STORAGE_RESERVATION",
        )
        reservation_file = Path(validated.request.storage_reservation_file).resolve(
            strict=True
        )
        free_before = shutil.disk_usage(reservation_file.parent).free
        release_m336k5_storage_reservation(reservation_file)
        free_after = shutil.disk_usage(reservation_file.parent).free
        release = M336K7StorageReservationReleaseReceipt.build(
            reservation=validated.storage_reservation,
            reservation_file=reservation_file,
            free_bytes_before_release=free_before,
            free_bytes_after_release=free_after,
        )
        release_path.write_text(
            canonical_json(release.canonical_object()) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        verify_m336k7_reservation_release(release_path, validated=validated)
        verify_m336k7_released_resource_state(validated)
    if args.validation_receipt is not None:
        output = args.validation_receipt.resolve(strict=False)
        if output.exists():
            raise FileExistsError("M336K8 validation receipt output must be fresh")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            canonical_json(asdict(validated.receipt)) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if args.validate_only:
        print(canonical_json(asdict(validated.receipt)))
        return
    request = validated.request
    require_m336k8_execution_authority(
        post_freeze_validation_accepted=True,
        operation="INVOKE_FINAL_CONTROLLER",
    )
    internal_request = build_m336k8_internal_stage_request(validated)
    if rehearsal_closure is not None:
        internal_request.update(
            {
                "native_stage_plan_binding_hash": (
                    rehearsal_closure.native_stage_plan_binding.plan_binding_hash
                ),
                "producer_consumer_parity_receipt_hash": (
                    rehearsal_closure.producer_consumer_parity.receipt_hash
                ),
                "dispatch_contract_hash": rehearsal_closure.dispatch_contract_hash,
            }
        )
    private_root = Path(request.private_root).resolve(strict=False)
    private_root.mkdir(parents=True)
    monitor = M336K5ResourceMonitor(
        ledger=private_root / "m336k8-resource-samples.jsonl",
        filesystem_root=private_root,
        private_root=private_root,
        temp_root=Path(request.stage_receipt_root),
        interval_seconds=validated.resource_policy.long_phase_sample_interval_seconds,
    )
    monitor.start("OFFICIAL_ROUTE")
    stage_request_path = private_root / "canonical-internal-stage-request.json"
    stage_request_path.write_text(
        canonical_json(internal_request) + "\n", encoding="utf-8", newline="\n"
    )
    components = {item.name: item for item in validated.freeze.components}
    dependency_value = _component_object(
        Path(request.repository), components, "executable_dependency_manifest"
    )
    capsule_value = _component_object(
        Path(request.repository), components, "execution_capsule_receipt"
    )
    native_stage_dispatches = None
    native_stage_plan_binding = validated.native_stage_plan_binding
    producer_consumer_parity = validated.producer_consumer_parity_receipt
    if rehearsal_closure is not None:
        native_stage_dispatches = rehearsal_closure.dispatches
        native_stage_plan_binding = rehearsal_closure.native_stage_plan_binding
        producer_consumer_parity = rehearsal_closure.producer_consumer_parity
        plan = build_m336k12_native_execution_plan(
            repository=Path(request.repository),
            python_executable=Path(request.python_executable),
            stage_request=stage_request_path,
            stage_receipt_root=Path(request.stage_receipt_root),
            route_run_id=validated.bundle.protocol_run_id.value,
            exact_f37_sha=request.exact_freeze_sha,
            route_registry_hash=validated.bundle.route_registry_hash,
            dispatches=native_stage_dispatches,
        )
        parity = verify_m336k12_native_stage_plan(
            plan=plan,
            dispatches=native_stage_dispatches,
            plan_binding=native_stage_plan_binding,
            repository=Path(request.repository),
            python_executable=Path(request.python_executable),
        )
        if parity != producer_consumer_parity:
            raise M336K2ProtocolError(
                "M336K12 disposable execution plan differs from preledger admission"
            )
    elif validated.native_stage_plan_binding is not None:
        dispatch_value = _component_object(
            Path(request.repository), components, "native_stage_dispatches"
        )
        native_stage_dispatches = tuple(
            M336K12NativeStageDispatch.from_dict(item)
            for item in dispatch_value["dispatches"]
        )
        plan = build_m336k12_native_execution_plan(
            repository=Path(request.repository),
            python_executable=Path(request.python_executable),
            stage_request=stage_request_path,
            stage_receipt_root=Path(request.stage_receipt_root),
            route_run_id=validated.bundle.protocol_run_id.value,
            exact_f37_sha=request.exact_freeze_sha,
            route_registry_hash=validated.bundle.route_registry_hash,
            dispatches=native_stage_dispatches,
        )
    elif (
        dependency_value.get("contract_role")
        == M336K11HermeticExecutableDependencyManifest.ROLE
    ):
        dependency = M336K11HermeticExecutableDependencyManifest.from_dict(
            dependency_value
        )
        capsule = M336K11NativeExecutionCapsuleReceipt.from_dict(capsule_value)
        effective_environment = M336K11EffectiveEnvironmentBinding.from_dict(
            _component_object(
                Path(request.repository), components, "effective_environment_binding"
            )
        )
        plan = build_m336k11_native_execution_plan(
            repository=Path(request.repository),
            python_executable=Path(request.python_executable),
            stage_request=stage_request_path,
            stage_receipt_root=Path(request.stage_receipt_root),
            route_run_id=validated.bundle.protocol_run_id.value,
            exact_f36_sha=request.exact_freeze_sha,
            route_registry_hash=capsule.route_registry_hash,
            dependency_manifest=dependency,
            effective_environment=effective_environment,
            capsule=capsule,
        )
    else:
        historical_dependency = executable_dependency_manifest_from_dict(
            dependency_value
        )
        historical_capsule = execution_capsule_receipt_from_dict(capsule_value)
        plan = build_m336k2_native_execution_plan(
            repository=Path(request.repository),
            python_executable=Path(request.python_executable),
            stage_request=stage_request_path,
            stage_receipt_root=Path(request.stage_receipt_root),
            route_run_id=validated.bundle.protocol_run_id.value,
            exact_f28_sha=request.exact_freeze_sha,
            route_registry_hash=historical_capsule.route_registry_hash,
            dependency_manifest=historical_dependency,
            capsule=historical_capsule,
        )
    ledger = M336K2RouteLedger(
        Path(request.route_ledger),
        git_worktrees=_worktrees(
            Path(request.repository), Path(request.git_executable)
        ),
    )
    worker = M336K5IdentityCheckingWorker(
        M336K5HermeticCommandWorker(
            plan,
            repository=Path(request.repository),
            git_executable=Path(request.git_executable),
            python_executable=Path(request.python_executable),
            powershell_executable=Path(request.executable_handles["powershell"]),
            bootstrap_script=(
                Path(request.repository) / "scripts/m336k5_python_bootstrap.py"
            ),
            expected_startup_receipt_hash=validated.receipt.startup_receipt_hash,
            resource_monitor=monitor,
            native_stage_dispatches=native_stage_dispatches,
            native_stage_plan_binding=native_stage_plan_binding,
            producer_consumer_parity=producer_consumer_parity,
        ),
        receipt_root=Path(request.stage_receipt_root),
        bundle=validated.bundle,
        expected_startup_receipt_hash=validated.receipt.startup_receipt_hash,
        expected_acquisition_binding_hashes=(
            {}
            if validated.official_acquisition_binding is None
            else {
                "official_acquisition_binding_receipt_hash": (
                    validated.official_acquisition_binding.receipt_hash
                ),
                "stage_request_acquisition_binding_hash": (
                    validated.post_freeze_inputs.stage_request_acquisition_binding_hash
                ),
                "acquisition_ledger_context_template_hash": (
                    validated.post_freeze_inputs.acquisition_ledger_context_template_hash
                ),
            }
        ),
    )
    try:
        result = run_m336k5_final_controller(
            validated=validated,
            ledger=ledger,
            preledger_guard=lambda: validated.receipt,
            worker=worker,
            output=Path(request.route_receipt),
        )
    finally:
        monitor.stop("OFFICIAL_ROUTE")
    verify_m336k5_route_ledger_identity(
        ledger,
        bundle=validated.bundle,
        exact_f30_sha=request.exact_freeze_sha,
        preledger_receipt_hash=validated.receipt.receipt_hash,
        official_acquisition_binding_receipt_hash=(
            None
            if validated.official_acquisition_binding is None
            else validated.official_acquisition_binding.receipt_hash
        ),
        official_executable_binding_receipt_hash=(
            None
            if validated.official_executable_binding is None
            else validated.official_executable_binding.receipt_hash
        ),
    )
    print(canonical_json(asdict(result)))


def _component_object(root: Path, components: dict, name: str) -> dict:
    component = components[name]
    path = root.joinpath(*Path(component.relative_path).parts).resolve(strict=True)
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise TypeError(f"M336K8 frozen component is not an object: {name}")
    return value


def _load_rehearsal_dispatch_closure(
    path: Path | None,
    *,
    validated,
) -> M336K12DisposableDispatchClosure | None:
    if path is None:
        return None
    closure_path = path.resolve(strict=True)
    repository = Path(validated.request.repository).resolve(strict=True)
    if closure_path.is_relative_to(repository):
        raise M336K2ProtocolError("M336K12 disposable dispatch closure is public")
    value = json.loads(closure_path.read_text(encoding="utf-8"))
    closure = M336K12DisposableDispatchClosure.from_dict(value)
    profile_id = getattr(validated.authorization, "official_profile_id", None)
    if (
        validated.request.purpose != "DISPOSABLE"
        or profile_id != closure.rehearsal_profile_id
        or closure.native_stage_plan_binding.exact_implementation_tip
        != validated.request.exact_implementation_sha
        or closure.native_stage_plan_binding.route_registry_hash
        != validated.bundle.route_registry_hash
        or closure.native_stage_plan_binding.typed_route_manifest_hash
        != validated.bundle.route_manifest_hash
    ):
        raise M336K2ProtocolError("M336K12 disposable dispatch identity changed")
    prospective_plan = build_m336k12_native_execution_plan(
        repository=repository,
        python_executable=Path(validated.request.python_executable),
        stage_request=(
            Path(validated.request.private_root)
            / "canonical-internal-stage-request.json"
        ),
        stage_receipt_root=Path(validated.request.stage_receipt_root),
        route_run_id=validated.bundle.protocol_run_id.value,
        exact_f37_sha=validated.request.exact_freeze_sha,
        route_registry_hash=validated.bundle.route_registry_hash,
        dispatches=closure.dispatches,
    )
    parity = verify_m336k12_native_stage_plan(
        plan=prospective_plan,
        dispatches=closure.dispatches,
        plan_binding=closure.native_stage_plan_binding,
        repository=repository,
        python_executable=Path(validated.request.python_executable),
    )
    if parity != closure.producer_consumer_parity:
        raise M336K2ProtocolError("M336K12 disposable dispatch parity changed")
    return closure


def _claim_execution_lock(release_path: Path, request_path: Path) -> None:
    lock_path = release_path.with_name(release_path.name + ".lock")
    try:
        descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise M336K2ProtocolError(
            "M336K8 exclusive execution lock already exists"
        ) from error
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            canonical_json({"request_path_hash": _path_hash(request_path)}) + "\n"
        )
        stream.flush()
        os.fsync(stream.fileno())


def _path_hash(path: Path) -> str:
    return content_hash(os.path.normcase(str(path.resolve(strict=True))))


def _worktrees(repository: Path, git: Path) -> tuple[Path, ...]:
    raw = subprocess.run(
        (str(git.resolve(strict=True)), "worktree", "list", "--porcelain", "-z"),
        cwd=repository.resolve(strict=True),
        check=True,
        capture_output=True,
    ).stdout
    return tuple(
        Path(item.removeprefix(b"worktree ").decode("utf-8")).resolve(strict=True)
        for item in raw.split(b"\0")
        if item.startswith(b"worktree ")
    )


if __name__ == "__main__":
    main()
