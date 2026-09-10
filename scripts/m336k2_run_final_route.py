"""Run the complete frozen M-33.6k.2 route from one typed controller."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_acquisition import (
    authorization_from_dict,
    verify_m336k2_final_authorization,
)
from ai_brain.stage3.acquisition.m336k2_controller import (
    build_preledger_proof,
    run_m336k2_final_controller,
)
from ai_brain.stage3.acquisition.m336k2_execution import (
    M336K2HermeticCommandWorker,
    build_m336k2_native_execution_plan,
    executable_dependency_manifest_from_dict,
    execution_capsule_receipt_from_dict,
    verify_m336k2_executable_handles,
    verify_m336k2_python_environment_manifest,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2CommittedFreezeAttestation,
    M336K2FreezeManifest,
    M336K2FrozenComponent,
    M336K2ProtocolError,
    M336K2RouteLedger,
    verify_complete_freeze,
)
from ai_brain.stage3.acquisition.m336k2_readiness import (
    readiness_from_dict,
    verify_m336k2_readiness_destinations,
)
from ai_brain.stage3.acquisition.m336k2_registry import (
    build_m336k2_route_registry,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = _object(args.request.resolve(strict=True))
    expected = {
        "repository",
        "git_executable",
        "python_executable",
        "exact_f28_sha",
        "freeze_manifest",
        "f28_attestation",
        "final_authorization",
        "route_ledger",
        "route_receipt",
        "route_run_id",
        "execution_mode",
        "stage_request",
        "stage_receipt_root",
    }
    if set(request) != expected:
        raise M336K2ProtocolError("M336K2 final controller request fields changed")
    repository = Path(request["repository"]).resolve(strict=True)
    git_executable = Path(request["git_executable"]).resolve(strict=True)
    freeze = _freeze(Path(request["freeze_manifest"]).resolve(strict=True))
    attestation = _attestation(Path(request["f28_attestation"]).resolve(strict=True))
    authorization = authorization_from_dict(
        _object(Path(request["final_authorization"]).resolve(strict=True))
    )
    exact_f28 = request["exact_f28_sha"]
    route_registry = build_m336k2_route_registry(repository)
    worktrees = _worktrees(repository, git_executable)
    ledger = M336K2RouteLedger(Path(request["route_ledger"]), git_worktrees=worktrees)
    executable_component = _component(freeze, "executable_dependency_manifest")
    executable_manifest = executable_dependency_manifest_from_dict(
        _object(repository.joinpath(*executable_component.relative_path.split("/")))
    )
    capsule_component = _component(freeze, "execution_capsule_receipt")
    capsule = execution_capsule_receipt_from_dict(
        _object(repository.joinpath(*capsule_component.relative_path.split("/")))
    )
    plan = build_m336k2_native_execution_plan(
        repository=repository,
        python_executable=Path(request["python_executable"]),
        stage_request=Path(request["stage_request"]),
        stage_receipt_root=Path(request["stage_receipt_root"]),
        route_run_id=request["route_run_id"],
        exact_f28_sha=exact_f28,
        route_registry_hash=route_registry.registry_hash,
        dependency_manifest=executable_manifest,
        capsule=capsule,
    )
    stage_request = _object(Path(request["stage_request"]).resolve(strict=True))
    handles = stage_request.get("executable_handles")
    if not isinstance(handles, dict):
        raise M336K2ProtocolError("M336K2 stage executable handles are missing")
    verify_m336k2_executable_handles(
        executable_manifest,
        {name: Path(path) for name, path in handles.items()},
    )
    if Path(handles.get("git", "")).resolve(strict=False) != git_executable or Path(
        handles.get("python", "")
    ).resolve(strict=False) != Path(request["python_executable"]).resolve(strict=True):
        raise M336K2ProtocolError("M336K2 controller executable handles differ")
    if Path(
        stage_request.get("final_destinations", {}).get("route_state_ledger", "")
    ).resolve(strict=False) != Path(request["route_ledger"]).resolve(strict=False):
        raise M336K2ProtocolError("M336K2 controller and stage ledger handles differ")

    def preledger_guard():
        verify_complete_freeze(repository, freeze, allow_prospective_f28=True)
        verify_m336k2_final_authorization(authorization)
        environment_component = _component(freeze, "python_environment_manifest")
        verify_m336k2_python_environment_manifest(
            _object(
                repository.joinpath(*environment_component.relative_path.split("/"))
            ),
            repository=repository,
            python_executable=Path(request["python_executable"]),
            git_executable=git_executable,
        )
        _verify_attestation(freeze, attestation, exact_f28)
        _verify_initial_lineage(
            repository,
            git_executable,
            exact_f28=exact_f28,
            expected_branch_ref=authorization.branch_ref,
        )
        readiness_component = _component(freeze, "q28_readiness")
        readiness = readiness_from_dict(
            _object(repository.joinpath(*readiness_component.relative_path.split("/")))
        )
        verify_m336k2_readiness_destinations(
            readiness,
            _stage_destinations(stage_request),
        )
        if (
            authorization.route_registry_hash != route_registry.registry_hash
            or authorization.authorization_hash != freeze.authorization_hash
            or exact_f28 != attestation.exact_f28_sha
        ):
            raise M336K2ProtocolError("M336K2 final pre-ledger cross-binding changed")
        preflight_hash = content_hash(
            tuple(
                _component(freeze, name).bytes_hash
                for name in (
                    "windows_jdk_identity",
                    "karina_jdk_identity",
                    "karina_stable_host_identity",
                    "storage_budget",
                    "execution_capsule_receipt",
                    "python_environment_manifest",
                    "executable_dependency_manifest",
                )
            )
        )
        return build_preledger_proof(
            preflight_receipt_hash=preflight_hash,
            freeze_receipt_hash=attestation.attestation_hash,
            authorization_receipt_hash=authorization.authorization_hash,
            exact_f28_sha=exact_f28,
            route_registry_hash=route_registry.registry_hash,
        )

    result = run_m336k2_final_controller(
        route_run_id=request["route_run_id"],
        execution_mode=request["execution_mode"],
        exact_f28_sha=exact_f28,
        route_registry_hash=route_registry.registry_hash,
        ledger=ledger,
        preledger_guard=preledger_guard,
        worker=M336K2HermeticCommandWorker(plan),
        output=Path(request["route_receipt"]),
    )
    print(canonical_json(asdict(result)))


def _freeze(path: Path) -> M336K2FreezeManifest:
    value = _object(path)
    value["components"] = tuple(
        M336K2FrozenComponent(**item) for item in value["components"]
    )
    value["self_reference_safe_exclusions"] = tuple(
        value["self_reference_safe_exclusions"]
    )
    return M336K2FreezeManifest(**value)


def _attestation(path: Path) -> M336K2CommittedFreezeAttestation:
    value = _object(path)
    value["self_reference_safe_exclusions"] = tuple(
        value["self_reference_safe_exclusions"]
    )
    return M336K2CommittedFreezeAttestation(**value)


def _component(freeze: M336K2FreezeManifest, name: str) -> M336K2FrozenComponent:
    rows = tuple(item for item in freeze.components if item.name == name)
    if len(rows) != 1:
        raise M336K2ProtocolError("M336K2 final freeze component lookup failed")
    return rows[0]


def _verify_attestation(
    freeze: M336K2FreezeManifest,
    attestation: M336K2CommittedFreezeAttestation,
    exact_f28: str,
) -> None:
    body = asdict(attestation)
    claimed = body.pop("attestation_hash")
    if (
        attestation.exact_f28_sha != exact_f28
        or attestation.exact_q28_parent != freeze.exact_q28_sha
        or attestation.prospective_freeze_tree_hash
        != freeze.prospective_freeze_tree_hash
        or attestation.authorization_hash != freeze.authorization_hash
        or attestation.route_hash != freeze.route_hash
        or not attestation.prospective_tree_matches
        or attestation.implementation_change_count != 0
        or attestation.merge_count != 0
        or not attestation.head_upstream_remote_equal
        or not attestation.worktree_clean
        or attestation.status != "PASS"
        or content_hash(body) != claimed
    ):
        raise M336K2ProtocolError("M336K2 post-F28 attestation is invalid")


def _stage_destinations(request: dict) -> dict[str, Path]:
    names = {
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
    value = request.get("final_destinations")
    if not isinstance(value, dict) or set(value) != names:
        raise M336K2ProtocolError("M336K2 stage destinations changed")
    return {name: Path(path) for name, path in value.items()}


def _verify_initial_lineage(
    repository: Path,
    git: Path,
    *,
    exact_f28: str,
    expected_branch_ref: str,
) -> None:
    branch = _git(git, repository, "symbolic-ref", "HEAD")
    head = _git(git, repository, "rev-parse", "HEAD^{commit}")
    upstream = _git(git, repository, "rev-parse", "@{upstream}^{commit}")
    remote_row = _git(
        git, repository, "ls-remote", "--exit-code", "origin", expected_branch_ref
    ).split()
    remote = remote_row[0] if remote_row else ""
    if (
        branch != expected_branch_ref
        or head != exact_f28
        or upstream != exact_f28
        or remote != exact_f28
        or _git(git, repository, "status", "--porcelain=v1")
    ):
        raise M336K2ProtocolError("M336K2 initial F28 lineage is not exact")


def _worktrees(repository: Path, git_executable: Path) -> tuple[Path, ...]:
    raw = subprocess.run(
        (str(git_executable), "worktree", "list", "--porcelain", "-z"),
        cwd=repository,
        check=True,
        capture_output=True,
    ).stdout
    prefix = b"worktree "
    paths = tuple(
        Path(field.removeprefix(prefix).decode("utf-8")).resolve(strict=True)
        for field in raw.split(b"\0")
        if field.startswith(prefix)
    )
    if repository not in paths:
        raise M336K2ProtocolError("M336K2 current repository is not a Git worktree")
    return paths


def _git(git: Path, repository: Path, *arguments: str) -> str:
    return subprocess.run(
        (str(git), *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    ).stdout.strip()


def _object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K2 final controller input is invalid") from error
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K2 final controller input is not an object")
    return value


if __name__ == "__main__":
    main()
