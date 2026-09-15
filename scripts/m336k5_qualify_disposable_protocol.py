"""Run a disposable FINAL-mode Q/F/H/E chain through the official M336K5 CLI."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

from m336k5_prepare_karina_capsule import prepare_m336k5_karina_capsule

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336f_selection import M336FSelectorLedger
from ai_brain.stage3.acquisition.m336j_execution import (
    compute_m336j_project_source_identity,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ProtocolError,
    M336K2RouteLedger,
    m336k2_minimal_environment,
)
from ai_brain.stage3.acquisition.m336k2_publication import (
    publication_contract_from_dict,
    verify_m336k2_commit_protocol,
)
from ai_brain.stage3.acquisition.m336k5_cleanup import (
    write_m336k5_project_generated_marker,
)
from ai_brain.stage3.acquisition.m336k5_controller import (
    verify_m336k5_acquisition_ledger_identity,
    verify_m336k5_evaluator_ledger_identity,
    verify_m336k5_route_ledger_identity,
    verify_m336k5_selector_ledger_identity,
)
from ai_brain.stage3.acquisition.m336k5_freeze import (
    M336K5FreezeManifest,
    attest_committed_m336k5_f30,
    materialize_m336k5_f30,
)
from ai_brain.stage3.acquisition.m336k5_identity import M336K5RouteIdentityBundle
from ai_brain.stage3.acquisition.m336k5_request import (
    build_m336k5_final_route_request,
    write_m336k5_final_route_request,
)
from ai_brain.stage3.acquisition.m336k5_resources import (
    GIB,
    M336K5ResourceMonitor,
    build_m336k5_resource_budget_receipt,
    release_m336k5_storage_reservation,
)
from ai_brain.stage3.acquisition.m336k5_startup import (
    build_m336k5_python_invocation,
    run_m336k5_python_invocation,
    startup_receipt_from_path,
    write_m336k5_python_invocation_plan,
)
from ai_brain.stage3.acquisition.m336k7_contracts import (
    verify_m336k7_unchanged_candidate_pool,
)
from ai_brain.stage3.acquisition.m336k7_freeze import (
    M336K7FreezeManifest,
    attest_committed_m336k7_f32,
    materialize_m336k7_f32,
)
from ai_brain.stage3.acquisition.m336k7_request import (
    build_m336k7_final_route_request,
    write_m336k7_final_route_request,
)
from ai_brain.stage3.acquisition.m336k8_contracts import (
    M336K8FreezeAssemblyPlan,
    M336K8ProjectSourceIdentityReceipt,
)
from ai_brain.stage3.acquisition.m336k8_freeze import (
    M336K9_READY_STATUS,
    M336K9_REQUIRED_FREEZE_COMPONENTS,
    M336K10_READY_STATUS,
    M336K10_REQUIRED_FREEZE_COMPONENTS,
    M336K8FreezeManifest,
    attest_committed_m336k8_freeze,
    materialize_m336k8_freeze,
)
from ai_brain.stage3.acquisition.m336k8_request import (
    build_m336k8_final_route_request,
    write_m336k8_final_route_request,
)
from ai_brain.stage3.acquisition.m336k9_authorization import (
    m336k_current_final_authorization_from_dict,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    M336KOfficialRouteProfileStatus,
    m336k_official_profile_registry,
)
from ai_brain.stage3.acquisition.m336k_acquisition import M336KAcquisitionLedger

_LAUNCH_GIT: Path | None = None
_LAUNCH_POWERSHELL: Path | None = None
_LAUNCH_RECEIPTS: Path | None = None
_LAUNCH_SEQUENCE = 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--startup-receipt", type=Path, required=True)
    args = parser.parse_args()
    request = _object(args.request.resolve(strict=True))
    namespace = request.get("protocol_namespace", "m336k5")
    official_profile_id = request.get("official_profile_id")
    official_admission_only = request.get("official_admission_only", False)
    disposable_publication_generation = request.get("disposable_publication_generation")
    if namespace not in {"m336k5", "m336k7", "m336k8"}:
        raise M336K2ProtocolError("M336K disposable protocol namespace changed")
    expected = {
        "source_repository",
        "git_executable",
        "python_executable",
        "base_sha",
        "disposable_branch",
        "disposable_label",
        "legacy_component_request_template",
        "stage_request_template",
        "output",
        "powershell_executable",
        "resource_budget",
        "storage_reservation",
        "storage_reservation_file",
    }
    m336k7_inputs = {
        "protocol_namespace",
        "resource_budget_policy",
        "resource_observation",
        "resource_gate",
        "capsule_binding_set",
        "legacy_capsule_compatibility",
        "persistent_private_capsule",
        "persistent_public_capsule_receipt",
        "legacy_public_capsule_receipt",
        "persistent_python_environment_manifest",
        "capsule_content_manifest",
        "capsule_lifecycle_policy",
        "capsule_liveness",
        "preservation_set",
        "cleanup_plan",
        "cleanup_cutoff_state",
        "candidate_pool",
    }
    if namespace in {"m336k7", "m336k8"}:
        expected = (expected - {"resource_budget"}) | m336k7_inputs
    if official_profile_id is not None:
        expected |= {"official_profile_id"}
    if "official_admission_only" in request:
        expected |= {"official_admission_only"}
    if "disposable_publication_generation" in request:
        expected |= {"disposable_publication_generation"}
    persistent = "persistent_karina_overlay" in request
    if namespace in {"m336k7", "m336k8"} and not persistent:
        raise M336K2ProtocolError(
            "M336K persistent-capsule rehearsal requires the persistent capsule"
        )
    if set(request) != expected | (
        {"persistent_karina_overlay"} if persistent else set()
    ):
        raise M336K2ProtocolError("M336K5 disposable request fields changed")
    official_profile = (
        m336k_official_profile_registry().profile(official_profile_id)
        if official_profile_id is not None
        else None
    )
    acquisition_bound_official = official_profile_id == "m336k8-final-v3"
    expected_profile_status = (
        M336KOfficialRouteProfileStatus.CURRENT_ACTIVE
        if official_admission_only
        else M336KOfficialRouteProfileStatus.REHEARSAL_ONLY
    )
    if (
        type(official_admission_only) is not bool
        or official_admission_only
        and official_profile is None
        or official_profile is not None
        and (
            namespace != "m336k8"
            or official_profile.profile_status is not expected_profile_status
        )
        or disposable_publication_generation is not None
        and (
            disposable_publication_generation != "m336k10"
            or namespace != "m336k8"
            or official_profile is None
        )
    ):
        raise M336K2ProtocolError("M336K9 rehearsal profile purpose changed")
    final_candidate_pool = None
    if namespace in {"m336k7", "m336k8"}:
        final_candidate_pool = verify_m336k7_unchanged_candidate_pool(
            Path(request["candidate_pool"])
        )
    output = Path(request["output"]).resolve(strict=False)
    if output.exists():
        raise FileExistsError("M336K5 disposable output must be fresh")
    output.mkdir(parents=True)
    monitor = M336K5ResourceMonitor(
        ledger=output / "resource-samples.private.jsonl",
        filesystem_root=output,
        private_root=output,
        temp_root=output,
    )
    monitor.start("DISPOSABLE_FULL_CHAIN")
    startup_receipt_path = args.startup_receipt.resolve(strict=True)
    startup = startup_receipt_from_path(startup_receipt_path)
    git = Path(request["git_executable"]).resolve(strict=True)
    python = Path(request["python_executable"]).resolve(strict=True)
    powershell = Path(request["powershell_executable"]).resolve(strict=True)
    source = Path(request["source_repository"]).resolve(strict=True)
    _configure_launcher(
        git,
        powershell,
        output / "launcher-receipts",
    )
    branch = request["disposable_branch"]
    if (
        official_admission_only
        and f"refs/heads/{branch}" != official_profile.authorization_branch_ref
        or not official_admission_only
        and not branch.startswith(f"disposable/{namespace}-")
    ):
        raise M336K2ProtocolError("M336K5 disposable branch namespace changed")
    remote = output / "origin.git"
    repository = output / "repository"
    private = output / "private"
    public = output / "public"
    private.mkdir()
    public.mkdir()
    reservation_path = Path(request["storage_reservation_file"]).resolve(strict=True)
    reservation_receipt = _verified_receipt(
        Path(request["storage_reservation"]).resolve(strict=True), "receipt_hash"
    )
    if (
        reservation_receipt.get("status") != "PASS"
        or reservation_receipt.get("sparse") is not False
        or reservation_path.stat().st_size
        != reservation_receipt.get("reservation_bytes")
    ):
        raise M336K2ProtocolError("M336K5 disposable reservation is invalid")
    _git(git, None, "init", "--bare", str(remote))
    _git(git, None, "clone", "--no-local", str(source), str(repository))
    _git(git, repository, "config", "core.autocrlf", "false")
    _git(git, repository, "config", "user.email", "m336k5@example.invalid")
    _git(git, repository, "config", "user.name", "M336K5 Disposable Proof")
    _git(git, repository, "remote", "set-url", "origin", str(remote))
    _git(git, repository, "checkout", "-B", branch, request["base_sha"])
    if namespace == "m336k5":
        _apply_working_tree(source, repository, git, request["base_sha"])
        _git(git, repository, "add", "--all")
        _git(
            git,
            repository,
            "commit",
            "-m",
            "M-33.6k.5 disposable implementation snapshot",
        )
    implementation = _git(git, repository, "rev-parse", "HEAD^{commit}")
    _git(git, repository, "push", "-u", "origin", branch)
    stage_template = _object(
        Path(request["stage_request_template"]).resolve(strict=True)
    )
    label = request["disposable_label"]
    if not isinstance(label, str) or re.fullmatch(r"[a-z0-9-]+", label) is None:
        raise M336K2ProtocolError("M336K5 disposable label is invalid")
    base_karina = stage_template["karina"]
    if persistent:
        persistent_overlay = _object(
            Path(request["persistent_karina_overlay"]).resolve(strict=True)
        )
        required_overlay = {
            "private_execution_capsule",
            "public_execution_capsule_receipt",
            "executable_dependency_manifest",
            "private_capsule_remote",
            "repository",
            "private_root",
            "m336k6_private_capsule_remote",
            "m336k6_public_capsule_receipt",
            "project_source_identity",
        }
        if set(persistent_overlay) != required_overlay:
            raise M336K2ProtocolError("M336K6 persistent overlay fields changed")
        karina_overlay = {
            name: persistent_overlay[name]
            for name in (
                "private_execution_capsule",
                "public_execution_capsule_receipt",
                "executable_dependency_manifest",
                "private_capsule_remote",
                "repository",
                "private_root",
            )
        }
        karina_preparation = {
            "project_source_identity": persistent_overlay["project_source_identity"]
        }
    else:
        karina_preparation = prepare_m336k5_karina_capsule(
            {
                "repository": str(repository),
                "exact_head": implementation,
                "git_executable": str(git),
                "base_private_capsule": base_karina["private_execution_capsule"],
                "base_public_execution_capsule_receipt": base_karina[
                    "public_execution_capsule_receipt"
                ],
                "ssh_executable": base_karina["ssh_executable"],
                "scp_executable": stage_template["executable_handles"]["scp"],
                "ssh_key": base_karina["ssh_key"],
                "known_hosts_file": base_karina["known_hosts_file"],
                "worker_endpoint": base_karina["worker_endpoint"],
                "remote_workspace": (
                    f"/home/ibicza/m336k5-disposable-{label}-{implementation[:12]}"
                ),
                "output": str(private / "karina-capsule"),
            }
        )
        karina_overlay = karina_preparation["karina_overlay"]
    startup_components = private / "startup-components"
    _run(
        python,
        repository,
        "scripts/m336k5_build_startup_components.py",
        "--repository",
        str(repository),
        "--git-executable",
        str(git),
        "--output",
        str(startup_components),
    )
    environment_path = startup_components / "python_environment_manifest.json"
    legacy_request = _object(
        Path(request["legacy_component_request_template"]).resolve(strict=True)
    )
    legacy_output = private / "legacy-components"
    if disposable_publication_generation == "m336k10":
        publication_values = {
            "q_root": "artifacts/m336k10/disposable/q35-like",
            "f_root": "artifacts/m336k10/disposable/f35-like-freeze",
            "h_root": "artifacts/m336k10/disposable/h35-like",
            "e_root": "artifacts/m336k10/disposable/e35-like",
            "q_subject": "M-33.6k.10 qualify disposable acquisition route",
            "f_subject": "M-33.6k.10 freeze disposable acquisition route",
            "h_subject": "M-33.6k.10 publish disposable sealed production",
            "e_subject": "M-33.6k.10 publish disposable independent evidence",
        }
    elif official_profile is not None:
        publication_values = {
            "q_root": "artifacts/m336k9/q34",
            "f_root": "artifacts/m336k9/f34-freeze",
            "h_root": "artifacts/m336k9/h34",
            "e_root": "artifacts/m336k9/e34",
            "q_subject": "M-33.6k.9 qualify disposable admission route",
            "f_subject": "M-33.6k.9 freeze disposable admission route",
            "h_subject": "M-33.6k.9 publish disposable sealed production",
            "e_subject": "M-33.6k.9 publish disposable independent evidence",
        }
    elif namespace == "m336k8":
        publication_values = {
            "q_root": "artifacts/m336k8/q33",
            "f_root": "artifacts/m336k8/f33-freeze",
            "h_root": "artifacts/m336k8/h33",
            "e_root": "artifacts/m336k8/e33",
            "q_subject": "M-33.6k.8 qualify exact source-domain freeze inputs",
            "f_subject": "M-33.6k.8 freeze final Java execution",
            "h_subject": "M-33.6k.8 publish sealed Java production",
            "e_subject": "M-33.6k.8 publish independent Java evidence",
        }
    elif namespace == "m336k7":
        publication_values = {
            "q_root": "artifacts/m336k7/q32",
            "f_root": "artifacts/m336k7/f32-freeze",
            "h_root": "artifacts/m336k7/h32",
            "e_root": "artifacts/m336k7/e32",
            "q_subject": "M-33.6k.7 qualify exact committed freeze inputs",
            "f_subject": "M-33.6k.7 freeze final Java execution",
            "h_subject": "M-33.6k.7 publish sealed Java production",
            "e_subject": "M-33.6k.7 publish independent Java evidence",
        }
    else:
        publication_values = {
            "q_root": "artifacts/m336k5/disposable/q-like",
            "f_root": "artifacts/m336k5/disposable/f-like",
            "h_root": "artifacts/m336k5/disposable/h-like",
            "e_root": "artifacts/m336k5/disposable/e-like",
            "q_subject": "M-33.6k.5 disposable Q-like",
            "f_subject": "M-33.6k.5 disposable F-like",
            "h_subject": "M-33.6k.5 disposable H-like",
            "e_subject": "M-33.6k.5 disposable E-like",
        }
    legacy_request.update(
        {
            "repository": str(repository),
            "python_executable": str(python),
            "python_environment_manifest": str(environment_path),
            "output": str(legacy_output),
            "branch_ref": f"refs/heads/{branch}",
            **publication_values,
            "execution_mode": "FINAL",
            "acquisition_run_id": (
                f"{namespace}.disposable.{request['disposable_label']}.acquisition.v1"
            ),
        }
    )
    legacy_request["executables"]["python"]["path"] = str(python)
    legacy_request["executables"]["powershell"]["path"] = str(powershell)
    legacy_request["karina_public_execution_capsule_receipt"] = karina_overlay[
        "public_execution_capsule_receipt"
    ]
    legacy_request["karina_executable_dependency_manifest"] = karina_overlay[
        "executable_dependency_manifest"
    ]
    legacy_request_path = private / "legacy-component-request.json"
    _write(legacy_request_path, legacy_request)
    _run(
        python,
        repository,
        "scripts/m336k2_build_component_bundle.py",
        "--request",
        str(legacy_request_path),
    )
    source_domain_output = None
    if namespace == "m336k8":
        source_domain_output = private / "source-domain-contracts"
        source_domain_request = {
            "repository": str(repository),
            "git_executable": str(git),
            "python_executable": str(python),
            "exact_implementation_tip": implementation,
            "startup_components": str(startup_components),
            "capsule_binding_set": request["capsule_binding_set"],
            "capsule_content_manifest": request["capsule_content_manifest"],
            "capsule_lifecycle_policy": request["capsule_lifecycle_policy"],
            "capsule_liveness_receipt": request["capsule_liveness"],
            "persistent_public_receipt": request["persistent_public_capsule_receipt"],
            "legacy_public_receipt": request["legacy_public_capsule_receipt"],
            "persistent_capsule_python_environment_manifest": request[
                "persistent_python_environment_manifest"
            ],
            "persistent_capsule_executable_dependency_manifest": persistent_overlay[
                "executable_dependency_manifest"
            ],
            "stable_host_identity_receipt": str(
                legacy_output / "karina_stable_host_identity.json"
            ),
            "executable_handles": legacy_request["executables"],
            "output": str(source_domain_output),
        }
        source_domain_request_path = private / "source-domain-request.json"
        _write(source_domain_request_path, source_domain_request)
        _run(
            python,
            repository,
            "scripts/m336k8_build_source_domain_contracts.py",
            "--request",
            str(source_domain_request_path),
        )
    q_root = repository.joinpath(*Path(legacy_request["q_root"]).parts)
    q_root.mkdir(parents=True)
    _write(
        q_root / "identity_qualification.json",
        _hashed(
            "receipt_hash",
            schema_version=1,
            contract_role=(
                "PUBLIC_SAFE_M336K9_CONTROLLER_ADMISSION_REHEARSAL_QUALIFICATION"
                if official_profile is not None
                else "PUBLIC_SAFE_M336K8_SOURCE_DOMAIN_REHEARSAL_QUALIFICATION"
                if namespace == "m336k8"
                else "PUBLIC_SAFE_M336K7_COMMITTED_FREEZE_REHEARSAL_QUALIFICATION"
                if namespace == "m336k7"
                else "PUBLIC_SAFE_M336K5_DISPOSABLE_IDENTITY_QUALIFICATION"
            ),
            required_mutation_case_count=(
                71
                if official_profile is not None
                else 44
                if namespace == "m336k8"
                else 32
                if namespace == "m336k7"
                else 25
            ),
            mutation_execution_phase="POST_F_LIKE_PRE_CONTROLLER",
            canonical_request_builder_present=True,
            external_route_run_id_absent=True,
            execution_mode="FINAL",
            status="PASS",
        ),
    )
    q_manifest = _q_manifest(q_root)
    q_manifest_path = q_root / "evidence_manifest.json"
    _write(q_manifest_path, q_manifest)
    readiness_body = {
        "schema_version": 1,
        "contract_role": (
            "PUBLIC_SAFE_M336K9_DISPOSABLE_Q_LIKE_READINESS"
            if official_profile is not None
            else "PUBLIC_SAFE_M336K8_DISPOSABLE_Q_LIKE_READINESS"
            if namespace == "m336k8"
            else "PUBLIC_SAFE_M336K7_DISPOSABLE_Q_LIKE_READINESS"
            if namespace == "m336k7"
            else "PUBLIC_SAFE_M336K5_DISPOSABLE_Q_LIKE_READINESS"
        ),
        "exact_implementation_tip": implementation,
        "official_one_shot_counter_count": 0,
        "new_final_source_body_bytes": 0,
        "status": (
            M336K10_READY_STATUS
            if acquisition_bound_official
            else M336K9_READY_STATUS
            if official_profile is not None
            else "READY_FOR_SOURCE_DOMAIN_BOUND_FINAL_JAVA_EXECUTION_V8"
            if namespace == "m336k8"
            else "READY_FOR_FROZEN_RESOURCE_BOUND_FINAL_JAVA_EXECUTION_V7"
            if namespace == "m336k7"
            else "READY_FOR_HERMETIC_FINAL_JAVA_EXECUTION_V5"
        ),
    }
    readiness = {**readiness_body, "readiness_hash": content_hash(readiness_body)}
    readiness_path = q_root / "readiness.json"
    _write(readiness_path, readiness)
    q_like = _commit(
        git, repository, legacy_request["q_subject"], legacy_request["q_root"]
    )
    _git(git, repository, "push", "origin", branch)
    typed_output = private / "typed-components"
    typed_request = {
        "repository": str(repository),
        "legacy_bundle": str(legacy_output),
        "exact_implementation_tip": implementation,
        "exact_q30_sha": q_like,
        "branch_ref": f"refs/heads/{branch}",
        "readiness_hash": readiness["readiness_hash"],
        "q_readiness": str(readiness_path),
        "q_evidence_manifest": str(q_manifest_path),
        "identity_mode": "OFFICIAL" if official_admission_only else "DISPOSABLE",
        "disposable_label": request["disposable_label"],
        "output": str(typed_output),
        "python_environment_manifest": str(environment_path),
        **{
            name: str(startup_components / f"{name}.json")
            for name in (
                "python_startup_policy",
                "python_startup_bootstrap",
                "windows_python_launcher",
                "karina_python_launcher",
                "sanitized_environment_policy",
                "startup_receipt_schema",
                "resource_monitor",
                "cleanup_policy",
                "recovery_checkpoint_policy",
            )
        },
        "storage_reservation": request["storage_reservation"],
    }
    if namespace in {"m336k7", "m336k8"}:
        typed_request.update(
            {
                "identity_namespace": namespace,
                "resource_budget_policy": request["resource_budget_policy"],
                "resource_observation": request["resource_observation"],
                "resource_gate": request["resource_gate"],
                "capsule_binding_set": request["capsule_binding_set"],
                "legacy_capsule_compatibility": request["legacy_capsule_compatibility"],
                "persistent_capsule_receipt": request[
                    "persistent_public_capsule_receipt"
                ],
                "capsule_content_manifest": request["capsule_content_manifest"],
                "capsule_lifecycle_policy": request["capsule_lifecycle_policy"],
                "capsule_liveness": request["capsule_liveness"],
                "preservation_set": request["preservation_set"],
                "cleanup_plan": request["cleanup_plan"],
                "cleanup_cutoff_state": request["cleanup_cutoff_state"],
                # An OFFICIAL-purpose admission rehearsal must present the
                # unchanged final metadata-only pool to the official component
                # builder.  The builder still freezes the disclosed synthetic
                # pool copied from the legacy rehearsal bundle, so this check
                # cannot acquire or expose final source bodies.
                "candidate_pool": (
                    request["candidate_pool"]
                    if official_admission_only
                    else legacy_request["candidate_pool"]
                ),
            }
        )
        if namespace == "m336k8":
            if source_domain_output is None:
                raise M336K2ProtocolError("M336K8 source-domain output is absent")
            typed_request.update(
                {
                    name: str(source_domain_output / f"{name}.json")
                    for name in (
                        "controller_source_identity_policy",
                        "controller_source_identity_receipt",
                        "controller_python_environment_manifest",
                        "controller_executable_dependency_manifest",
                        "controller_startup_binding",
                        "persistent_capsule_source_binding",
                        "bridge_surface_manifest",
                        "source_domain_compatibility",
                        "legacy_controller_alias_receipt",
                        "freeze_assembly_plan",
                    )
                }
            )
            typed_request["persistent_capsule_python_environment_manifest"] = request[
                "persistent_python_environment_manifest"
            ]
            typed_request["persistent_capsule_executable_dependency_manifest"] = (
                persistent_overlay["executable_dependency_manifest"]
            )
            if official_profile is not None:
                typed_request["official_profile_id"] = official_profile.profile_id
    else:
        typed_request["resource_budget"] = request["resource_budget"]
    typed_request_path = private / "typed-component-request.json"
    _write(typed_request_path, typed_request)
    _run(
        python,
        repository,
        "scripts/m336k5_build_component_bundle.py",
        "--request",
        str(typed_request_path),
    )
    components = {
        path.stem: path
        for path in typed_output.glob("*.json")
        if path.name != "bundle_receipt.json"
    }
    f_root = repository.joinpath(*Path(legacy_request["f_root"]).parts)
    freeze_builder = (
        materialize_m336k8_freeze
        if namespace == "m336k8"
        else materialize_m336k7_f32
        if namespace == "m336k7"
        else materialize_m336k5_f30
    )
    build = freeze_builder(
        repository=repository,
        git_executable=git,
        exact_implementation_tip=implementation,
        **(
            {"exact_qualification_sha": q_like}
            if namespace == "m336k8"
            else {"exact_q32_sha": q_like}
            if namespace == "m336k7"
            else {"exact_q30_sha": q_like}
        ),
        readiness=readiness_path,
        component_sources=components,
        output=f_root,
        expected_branch=branch,
        freeze_relative_root=legacy_request["f_root"],
        **(
            {
                "readiness_status": (
                    M336K10_READY_STATUS
                    if acquisition_bound_official
                    else M336K9_READY_STATUS
                ),
                "freeze_role": (
                    M336K8FreezeManifest.ROLE_V3
                    if acquisition_bound_official
                    else M336K8FreezeManifest.ROLE_V2
                ),
                "required_components": (
                    M336K10_REQUIRED_FREEZE_COMPONENTS
                    if acquisition_bound_official
                    else M336K9_REQUIRED_FREEZE_COMPONENTS
                ),
                "build_receipt_name": (
                    "f35_build_receipt.json"
                    if acquisition_bound_official
                    else "f34_build_receipt.json"
                ),
            }
            if official_profile is not None
            else {}
        ),
    )
    f_like = _commit(
        git, repository, legacy_request["f_subject"], legacy_request["f_root"]
    )
    _git(git, repository, "push", "origin", branch)
    freeze = _load_freeze(f_root / "freeze_manifest.json")
    if namespace == "m336k8":
        attestation = attest_committed_m336k8_freeze(
            repository, git, freeze_manifest=freeze, exact_freeze_sha=f_like
        )
    elif namespace == "m336k7":
        attestation = attest_committed_m336k7_f32(
            repository, git, freeze_manifest=freeze, exact_f32_sha=f_like
        )
    else:
        attestation = attest_committed_m336k5_f30(
            repository, git, freeze_manifest=freeze, exact_f30_sha=f_like
        )
    attestation_path = private / (
        "freeze-attestation.json"
        if namespace == "m336k8"
        else "f32-attestation.json"
        if namespace == "m336k7"
        else "f30-attestation.json"
    )
    _write(attestation_path, asdict(attestation))
    runtime = output / "runtime"
    destinations = {
        "acquisition_ledger": str(runtime / "ledgers" / "acquisition.jsonl"),
        "selector_ledger": str(runtime / "ledgers" / "selector.jsonl"),
        "evaluator_ledger": str(runtime / "ledgers" / "evaluator.jsonl"),
        "route_state_ledger": str(runtime / "ledgers" / "route.jsonl"),
        "vault": str(runtime / "vault"),
        "selected_source_snapshot": str(runtime / "windows-selected"),
        "windows_production": str(runtime / "windows-production"),
        "karina_production": str(runtime / "karina-production"),
        "evaluator_root": str(runtime / "evaluator"),
    }
    stage = _render_stage_template(
        stage_template,
        repository=repository,
        git=git,
        python=python,
        powershell=powershell,
        implementation=implementation,
        f_like=f_like,
        freeze_root=f_root,
        attestation=attestation_path,
        runtime=runtime,
        destinations=destinations,
    )
    stage["karina"].update(karina_overlay)
    bundle_path = _frozen_component(repository, freeze, "route_identity_bundle")
    authorization_path = _frozen_component(repository, freeze, "final_authorization")
    contract_path = _frozen_component(repository, freeze, "h28_publication_contract")
    common_request = {
        "purpose": "OFFICIAL" if official_admission_only else "DISPOSABLE",
        "repository": str(repository),
        "git_executable": str(git),
        "python_executable": str(python),
        "exact_implementation_sha": implementation,
        "freeze_manifest": str(f_root / "freeze_manifest.json"),
        "final_authorization": str(authorization_path),
        "route_identity_bundle": str(bundle_path),
        "publication_contract": str(contract_path),
        "route_ledger": destinations["route_state_ledger"],
        "route_receipt": str(runtime / "route-receipt.json"),
        "stage_state": str(runtime / "stage-state.json"),
        "stage_receipt_root": str(runtime / "stage-receipts"),
        "private_root": str(runtime / "private"),
        "authority_statement": stage["authority_statement"],
        "frozen_spdx_reference": stage["frozen_spdx_reference"],
        "windows_java": stage["windows_java"],
        "windows_javac": stage["windows_javac"],
        "final_destinations": destinations,
        "executable_handles": stage["executable_handles"],
    }
    if namespace in {"m336k7", "m336k8"}:
        persistent_overlay = _object(
            Path(request["persistent_karina_overlay"]).resolve(strict=True)
        )
        component_names = [
            "post_freeze_input_bundle",
            "resource_budget_policy",
            "resource_observation",
            "storage_reservation",
            "resource_gate",
            "capsule_binding_set",
            "legacy_capsule_compatibility",
            "capsule_liveness",
        ]
        if namespace == "m336k8":
            component_names.extend(
                (
                    "freeze_assembly_plan",
                    "freeze_assembly_receipt",
                    "controller_source_identity_policy",
                    "controller_source_identity_receipt",
                    "controller_python_environment_manifest",
                    "controller_executable_dependency_manifest",
                    "controller_startup_binding",
                    "persistent_capsule_source_binding",
                    "persistent_capsule_python_environment_manifest",
                    "persistent_capsule_executable_dependency_manifest",
                    "legacy_controller_alias_receipt",
                    "bridge_surface_manifest",
                    "source_domain_compatibility",
                    "frozen_contract_compatibility_v2",
                )
            )
        component_paths = {
            name: _frozen_component(repository, freeze, name)
            for name in component_names
        }
        legacy_karina = stage["karina"]
        current_karina = {
            "persistent_private_capsule": request["persistent_private_capsule"],
            "private_execution_capsule": persistent_overlay[
                "private_execution_capsule"
            ],
            "persistent_public_capsule_receipt": request[
                "persistent_public_capsule_receipt"
            ],
            "legacy_public_capsule_receipt": request["legacy_public_capsule_receipt"],
            "executable_dependency_manifest": persistent_overlay[
                "executable_dependency_manifest"
            ],
            "python_environment_manifest": request[
                "persistent_python_environment_manifest"
            ],
            "capsule_liveness_receipt": str(component_paths["capsule_liveness"]),
            **{
                name: legacy_karina[name]
                for name in (
                    "ssh_executable",
                    "ssh_key",
                    "known_hosts_file",
                    "worker_endpoint",
                    "repository",
                    "private_root",
                    "private_capsule_remote",
                    "javac",
                )
            },
        }
        if namespace == "m336k8":
            current_common = dict(common_request)
            current_common["exact_implementation_tip"] = current_common.pop(
                "exact_implementation_sha"
            )
            final_request = build_m336k8_final_route_request(
                **current_common,
                exact_freeze_sha=f_like,
                freeze_attestation=str(attestation_path),
                post_freeze_input_bundle=str(
                    component_paths["post_freeze_input_bundle"]
                ),
                freeze_assembly_plan=str(component_paths["freeze_assembly_plan"]),
                freeze_assembly_receipt=str(component_paths["freeze_assembly_receipt"]),
                controller_source_identity_policy=str(
                    component_paths["controller_source_identity_policy"]
                ),
                controller_source_identity_receipt=str(
                    component_paths["controller_source_identity_receipt"]
                ),
                controller_python_environment_manifest=str(
                    component_paths["controller_python_environment_manifest"]
                ),
                controller_executable_dependency_manifest=str(
                    component_paths["controller_executable_dependency_manifest"]
                ),
                controller_startup_binding=str(
                    component_paths["controller_startup_binding"]
                ),
                persistent_capsule_binding_set=str(
                    component_paths["capsule_binding_set"]
                ),
                persistent_capsule_source_binding=str(
                    component_paths["persistent_capsule_source_binding"]
                ),
                persistent_capsule_python_environment_manifest=str(
                    component_paths["persistent_capsule_python_environment_manifest"]
                ),
                persistent_capsule_executable_dependency_manifest=str(
                    component_paths["persistent_capsule_executable_dependency_manifest"]
                ),
                legacy_capsule_compatibility=str(
                    component_paths["legacy_capsule_compatibility"]
                ),
                legacy_controller_alias_receipt=str(
                    component_paths["legacy_controller_alias_receipt"]
                ),
                bridge_surface_manifest=str(component_paths["bridge_surface_manifest"]),
                source_domain_compatibility=str(
                    component_paths["source_domain_compatibility"]
                ),
                frozen_contract_compatibility_v2=str(
                    component_paths["frozen_contract_compatibility_v2"]
                ),
                resource_budget_policy=str(component_paths["resource_budget_policy"]),
                resource_observation_receipt=str(
                    component_paths["resource_observation"]
                ),
                storage_reservation_receipt=str(component_paths["storage_reservation"]),
                storage_reservation_file=str(reservation_path),
                resource_gate_receipt=str(component_paths["resource_gate"]),
                capsule_liveness_receipt=str(component_paths["capsule_liveness"]),
                karina=current_karina,
            )
        else:
            final_request = build_m336k7_final_route_request(
                **common_request,
                exact_f32_sha=f_like,
                f32_attestation=str(attestation_path),
                post_freeze_input_bundle=str(
                    component_paths["post_freeze_input_bundle"]
                ),
                resource_budget_policy=str(component_paths["resource_budget_policy"]),
                resource_observation_receipt=str(
                    component_paths["resource_observation"]
                ),
                storage_reservation_receipt=str(component_paths["storage_reservation"]),
                storage_reservation_file=str(reservation_path),
                resource_gate_receipt=str(component_paths["resource_gate"]),
                capsule_binding_set=str(component_paths["capsule_binding_set"]),
                legacy_compatibility_receipt=str(
                    component_paths["legacy_capsule_compatibility"]
                ),
                capsule_liveness_receipt=str(component_paths["capsule_liveness"]),
                karina=current_karina,
            )
    else:
        final_request = build_m336k5_final_route_request(
            **common_request,
            exact_f30_sha=f_like,
            f30_attestation=str(attestation_path),
            karina=stage["karina"],
        )
    final_request_path = private / "canonical-final-request.json"
    request_writer = (
        write_m336k8_final_route_request
        if namespace == "m336k8"
        else write_m336k7_final_route_request
        if namespace == "m336k7"
        else write_m336k5_final_route_request
    )
    request_writer(final_request, final_request_path)
    mutation_path = public / "identity_mutation_receipt.json"
    if namespace == "m336k8":
        _run(
            python,
            repository,
            "scripts/m336k8_run_contract_mutations.py",
            "--repository",
            str(repository),
            "--output",
            str(mutation_path),
        )
    elif namespace == "m336k7":
        _run(
            python,
            repository,
            "scripts/m336k7_run_contract_mutations.py",
            "--repository",
            str(repository),
            "--output",
            str(mutation_path),
        )
    else:
        _run(
            python,
            repository,
            "scripts/m336k5_run_identity_mutations.py",
            "--request",
            str(final_request_path),
            "--workspace",
            str(private / "identity-mutation-workspace"),
            "--output",
            str(mutation_path),
        )
    mutation = _object(mutation_path)
    if (
        mutation.get(
            "mutation_case_count" if namespace in {"m336k7", "m336k8"} else "case_count"
        )
        != (44 if namespace == "m336k8" else 32 if namespace == "m336k7" else 25)
        or mutation.get("accepted_invalid_case_count") != 0
        or mutation.get("wrong_rejection_layer_count") != 0
        or namespace == "m336k8"
        and mutation.get("hash_only_cross_domain_rejection_count") != 0
        or mutation.get("status") != "PASS"
    ):
        raise M336K2ProtocolError("M336K5 disposable mutation matrix failed")
    admission_mutation = None
    if official_profile is not None:
        admission_mutation_path = public / "controller_admission_mutation_report.json"
        _run(
            python,
            repository,
            "scripts/m336k9_run_admission_mutations.py",
            "--repository",
            str(repository),
            "--python",
            str(python),
            "--output",
            str(admission_mutation_path),
        )
        admission_mutation = _object(admission_mutation_path)
        if (
            admission_mutation.get("mutation_case_count") != 27
            or admission_mutation.get("accepted_invalid_count") != 0
            or admission_mutation.get("wrong_rejection_layer_count") != 0
            or admission_mutation.get("status") != "PASS"
        ):
            raise M336K2ProtocolError("M336K9 admission mutation matrix failed")
    validation_path = private / "preledger-invocation.json"
    final_route_script = (
        "scripts/m336k8_run_final_route.py"
        if namespace == "m336k8"
        else "scripts/m336k7_run_final_route.py"
        if namespace == "m336k7"
        else "scripts/m336k5_run_final_route.py"
    )
    _run(
        python,
        repository,
        final_route_script,
        "--request",
        str(final_request_path),
        "--validate-only",
        "--validation-receipt",
        str(validation_path),
        *(
            ("--startup-receipt", str(startup_receipt_path))
            if namespace == "m336k8"
            else ()
        ),
    )
    monitor.sample("DISPOSABLE_POST_FREEZE_VALIDATION")
    release_receipt_path = public / "reservation_release_receipt.json"
    if official_admission_only:
        preledger = _object(validation_path)
        counters = {
            "route_events": preledger["route_ledger_writes"],
            "acquisition_reservations": preledger["acquisition_reservations"],
            "source_requests": preledger["source_requests"],
            "vault_files": preledger["vault_files"],
        }
        if (
            any(counters.values())
            or preledger.get("status") != "FINAL_INVOCATION_ACCEPTED_PRE_LEDGER"
            or preledger.get("official_profile_id") != official_profile.profile_id
            or preledger.get("official_profile_hash") != official_profile.profile_hash
            or preledger.get("official_profile_registry_hash")
            != m336k_official_profile_registry().registry_hash
            or not preledger.get("controller_admission_receipt_hash")
            or acquisition_bound_official
            and not preledger.get("official_acquisition_binding_receipt_hash")
            or any(Path(path).exists() for path in destinations.values())
        ):
            raise M336K2ProtocolError("M336K9 official admission rehearsal spent state")
        free_before_release = shutil.disk_usage(reservation_path.parent).free
        release_m336k5_storage_reservation(reservation_path)
        free_after_release = shutil.disk_usage(reservation_path.parent).free
        release_body = {
            "schema_version": 1,
            "contract_role": "PUBLIC_SAFE_M336K9_REHEARSAL_RESERVATION_RELEASE",
            "storage_reservation_receipt_hash": reservation_receipt["receipt_hash"],
            "released_bytes": reservation_receipt["reservation_bytes"],
            "free_bytes_before_release": free_before_release,
            "free_bytes_after_release": free_after_release,
            "status": "PASS",
        }
        release_receipt = {
            **release_body,
            "receipt_hash": content_hash(release_body),
        }
        _write(release_receipt_path, release_receipt)
        monitor.stop("OFFICIAL_ADMISSION_REHEARSAL")
        body = {
            "schema_version": 1,
            "contract_role": (
                "PUBLIC_SAFE_M336K10_OFFICIAL_ACQUISITION_ADMISSION_REHEARSAL"
                if acquisition_bound_official
                else "PUBLIC_SAFE_M336K9_OFFICIAL_PURPOSE_ADMISSION_REHEARSAL"
            ),
            "implementation_tip": implementation,
            "q_like_sha": q_like,
            "f_like_sha": f_like,
            "freeze_build_receipt_hash": build["receipt_hash"],
            "f_attestation_hash": attestation.attestation_hash,
            "canonical_final_request_hash": final_request.request_hash,
            "preledger_invocation_receipt_hash": preledger["receipt_hash"],
            "preledger_status": preledger["status"],
            "official_profile_id": official_profile.profile_id,
            "official_profile_status": official_profile.profile_status.value,
            "official_profile_hash": official_profile.profile_hash,
            "official_profile_registry_hash": preledger[
                "official_profile_registry_hash"
            ],
            "controller_admission_receipt_hash": preledger[
                "controller_admission_receipt_hash"
            ],
            "controller_admission_result": "PASS",
            "controller_admission_receipt_bound": True,
            "official_acquisition_binding_receipt_hash": preledger.get(
                "official_acquisition_binding_receipt_hash"
            ),
            "acquisition_admission_status": (
                "OFFICIAL_ACQUISITION_INPUTS_ACCEPTED_PRELEDGER"
                if acquisition_bound_official
                else "NOT_APPLICABLE"
            ),
            "reservation_release_receipt_hash": release_receipt["receipt_hash"],
            **counters,
            "official_one_shot_counter_count": 0,
            "source_body_bytes": 0,
            "status": "PASS",
        }
        receipt = {**body, "receipt_hash": content_hash(body)}
        _write(public / "official_admission_rehearsal.json", receipt)
        write_m336k5_project_generated_marker(
            output,
            category="DISPOSABLE_PROTOCOL_CLONE",
            terminal_run_id=f"{request['disposable_label']}-{f_like}",
        )
        print(canonical_json(receipt))
        return
    if namespace == "m336k5":
        free_before_release = shutil.disk_usage(reservation_path.parent).free
        release_m336k5_storage_reservation(reservation_path)
        free_after_release = shutil.disk_usage(reservation_path.parent).free
        release_body = {
            "schema_version": 1,
            "contract_role": "PUBLIC_SAFE_M336K5_DISPOSABLE_RESERVATION_RELEASE",
            "storage_reservation_receipt_hash": reservation_receipt["receipt_hash"],
            "released_bytes": reservation_receipt["reservation_bytes"],
            "free_bytes_before_release": free_before_release,
            "free_bytes_after_release": free_after_release,
            "status": "PASS",
        }
        release_receipt = {
            **release_body,
            "receipt_hash": content_hash(release_body),
        }
        _write(release_receipt_path, release_receipt)
    execution_arguments = ["--request", str(final_request_path)]
    if namespace in {"m336k7", "m336k8"}:
        execution_arguments.extend(("--startup-receipt", str(startup_receipt_path)))
    if namespace in {"m336k7", "m336k8"}:
        execution_arguments.extend(
            (
                "--post-freeze-validation-receipt",
                str(validation_path),
                "--reservation-release-receipt",
                str(release_receipt_path),
            )
        )
    _run(python, repository, final_route_script, *execution_arguments)
    release_receipt = _object(release_receipt_path)
    monitor.sample("DISPOSABLE_FINAL_ROUTE_COMPLETE")
    e_like = _git(git, repository, "rev-parse", "HEAD^{commit}")
    h_like = _git(git, repository, "rev-parse", f"{e_like}^")
    contract = publication_contract_from_dict(_object(contract_path))
    protocol = verify_m336k2_commit_protocol(
        repository=repository,
        git_executable=git,
        exact_q28_sha=q_like,
        exact_f28_sha=f_like,
        exact_h28_sha=h_like,
        exact_e28_sha=e_like,
        contract=contract,
    )
    bundle = M336K5RouteIdentityBundle.from_dict(_object(bundle_path))
    route_receipt = _object(Path(final_request.route_receipt))
    observed = _identity_observations(
        repository,
        contract,
        route_receipt,
        bundle,
        final_request,
        _object(validation_path),
    )
    source_domain_evidence = {}
    current_full_source_identity = compute_m336j_project_source_identity(
        repository, git
    )
    persistent_full_source_identity = karina_preparation["project_source_identity"]
    if namespace == "m336k8":
        source_identity = M336K8ProjectSourceIdentityReceipt.from_dict(
            _object(
                _frozen_component(
                    repository, freeze, "controller_source_identity_receipt"
                )
            )
        )
        capsule_source = _object(
            _frozen_component(repository, freeze, "persistent_capsule_source_binding")
        )
        bridge = _object(
            _frozen_component(repository, freeze, "bridge_surface_manifest")
        )
        compatibility = _object(
            _frozen_component(repository, freeze, "source_domain_compatibility")
        )
        plan = M336K8FreezeAssemblyPlan.from_dict(
            _object(_frozen_component(repository, freeze, "freeze_assembly_plan"))
        )
        assembly = _object(
            _frozen_component(repository, freeze, "freeze_assembly_receipt")
        )
        gate = _object(
            _frozen_component(repository, freeze, "frozen_contract_compatibility_v2")
        )
        windows_source_identity = source_identity.live_project_source_identity
        karina_source_identity = source_identity.live_project_source_identity
        current_full_source_identity = windows_source_identity
        persistent_full_source_identity = capsule_source[
            "capsule_project_source_identity"
        ]
        source_domain_evidence = {
            "controller_source_identity_receipt_hash": source_identity.receipt_hash,
            "controller_startup_binding_hash": _object(
                _frozen_component(repository, freeze, "controller_startup_binding")
            )["binding_hash"],
            "persistent_capsule_source_binding_hash": capsule_source["binding_hash"],
            "source_domain_compatibility_receipt_hash": compatibility["receipt_hash"],
            "controller_capsule_full_identity_difference_count": compatibility[
                "full_project_identity_difference_count"
            ],
            "bridge_surface_manifest_hash": bridge["manifest_hash"],
            "bridge_tree_difference_count": int(
                bridge["controller_tree_hash"] != bridge["capsule_tree_hash"]
            ),
            "bridge_changed_entry_count": bridge["changed_entry_count"],
            "freeze_assembly_plan_hash": plan.plan_hash,
            "producer_origin_map_hash": plan.producer_origin_map_hash,
            "freeze_assembly_receipt_hash": assembly["receipt_hash"],
            "producer_origin_difference_count": assembly["wrong_origin_count"],
            "compatibility_gate_v2_hash": gate["report_hash"],
            "compatibility_semantic_check_count": gate["semantic_check_count"],
            "compatibility_semantic_mismatch_count": gate[
                "semantic_binding_mismatch_count"
            ],
            "rehearsal_official_assembly_plan_difference_count": 0,
            "rehearsal_official_producer_origin_difference_count": 0,
        }
    elif namespace == "m336k7":
        windows_source_identity, karina_source_identity = (
            _persistent_execution_source_identities(
                repository, Path(request["capsule_content_manifest"])
            )
        )
    else:
        windows_source_identity = current_full_source_identity
        karina_source_identity = persistent_full_source_identity
    source_identity_difference_count = int(
        windows_source_identity != karina_source_identity
    )
    if namespace == "m336k8":
        if source_identity_difference_count != 0:
            raise M336K2ProtocolError(
                "M336K8 current Windows/Karina source identity differs"
            )
        if (
            source_domain_evidence["controller_capsule_full_identity_difference_count"]
            != 1
        ):
            raise M336K2ProtocolError(
                "M336K8 controller/capsule source separation disappeared"
            )
    elif source_identity_difference_count:
        raise M336K2ProtocolError("M336K5 disposable platform source identity differs")
    monitor.stop("DISPOSABLE_FULL_CHAIN")
    maximum_private_bytes = max(
        sample.private_root_size_bytes for sample in monitor.samples
    )
    derived_storage_budget = max(2 * GIB, 2 * maximum_private_bytes)
    measured_budget = build_m336k5_resource_budget_receipt(
        monitor.samples,
        frozen_storage_budget_bytes=derived_storage_budget,
    )
    _write(public / "disposable_resource_budget.json", asdict(measured_budget))
    if measured_budget.status != "PASS":
        raise M336K2ProtocolError("M336K5 disposable resource budget failed")
    rehearsal_pool = _object(typed_output / "candidate_pool.json")
    body = {
        "schema_version": 1,
        "contract_role": (
            "PUBLIC_SAFE_M336K9_CONTROLLER_ADMISSION_FULL_ROUTE_REHEARSAL"
            if official_profile is not None
            else "PUBLIC_SAFE_M336K8_OFFICIAL_ISOMORPHIC_COMMITTED_FREEZE_REHEARSAL"
            if namespace == "m336k8"
            else "PUBLIC_SAFE_M336K7_EXACT_COMMITTED_FREEZE_REHEARSAL"
            if namespace == "m336k7"
            else "PUBLIC_SAFE_M336K5_DISPOSABLE_FINAL_MODE_PROOF"
        ),
        "implementation_tip": implementation,
        "q_like_sha": q_like,
        "f_like_sha": f_like,
        "h_like_sha": h_like,
        "e_like_sha": e_like,
        "freeze_build_receipt_hash": build["receipt_hash"],
        "f_attestation_hash": attestation.attestation_hash,
        "canonical_final_request_hash": final_request.request_hash,
        "disposable_controller_startup_receipt_hash": startup.receipt_hash,
        "resource_budget_receipt_hash": measured_budget.receipt_hash,
        "resource_sample_count": measured_budget.sample_count,
        "reservation_release_receipt_hash": release_receipt["receipt_hash"],
        "preledger_invocation_receipt_hash": _object(validation_path)["receipt_hash"],
        "identity_mutation_receipt_hash": mutation[
            "report_hash" if namespace == "m336k8" else "receipt_hash"
        ],
        "identity_mutation_case_count": mutation[
            "mutation_case_count" if namespace in {"m336k7", "m336k8"} else "case_count"
        ],
        "accepted_invalid_case_count": mutation["accepted_invalid_case_count"],
        "wrong_rejection_layer_count": mutation["wrong_rejection_layer_count"],
        "route_identity_bundle_hash": bundle.bundle_hash,
        "derived_protocol_run_id_hash": bundle.protocol_run_id.identity_hash,
        "external_route_run_id_absent": "route_run_id"
        not in final_request.canonical_object(),
        "execution_mode": bundle.execution_mode.value,
        "identity_observer_count": observed,
        "windows_project_source_identity": windows_source_identity,
        "karina_project_source_identity": karina_source_identity,
        "platform_source_identity_difference_count": source_identity_difference_count,
        "persistent_capsule_source_identity_is_explicit": namespace
        in {"m336k7", "m336k8"},
        "current_full_project_source_identity": current_full_source_identity,
        "persistent_capsule_full_project_source_identity": (
            persistent_full_source_identity
        ),
        "route_receipt_hash": route_receipt["receipt_hash"],
        "commit_protocol_receipt_hash": protocol["receipt_hash"],
        "source_leak_count": protocol["source_leak_count"],
        "absolute_path_count": protocol["absolute_path_count"],
        "private_public_artifact_count": protocol["private_artifact_count"],
        "official_one_shot_counter_count": 0,
        **(
            {
                "official_profile_id": official_profile.profile_id,
                "official_profile_status": official_profile.profile_status.value,
                "official_profile_hash": official_profile.profile_hash,
                "official_profile_registry_hash": m336k_official_profile_registry().registry_hash,
                "controller_admission_mutation_report_hash": admission_mutation[
                    "report_hash"
                ],
                "controller_admission_mutation_case_count": admission_mutation[
                    "mutation_case_count"
                ],
                "controller_admission_accepted_invalid_count": admission_mutation[
                    "accepted_invalid_count"
                ],
                "controller_admission_wrong_rejection_layer_count": admission_mutation[
                    "wrong_rejection_layer_count"
                ],
                "controller_admission_receipt_hash": _object(validation_path)[
                    "controller_admission_receipt_hash"
                ],
                "controller_admission_result": "PASS",
            }
            if official_profile is not None and admission_mutation is not None
            else {}
        ),
        **source_domain_evidence,
        **(
            {
                "final_candidate_pool_hash": final_candidate_pool["pool_hash"],
                "final_candidate_pool_bytes_hash": bytes_hash(
                    Path(request["candidate_pool"]).resolve(strict=True).read_bytes()
                ),
                "final_candidate_count": final_candidate_pool["candidate_count"],
                "final_organization_count": final_candidate_pool["organization_count"],
                "final_maximum_candidates_per_organization": final_candidate_pool[
                    "maximum_candidates_per_organization"
                ],
                "disposable_candidate_pool_hash": rehearsal_pool["pool_hash"],
                "final_source_body_bytes_before_f32": 0,
            }
            if final_candidate_pool is not None
            else {}
        ),
        "status": "PASS",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    _write(public / "disposable_protocol_receipt.json", receipt)
    write_m336k5_project_generated_marker(
        output,
        category="DISPOSABLE_PROTOCOL_CLONE",
        terminal_run_id=f"{request['disposable_label']}-{e_like}",
    )
    print(canonical_json(receipt))


def _apply_working_tree(
    source: Path, repository: Path, git: Path, base_sha: str
) -> None:
    patch = subprocess.run(
        (str(git), "diff", "--binary", base_sha),
        cwd=source,
        check=True,
        capture_output=True,
    ).stdout
    if patch:
        subprocess.run(
            (str(git), "apply", "--binary", "-"),
            cwd=repository,
            input=patch,
            check=True,
            capture_output=True,
        )
    untracked = _git(git, source, "ls-files", "--others", "--exclude-standard", "-z")
    for relative in (item for item in untracked.split("\0") if item):
        source_path = source / relative
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target)


def _persistent_execution_source_identities(
    repository: Path, content_manifest_path: Path
) -> tuple[str, str]:
    """Compare only source bytes that the preserved Karina capsule executes."""

    relative_paths = (
        "scripts/m336k5_python_bootstrap.py",
        "scripts/m336j_karina_execution.py",
    )
    manifest = _verified_receipt(
        content_manifest_path.resolve(strict=True), "manifest_hash"
    )
    entries = {
        item["relative_path"]: item["bytes_hash"] for item in manifest["entries"]
    }
    capsule_rows = tuple((name, entries[name]) for name in relative_paths)
    current_rows = tuple(
        (
            name,
            bytes_hash(repository.joinpath(*Path(name).parts).read_bytes()),
        )
        for name in relative_paths
    )
    if current_rows != capsule_rows:
        raise M336K2ProtocolError("M336K7 preserved capsule executable source changed")
    return content_hash(current_rows), content_hash(capsule_rows)


def _render_stage_template(
    value: dict,
    *,
    repository: Path,
    git: Path,
    python: Path,
    powershell: Path,
    implementation: str,
    f_like: str,
    freeze_root: Path,
    attestation: Path,
    runtime: Path,
    destinations: dict[str, str],
) -> dict:
    replacements = {
        "@IMPLEMENTATION_TIP@": implementation,
        "@F_SHA@": f_like,
        "@REPOSITORY@": str(repository),
        "@GIT_EXECUTABLE@": str(git),
        "@FREEZE_MANIFEST@": str(freeze_root / "freeze_manifest.json"),
        "@F28_ATTESTATION@": str(attestation),
        "@PRIVATE_ROOT@": str(runtime / "private"),
        "@STAGE_STATE@": str(runtime / "stage-state.json"),
        "@STAGE_RECEIPT_ROOT@": str(runtime / "stage-receipts"),
        "@ACQUISITION_LEDGER@": destinations["acquisition_ledger"],
        "@SELECTOR_LEDGER@": destinations["selector_ledger"],
        "@EVALUATOR_LEDGER@": destinations["evaluator_ledger"],
        "@ROUTE_LEDGER@": destinations["route_state_ledger"],
        "@VAULT@": destinations["vault"],
        "@SELECTED_SOURCE_SNAPSHOT@": destinations["selected_source_snapshot"],
        "@WINDOWS_PRODUCTION@": destinations["windows_production"],
        "@KARINA_PRODUCTION@": destinations["karina_production"],
        "@EVALUATOR_ROOT@": destinations["evaluator_root"],
    }
    freeze = _load_freeze(freeze_root / "freeze_manifest.json")
    for component in freeze.components:
        replacements[f"@COMPONENT_{component.name.upper()}@"] = str(
            repository.joinpath(*Path(component.relative_path).parts)
        )
    result = _replace(value, replacements)
    result["python_executable"] = str(python)
    result["git_executable"] = str(git)
    result["executable_handles"]["python"] = str(python)
    result["executable_handles"]["git"] = str(git)
    result["executable_handles"]["powershell"] = str(powershell)
    return result


def _identity_observations(
    repository, contract, route_receipt, bundle, final_request, validation
) -> int:
    if (
        route_receipt.get("route_identity_bundle_hash") != bundle.bundle_hash
        or route_receipt.get("protocol_run_id")
        != bundle.protocol_run_id.canonical_object()
    ):
        raise M336K2ProtocolError("M336K5 controller identity observation differs")
    verified = 1
    verify_m336k5_route_ledger_identity(
        M336K2RouteLedger(
            Path(final_request.route_ledger), git_worktrees=(repository,)
        ),
        bundle=bundle,
        exact_f30_sha=final_request.exact_f30_sha,
        preledger_receipt_hash=validation["receipt_hash"],
    )
    verified += 1
    private = Path(final_request.private_root)
    authorization = m336k_current_final_authorization_from_dict(
        _object(Path(final_request.final_authorization))
    )
    freeze = _load_freeze(Path(final_request.freeze_manifest))
    pool = _object(_frozen_component(repository, freeze, "candidate_pool"))
    acquisition_receipt = _object(private / "acquisition_public_receipt.json")
    if (
        acquisition_receipt.get("protocol_run_id")
        != bundle.protocol_run_id.canonical_object()
        or acquisition_receipt.get("acquisition_run_id_typed")
        != bundle.acquisition_run_id.canonical_object()
        or acquisition_receipt.get("route_identity_bundle_hash") != bundle.bundle_hash
    ):
        raise M336K2ProtocolError("M336K5 acquisition identity observation differs")
    verify_m336k5_acquisition_ledger_identity(
        M336KAcquisitionLedger(
            Path(final_request.final_destinations["acquisition_ledger"]),
            git_worktrees=(repository,),
        ),
        bundle=bundle,
        exact_f30_sha=final_request.exact_f30_sha,
        authorization_hash=authorization.authorization_hash,
        candidate_pool_hash=pool["pool_hash"],
    )
    verified += 1
    qualification = _object(private / "candidate_qualification.json")
    summary = _object(private / "compilation-closure" / "qualification_summary.json")
    census = _object(private / "selectability_census.json")
    closure = _object(
        private / "compilation-closure" / "compilation_closure_manifest.json"
    )
    proof = _object(
        private / "compilation-closure" / "compilation_closure_feasibility.json"
    )
    bindings = _object(private / "source_entry_binding_manifest.json")
    verify_m336k5_selector_ledger_identity(
        M336FSelectorLedger(
            Path(final_request.final_destinations["selector_ledger"]),
            git_worktrees=(repository,),
        ),
        bundle=bundle,
        qualification_report_hash=qualification["report_hash"],
        qualification_summary_hash=summary["summary_hash"],
        census_hash=census["census_hash"],
        closure_manifest_hash=closure["manifest_hash"],
        feasibility_proof_hash=proof["proof_hash"],
        binding_manifest_hash=bindings["manifest_hash"],
    )
    verified += 1
    h_commit = _object(private / "h28_commit_receipt.json")["exact_h28_sha"]
    windows_seal = _object(
        Path(final_request.final_destinations["windows_production"])
        / "m336i_production_seal.json"
    )["seal_hash"]
    karina_seal = _object(
        Path(final_request.final_destinations["karina_production"])
        / "m336i_production_seal.json"
    )["seal_hash"]
    verify_m336k5_evaluator_ledger_identity(
        Path(final_request.final_destinations["evaluator_ledger"]),
        bundle=bundle,
        exact_h30_sha=h_commit,
        windows_production_seal_hash=windows_seal,
        karina_production_seal_hash=karina_seal,
    )
    verified += 1
    for relative in (
        f"{contract.h_root}/route_identity_observation.json",
        f"{contract.e_root}/route_identity_observation.json",
    ):
        value = _object(repository.joinpath(*Path(relative).parts))
        _verify_identity_observation(value, bundle)
        verified += 1
    if verified != 7:
        raise M336K2ProtocolError("M336K5 identity observer closure changed")
    return verified


def _verify_identity_observation(value: dict, bundle) -> None:
    body = dict(value)
    claimed = body.pop("receipt_hash", None)
    if (
        content_hash(body) != claimed
        or value.get("route_version") != bundle.route_version.canonical_object()
        or value.get("protocol_run_id") != bundle.protocol_run_id.canonical_object()
        or value.get("acquisition_run_id")
        != bundle.acquisition_run_id.canonical_object()
        or value.get("selector_run_id") != bundle.selector_run_id.canonical_object()
        or value.get("evaluator_run_id") != bundle.evaluator_run_id.canonical_object()
        or value.get("execution_mode") != bundle.execution_mode.canonical_object()
        or value.get("route_identity_bundle_hash") != bundle.bundle_hash
        or value.get("status") != "PASS"
    ):
        raise M336K2ProtocolError("M336K5 publication identity observation differs")


def _frozen_component(repository: Path, freeze, name: str) -> Path:
    rows = [item for item in freeze.components if item.name == name]
    if len(rows) != 1:
        raise M336K2ProtocolError("M336K5 disposable frozen component lookup failed")
    return repository.joinpath(*Path(rows[0].relative_path).parts).resolve(strict=True)


def _load_freeze(path: Path):
    value = _object(path)
    if value.get("contract_role") in {
        M336K8FreezeManifest.ROLE,
        M336K8FreezeManifest.ROLE_V2,
        M336K8FreezeManifest.ROLE_V3,
    }:
        return M336K8FreezeManifest.from_dict(value)
    if value.get("contract_role") == "M336K7_F32_TYPED_FREEZE_V1":
        return M336K7FreezeManifest.from_dict(value)
    return M336K5FreezeManifest.from_dict(value)


def _q_manifest(root: Path) -> dict:
    rows = tuple(
        (
            path.relative_to(root).as_posix(),
            path.stat().st_size,
            bytes_hash(path.read_bytes()),
        )
        for path in root.rglob("*")
        if path.is_file()
    )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K5_DISPOSABLE_Q_LIKE_MANIFEST",
        "files": tuple(sorted(rows)),
        "file_count": len(rows),
        "tree_hash": content_hash(tuple(sorted(rows))),
        "source_leak_count": 0,
        "absolute_path_count": 0,
        "private_artifact_count": 0,
        "status": "PASS",
    }
    return {**body, "manifest_hash": content_hash(body)}


def _commit(git: Path, repository: Path, subject: str, relative: str) -> str:
    _git(git, repository, "add", "-f", "--", relative)
    _git(git, repository, "commit", "-m", subject)
    return _git(git, repository, "rev-parse", "HEAD^{commit}")


def _configure_launcher(git: Path, powershell: Path, receipts: Path) -> None:
    global _LAUNCH_GIT, _LAUNCH_POWERSHELL, _LAUNCH_RECEIPTS, _LAUNCH_SEQUENCE
    _LAUNCH_GIT = git
    _LAUNCH_POWERSHELL = powershell
    _LAUNCH_RECEIPTS = receipts
    _LAUNCH_SEQUENCE = 0


def _run(python: Path, repository: Path, script: str, *arguments: str) -> None:
    global _LAUNCH_SEQUENCE
    if _LAUNCH_GIT is None or _LAUNCH_POWERSHELL is None or _LAUNCH_RECEIPTS is None:
        raise RuntimeError("M336K5 disposable launcher is not configured")
    _LAUNCH_SEQUENCE += 1
    root = _LAUNCH_RECEIPTS / f"{_LAUNCH_SEQUENCE:03d}"
    target = repository / script
    final_cli = script in {
        "scripts/m336k5_run_final_route.py",
        "scripts/m336k7_run_final_route.py",
        "scripts/m336k8_run_final_route.py",
    }
    target_arguments = tuple(arguments)
    if (
        script == "scripts/m336k8_run_final_route.py"
        and "--startup-receipt" not in target_arguments
    ):
        target_arguments += ("--startup-receipt", str(root / "startup.json"))
    role = (
        "VALIDATE_ONLY"
        if final_cli and "--validate-only" in arguments
        else "FINAL_CONTROLLER"
        if final_cli
        else "DISPOSABLE_CONTROLLER"
        if script
        in {
            "scripts/m336k5_run_identity_mutations.py",
            "scripts/m336k7_run_contract_mutations.py",
            "scripts/m336k8_run_contract_mutations.py",
            "scripts/m336k9_run_admission_mutations.py",
        }
        else "BUILD_HELPER"
    )
    plan = build_m336k5_python_invocation(
        platform_role="WINDOWS",
        process_role=role,
        python_executable=python,
        git_executable=_LAUNCH_GIT,
        powershell_executable=_LAUNCH_POWERSHELL,
        repository=repository,
        working_directory=repository,
        bootstrap_script=repository / "scripts/m336k5_python_bootstrap.py",
        target=target,
        execute_arguments=target_arguments,
        validate_arguments=target_arguments,
        execute_startup_receipt=root / "startup.json",
        validate_startup_receipt=root / "startup-validate.json",
    )
    plan_path = root / "invocation-plan.json"
    write_m336k5_python_invocation_plan(plan, plan_path)
    result = run_m336k5_python_invocation(plan_path=plan_path, operation="execute")
    if result.returncode:
        (root / "failure.stdout.log").write_bytes(result.stdout)
        (root / "failure.stderr.log").write_bytes(result.stderr)
        raise subprocess.CalledProcessError(
            result.returncode,
            (script, *arguments),
            output=result.stdout,
            stderr=result.stderr,
        )


def _git(git: Path, repository: Path | None, *arguments: str) -> str:
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


def _hashed(field: str, **body) -> dict:
    return {**body, field: content_hash(body)}


def _replace(value, replacements: dict[str, str]):
    if isinstance(value, dict):
        return {key: _replace(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace(item, replacements) for item in value]
    if isinstance(value, str):
        for old, new in replacements.items():
            value = value.replace(old, new)
    return value


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _object(path: Path) -> dict:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K5 disposable JSON input is not an object")
    return value


def _verified_receipt(path: Path, hash_field: str) -> dict:
    value = _object(path)
    body = dict(value)
    claimed = body.pop(hash_field, None)
    if not isinstance(claimed, str) or content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K5 disposable receipt hash changed")
    return value


if __name__ == "__main__":
    main()
