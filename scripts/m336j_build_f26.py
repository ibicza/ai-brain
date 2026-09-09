"""Build the typed M-33.6j.3 F26 freeze without spending one-shot capacity."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass, fields
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)
from ai_brain.stage3.acquisition.m336i_acquisition import acquisition_provider_identity
from ai_brain.stage3.acquisition.m336j_execution import (
    dependency_manifest_from_dict,
    public_execution_capsule_receipt_from_dict,
)
from ai_brain.stage3.acquisition.m336j_final_v2 import (
    M336J3_AUTHORIZATION_PATH,
    M336J3_FREEZE_MANIFEST_PATH,
    M336J3_FREEZE_ROOT,
    M336J3_FROZEN_FILE_MANIFEST_PATH,
    build_m336j_f26_frozen_file_manifest,
    build_m336j_final_authorization_v2,
    build_m336j_final_freeze_manifest_v2,
    build_m336j_git_executable_receipt_v2,
    compute_m336j_freeze_tree_identity_v2,
    compute_m336j_q26_staging_tree_hash,
    dump_m336j_f26_frozen_file_manifest,
    dump_m336j_final_authorization_v2,
    dump_m336j_final_freeze_manifest_v2,
    load_m336j_f26_frozen_file_manifest,
    load_m336j_final_authorization_input_v2,
    resolve_m336j_f26_frozen_sources,
    verify_m336j_authorization_manifest_cross_bindings_v2,
    verify_m336j_pre_freeze_lineage_v2,
)
from ai_brain.stage3.acquisition.m336j_readiness import readiness_result_from_dict
from ai_brain.stage3.acquisition.m336j_registry import (
    build_m336j_route_manifest,
    build_m336j_route_registry,
    command_renderer_identity_hash,
)
from ai_brain.stage3.acquisition.m336j_schemas import build_public_schema_registry


@dataclass(frozen=True)
class M336JF26BuildRequest:
    repository: Path
    git_executable: Path
    exact_q26_sha: str
    exact_r26_sha: str
    q26_staging_tree_hash: str
    readiness: Path
    public_capsule_receipt: Path
    python_environment_manifest: Path
    executable_dependency_manifest: Path
    spdx_binding: Path
    authorization_input: Path
    frozen_file_manifest: Path


def load_m336j_f26_build_request(path: Path) -> M336JF26BuildRequest:
    value = _object(path)
    expected = {item.name for item in fields(M336JF26BuildRequest)}
    if set(value) != expected:
        raise ValueError("M336J F26 request fields changed")
    path_fields = expected - {
        "exact_q26_sha",
        "exact_r26_sha",
        "q26_staging_tree_hash",
    }
    if any(not isinstance(value[name], str) for name in expected):
        raise TypeError("M336J F26 request values must be JSON strings")
    return M336JF26BuildRequest(
        **{
            name: Path(item) if name in path_fields else item
            for name, item in value.items()
        }
    )


def materialize_m336j_f26_prospective_tree(
    *,
    repository: Path,
    frozen_files,
    frozen_sources: dict[str, Path],
    capsule,
    dependencies,
):
    """Materialize the deterministic self-excluded F26 base tree."""

    output = repository / M336J3_FREEZE_ROOT
    if output.exists():
        raise FileExistsError("M336J F26 freeze root must be fresh")
    output.mkdir(parents=True)
    (repository / M336J3_FROZEN_FILE_MANIFEST_PATH).write_bytes(
        dump_m336j_f26_frozen_file_manifest(frozen_files)
    )
    for row in frozen_files.files:
        source = frozen_sources[row.destination_path]
        destination = output.joinpath(*row.destination_path.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if bytes_hash(destination.read_bytes()) != row.bytes_hash:
            raise ValueError("M336J F26 frozen input copy changed bytes")
    registry = build_m336j_route_registry()
    route = build_m336j_route_manifest(
        registry,
        execution_capsule_public_receipt_hash=capsule.receipt_hash,
        remote_command_renderer_hash=command_renderer_identity_hash(),
        executable_dependency_manifest_hash=dependencies.manifest_hash,
        minimal_environment_policy_hash=capsule.minimal_environment_policy_hash,
    )
    write_canonical_json(output / "route_component_registry.json", registry)
    write_canonical_json(output / "route_manifest.json", route)
    write_canonical_json(output / "remote_schemas.json", build_public_schema_registry())
    orchestration = {
        "schema_version": 2,
        "contract_role": "M336J_F26_H26_E26_ORCHESTRATION",
        "f26_builder": "scripts/m336j_build_f26.py",
        "final_controller": "scripts/m336i_java_final_route.py",
        "h26_publisher": "scripts/m336j_publish_h26.py",
        "e26_publisher": "scripts/m336j_publish_e26.py",
        "production_seals_precede_golden_generation": True,
        "evaluator_execution_may_precede_h26_commit": True,
        "h26_contains_only_sealed_production_subset": True,
    }
    write_canonical_json(
        output / "future_orchestration_manifest_v2.json",
        {
            **orchestration,
            "manifest_hash": content_hash(orchestration),
        },
    )
    return output, registry, route


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = load_m336j_f26_build_request(args.request)
    repository = request.repository.resolve(strict=True)
    git = request.git_executable.resolve(strict=True)
    q26 = request.exact_q26_sha
    r26 = request.exact_r26_sha
    verify_m336j_pre_freeze_lineage_v2(
        repository, git, exact_r26_sha=r26, exact_q26_sha=q26
    )
    staging_hash = compute_m336j_q26_staging_tree_hash(
        repository, git, exact_r26_sha=r26, exact_q26_sha=q26
    )
    if staging_hash != request.q26_staging_tree_hash:
        raise ValueError("M336J F26 Q26 staging identity changed")
    readiness = readiness_result_from_dict(_object(request.readiness))
    if readiness.status != "READY_FOR_HERMETIC_FINAL_ACQUISITION":
        raise ValueError("M336J F26 readiness is not exact Q25 PASS")
    capsule = public_execution_capsule_receipt_from_dict(
        _object(request.public_capsule_receipt)
    )
    dependencies = dependency_manifest_from_dict(
        _object(request.executable_dependency_manifest)
    )
    python_environment = _verified_object(
        request.python_environment_manifest, "identity_hash"
    )
    spdx_binding = _verified_object(request.spdx_binding, "spdx_reference_binding_hash")
    frozen_files = load_m336j_f26_frozen_file_manifest(request.frozen_file_manifest)
    expected_frozen_files = build_m336j_f26_frozen_file_manifest(
        repository,
        acquisition_mode=frozen_files.acquisition_mode,
        readiness=request.readiness,
        public_capsule_receipt=request.public_capsule_receipt,
        python_environment_manifest=request.python_environment_manifest,
        executable_dependency_manifest=request.executable_dependency_manifest,
        spdx_binding=request.spdx_binding,
    )
    if frozen_files != expected_frozen_files:
        raise ValueError("M336J F26 frozen file manifest differs from named inputs")
    frozen_sources = resolve_m336j_f26_frozen_sources(
        repository,
        acquisition_mode=frozen_files.acquisition_mode,
        readiness=request.readiness,
        public_capsule_receipt=request.public_capsule_receipt,
        python_environment_manifest=request.python_environment_manifest,
        executable_dependency_manifest=request.executable_dependency_manifest,
        spdx_binding=request.spdx_binding,
    )
    output, registry, route = materialize_m336j_f26_prospective_tree(
        repository=repository,
        frozen_files=frozen_files,
        frozen_sources=frozen_sources,
        capsule=capsule,
        dependencies=dependencies,
    )
    freeze_identity = compute_m336j_freeze_tree_identity_v2(repository, git)
    authorization_input = load_m336j_final_authorization_input_v2(
        request.authorization_input
    )
    if frozen_files.acquisition_mode != authorization_input.acquisition_mode:
        raise ValueError("M336J F26 frozen files differ from authorization mode")
    expected = _expected_authorization_values(
        output=output,
        q26=q26,
        r26=r26,
        staging_hash=staging_hash,
        freeze_identity=freeze_identity,
        capsule=capsule,
        dependencies=dependencies,
        python_environment=python_environment,
        spdx_binding=spdx_binding,
        registry=registry,
        route=route,
    )
    if any(
        getattr(authorization_input, name) != value for name, value in expected.items()
    ):
        raise ValueError(
            "M336J F26 typed authorization input differs from frozen inputs"
        )
    policy = _object(output / "acquisition_policy.json")
    if (
        tuple(policy["allowed_network_hosts"])
        != authorization_input.allowed_network_hosts
        or policy["acquisition_run_id"] != authorization_input.acquisition_run_id
    ):
        raise ValueError("M336J F26 policy/authorization run or host binding changed")
    authorization = build_m336j_final_authorization_v2(authorization_input)
    manifest = build_m336j_final_freeze_manifest_v2(authorization=authorization)
    verify_m336j_authorization_manifest_cross_bindings_v2(authorization, manifest)
    (repository / M336J3_AUTHORIZATION_PATH).write_bytes(
        dump_m336j_final_authorization_v2(authorization)
    )
    (repository / M336J3_FREEZE_MANIFEST_PATH).write_bytes(
        dump_m336j_final_freeze_manifest_v2(manifest)
    )
    if compute_m336j_freeze_tree_identity_v2(repository, git) != freeze_identity:
        raise ValueError("M336J F26 self-excluded freeze identity changed")
    leak_counts = _scan_public_freeze_tree(output)
    git_receipt = build_m336j_git_executable_receipt_v2(
        git,
        execution_capsule_public_receipt_hash=capsule.receipt_hash,
        environment_identity_hash=python_environment["environment_manifest_hash"],
    )
    rows = tuple(
        (path.relative_to(repository).as_posix(), bytes_hash(path.read_bytes()))
        for path in sorted(
            (item for item in output.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(repository).as_posix().encode("utf-8"),
        )
    )
    receipt_body = {
        "schema_version": 2,
        "contract_role": "M336J_F26_STAGING_RECEIPT_V2",
        "exact_q26_sha": q26,
        "exact_r26_sha": r26,
        "q26_staging_tree_hash": staging_hash,
        "freeze_tree_identity": freeze_identity,
        "authorization_hash": authorization.authorization_hash,
        "freeze_manifest_hash": manifest.manifest_hash,
        "git_executable_receipt_hash": git_receipt.receipt_hash,
        "frozen_file_manifest_hash": frozen_files.manifest_hash,
        "prospective_file_count": len(rows),
        "prospective_tree_content_hash": content_hash(rows),
        "network_access_count": 0,
        "one_shot_ledger_write_count": 0,
        "source_body_byte_count": 0,
        "source_leak_count": leak_counts["source_leak_count"],
        "absolute_public_path_count": leak_counts["absolute_public_path_count"],
        "private_artifact_count": leak_counts["private_artifact_count"],
        "status": "F26_READY_TO_COMMIT",
    }
    print(
        json.dumps(
            {**receipt_body, "receipt_hash": content_hash(receipt_body)},
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _expected_authorization_values(
    *,
    output,
    q26,
    r26,
    staging_hash,
    freeze_identity,
    capsule,
    dependencies,
    python_environment,
    spdx_binding,
    registry,
    route,
) -> dict:
    source_hash, signature_hash = acquisition_provider_identity()
    policy = _verified_object(
        output / "acquisition_policy.json", "acquisition_policy_hash"
    )
    denylist = _verified_object(output / "denylist.json", "denylist_hash")
    authority = _verified_object(output / "authority_root.json", "authority_root_hash")
    selector = _verified_object(output / "selector_policy.json", "selector_policy_hash")
    thresholds = _verified_object(
        output / "threshold_manifest.json", "threshold_manifest_hash"
    )
    publication = _verified_object(
        output / "publication_boundary_contract.json",
        "publication_boundary_policy_hash",
    )
    public_contract = _verified_object(
        output / "public_artifact_contract.json", "public_artifact_contract_hash"
    )
    jdk = _verified_object(
        output / "compiler_jdk_identities.json", "compiler_jdk_identities_hash"
    )
    karina_host = _verified_object(
        output / "karina_host_identity_receipt.json", "receipt_hash"
    )
    return {
        "exact_q26_sha": q26,
        "exact_r26_sha": r26,
        "q26_staging_tree_hash": staging_hash,
        "prospective_f26_freeze_identity": freeze_identity,
        "route_registry_hash": registry.registry_hash,
        "route_manifest_hash": route.manifest_hash,
        "acquisition_provider_source_hash": source_hash,
        "acquisition_provider_callable_signature_hash": signature_hash,
        "candidate_pool_hash": _object(output / "candidate_pool.json")["pool_hash"],
        "acquisition_policy_hash": policy["acquisition_policy_hash"],
        "denylist_hash": denylist["denylist_hash"],
        "authority_root_hash": authority["authority_root_hash"],
        "selector_policy_hash": selector["selector_policy_hash"],
        "threshold_manifest_hash": thresholds["threshold_manifest_hash"],
        "publication_boundary_hash": publication["publication_boundary_policy_hash"],
        "public_artifact_contract_hash": public_contract[
            "public_artifact_contract_hash"
        ],
        "spdx_reference_binding_hash": spdx_binding["spdx_reference_binding_hash"],
        "execution_capsule_public_receipt_hash": capsule.receipt_hash,
        "python_environment_manifest_hash": python_environment[
            "environment_manifest_hash"
        ],
        "executable_dependency_manifest_hash": dependencies.manifest_hash,
        "remote_command_renderer_hash": command_renderer_identity_hash(),
        "minimal_environment_policy_hash": capsule.minimal_environment_policy_hash,
        "windows_public_jdk_identity_receipt_hash": jdk[
            "windows_public_jdk_receipt_hash"
        ],
        "karina_public_jdk_identity_receipt_hash": jdk[
            "karina_public_jdk_receipt_hash"
        ],
        "karina_stable_host_identity_receipt_hash": karina_host["receipt_hash"],
    }


def _object(path: Path) -> dict:
    value = strict_json_file(path.resolve(strict=True))
    if not isinstance(value, dict):
        raise TypeError("M336J F26 input must be an object")
    return value


def _verified_object(path: Path, hash_field: str) -> dict:
    value = _object(path)
    body = dict(value)
    claimed = body.pop(hash_field, None)
    if content_hash(body) != claimed:
        raise ValueError(f"M336J F26 {hash_field} differs from content")
    return value


def _scan_public_freeze_tree(root: Path) -> dict[str, int]:
    source_leaks = 0
    absolute_paths = 0
    private_artifacts = 0
    absolute_pattern = re.compile(r"(?:^|[\s\"'])[A-Za-z]:[\\/]|/(?:home|Users|root)/")
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix().casefold()
        source_leaks += path.suffix.casefold() == ".java"
        private_artifacts += any(
            token in relative for token in ("private", "secret", "credential", "vault")
        )
        if path.suffix.casefold() in {".json", ".txt", ".md"}:
            absolute_paths += bool(
                absolute_pattern.search(path.read_text(encoding="utf-8"))
            )
    if source_leaks or absolute_paths or private_artifacts:
        raise ValueError("M336J F26 prospective public tree leaks private material")
    return {
        "source_leak_count": source_leaks,
        "absolute_public_path_count": absolute_paths,
        "private_artifact_count": private_artifacts,
    }


if __name__ == "__main__":
    main()
