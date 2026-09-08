"""Build the future immutable M-33.6j F25 freeze without acquiring source."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path, PurePosixPath

from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)
from ai_brain.stage3.acquisition.m336j_execution import (
    dependency_manifest_from_dict,
    public_execution_capsule_receipt_from_dict,
)
from ai_brain.stage3.acquisition.m336j_freeze import (
    M336J_ACQUISITION_RUN_ID,
    M336J_BRANCH_REF,
    M336J_EXACT_F24_SHA,
    M336J_EXACT_Q23_SHA,
    M336J_FREEZE_MANIFEST_PATH,
    M336J_FREEZE_ROOT,
    M336J_FROZEN_AUTHORIZATION_PATH,
    build_m336j_final_acquisition_authorization,
    compute_m336j_freeze_tree_identity,
)
from ai_brain.stage3.acquisition.m336j_future import (
    build_m336j_future_orchestration_manifest,
)
from ai_brain.stage3.acquisition.m336j_readiness import readiness_result_from_dict
from ai_brain.stage3.acquisition.m336j_registry import (
    build_m336j_route_manifest,
    build_m336j_route_registry,
    command_renderer_identity_hash,
)
from ai_brain.stage3.acquisition.m336j_schemas import build_public_schema_registry

_REQUEST_FIELDS = {
    "repository",
    "exact_q25_sha",
    "exact_r25b_sha",
    "readiness",
    "public_capsule_receipt",
    "executable_dependency_manifest",
    "authorization_values",
    "freeze_files",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = _object(args.request)
    if set(request) != _REQUEST_FIELDS:
        raise ValueError("M336J F25 request fields changed")
    repository = Path(request["repository"]).resolve(strict=True)
    q25 = request["exact_q25_sha"]
    r25b = request["exact_r25b_sha"]
    if (
        _git(repository, "rev-parse", "HEAD^{commit}") != q25
        or _git(repository, "rev-parse", "HEAD^1") != r25b
        or _git(repository, "rev-parse", "HEAD^2")
        != "b05ac235b291acbb514cb8256302610964042d3f"
        or _git(repository, "rev-parse", "HEAD^3") != M336J_EXACT_F24_SHA
        or _git(repository, "status", "--porcelain=v1")
        or int(
            _git(
                repository,
                "rev-list",
                "--count",
                "--merges",
                f"{M336J_EXACT_F24_SHA}..HEAD",
            )
        )
    ):
        raise ValueError("M336J F25 requires clean exact Q25 linear ancestry")
    readiness = readiness_result_from_dict(_object(Path(request["readiness"])))
    if readiness.exact_r25_sha != r25b:
        raise ValueError("M336J F25 readiness is not bound to exact R25b")
    output = repository / M336J_FREEZE_ROOT
    if output.exists():
        raise FileExistsError("M336J F25 freeze root must be fresh")
    capsule = public_execution_capsule_receipt_from_dict(
        _object(Path(request["public_capsule_receipt"]))
    )
    dependencies = dependency_manifest_from_dict(
        _object(Path(request["executable_dependency_manifest"]))
    )
    registry = build_m336j_route_registry()
    route = build_m336j_route_manifest(
        registry,
        execution_capsule_public_receipt_hash=capsule.receipt_hash,
        remote_command_renderer_hash=command_renderer_identity_hash(),
        executable_dependency_manifest_hash=dependencies.manifest_hash,
        minimal_environment_policy_hash=capsule.minimal_environment_policy_hash,
    )
    output.mkdir(parents=True)
    write_canonical_json(output / "route_component_registry.json", registry)
    write_canonical_json(output / "route_manifest.json", route)
    write_canonical_json(output / "remote_schemas.json", build_public_schema_registry())
    write_canonical_json(
        output / "future_orchestration_manifest.json",
        build_m336j_future_orchestration_manifest(),
    )
    freeze_files = request["freeze_files"]
    if not isinstance(freeze_files, dict) or not freeze_files:
        raise ValueError("M336J F25 frozen file set is empty")
    for name, raw_source in sorted(freeze_files.items()):
        relative = PurePosixPath(name)
        if relative.is_absolute() or any(
            part in {"", ".", ".."} for part in relative.parts
        ):
            raise ValueError("M336J F25 frozen file destination is unsafe")
        source = Path(raw_source).resolve(strict=True)
        if not source.is_file():
            raise ValueError("M336J F25 frozen input is not a file")
        destination = output.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    freeze_identity = compute_m336j_freeze_tree_identity(repository)
    supplied = request["authorization_values"]
    if not isinstance(supplied, dict):
        raise TypeError("M336J F25 authorization values must be an object")
    authorization = build_m336j_final_acquisition_authorization(
        **{
            **supplied,
            "acquisition_mode": "FINAL",
            "exact_q23_sha": M336J_EXACT_Q23_SHA,
            "r24_implementation_tree_identity": (
                readiness.r25_implementation_tree_identity
            ),
            "q24_evidence_identity": readiness.q25_evidence_identity,
            "f24_parent_sha": q25,
            "f24_freeze_tree_identity": freeze_identity,
            "route_registry_hash": registry.registry_hash,
            "route_manifest_hash": route.manifest_hash,
            "acquisition_run_id": M336J_ACQUISITION_RUN_ID,
            "branch_ref": M336J_BRANCH_REF,
        }
    )
    write_canonical_json(repository / M336J_FROZEN_AUTHORIZATION_PATH, authorization)
    freeze_body = {
        "schema_version": 1,
        "contract_role": "M336J_IMMUTABLE_FINAL_FREEZE",
        "exact_q25_sha": q25,
        "exact_r25b_sha": r25b,
        "freeze_tree_identity": freeze_identity,
        "authorization_hash": authorization.authorization_hash,
        "route_registry_hash": registry.registry_hash,
        "route_manifest_hash": route.manifest_hash,
        "final_acquisition_reservation_count": 0,
        "final_acquisition_invocation_count": 0,
        "status": "F25_READY_TO_COMMIT",
    }
    write_canonical_json(repository / M336J_FREEZE_MANIFEST_PATH, freeze_body)
    if compute_m336j_freeze_tree_identity(repository) != freeze_identity:
        raise ValueError(
            "M336J F25 freeze identity changed after self-excluded outputs"
        )
    print(json.dumps(freeze_body, sort_keys=True, separators=(",", ":")))


def _object(path: Path) -> dict:
    value = strict_json_file(path.resolve(strict=True))
    if not isinstance(value, dict):
        raise TypeError("M336J F25 input must be an object")
    return value


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


if __name__ == "__main__":
    main()
