"""Independent exact-R25 readiness gate for the M-33.6j hermetic route."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336h_contracts import strict_json_file
from ai_brain.stage3.acquisition.m336i_acquisition import (
    acquisition_provider_identity,
    compute_m336i_commit_tree_identity,
)
from ai_brain.stage3.acquisition.m336j_execution import (
    dependency_manifest_from_dict,
    public_execution_capsule_receipt_from_dict,
    public_value_has_private_path,
    python_environment_identity_from_dict,
)
from ai_brain.stage3.acquisition.m336j_mutations import (
    M336J_MUTATIONS,
    M336J_ROBUST_PASS_MUTATIONS,
)
from ai_brain.stage3.acquisition.m336j_registry import (
    build_m336j_route_manifest,
    build_m336j_route_registry,
    command_renderer_identity_hash,
)

M336J_EXACT_F24_SHA = "4891de1c3a0f6ba2d5d012ab5189dbb5222ba6bd"
M336J_READINESS_STATUS = "READY_FOR_HERMETIC_FINAL_ACQUISITION"


@dataclass(frozen=True)
class M336JReadinessRequest:
    repository: Path
    exact_r25_sha: str
    git_executable: Path
    route_registry: Path
    route_manifest: Path
    public_capsule_receipt: Path
    python_environment_manifest: Path
    executable_dependency_manifest: Path
    host_preflight_receipt: Path
    remote_materialization_receipt: Path
    remote_production_receipt: Path
    remote_replay_receipt: Path
    remote_evaluation_receipt: Path
    remote_runtime_receipt: Path
    mutation_report: Path
    windows_quality_receipt: Path
    karina_quality_receipt: Path
    final_unspent_receipt: Path
    q25_evidence_staging_root: Path
    git_worktrees: tuple[Path, ...]


@dataclass(frozen=True)
class M336JReadinessResult:
    schema_version: int
    contract_role: str
    exact_f24_sha: str
    exact_r25_sha: str
    r25_implementation_tree_identity: str
    q25_evidence_identity: str
    route_registry_hash: str
    route_manifest_hash: str
    execution_capsule_public_receipt_hash: str
    python_environment_manifest_hash: str
    executable_dependency_manifest_hash: str
    remote_command_renderer_hash: str
    minimal_environment_policy_hash: str
    acquisition_provider_source_hash: str
    acquisition_provider_callable_signature_hash: str
    host_preflight_receipt_hash: str
    remote_materialization_receipt_hash: str
    remote_production_receipt_hash: str
    remote_replay_receipt_hash: str
    remote_evaluation_receipt_hash: str
    remote_runtime_receipt_hash: str
    mutation_report_hash: str
    windows_quality_receipt_hash: str
    karina_quality_receipt_hash: str
    executable_dependency_count: int
    rejected_mutation_count: int
    bare_remote_executable_lookup_count: int
    profile_dependent_command_count: int
    unregistered_ssh_command_count: int
    remote_rehearsal_failure_count: int
    platform_neutral_difference_count: int
    source_leak_count: int
    absolute_public_path_count: int
    final_acquisition_reservation_count: int
    final_acquisition_invocation_count: int
    final_selector_reservation_count: int
    final_selector_invocation_count: int
    final_evaluator_reservation_count: int
    final_evaluator_invocation_count: int
    new_final_source_body_bytes: int
    status: str
    readiness_hash: str


def readiness_request_from_dict(value: dict) -> M336JReadinessRequest:
    expected = {item.name for item in fields(M336JReadinessRequest)}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("M336J readiness request fields changed")
    converted = {
        key: tuple(Path(item) for item in item_value)
        if key == "git_worktrees"
        else item_value
        if key == "exact_r25_sha"
        else Path(item_value)
        for key, item_value in value.items()
    }
    return M336JReadinessRequest(**converted)


def compute_m336j_evidence_tree_identity(root: Path) -> str:
    resolved = root.resolve(strict=True)
    rows = tuple(
        (
            path.relative_to(resolved).as_posix(),
            path.stat().st_size,
            bytes_hash(path.read_bytes()),
        )
        for path in sorted(
            (item for item in resolved.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(resolved).as_posix().encode(),
        )
    )
    if not rows:
        raise ValueError("M336J Q25 evidence staging is empty")
    return content_hash(rows)


def verify_m336j_ready_for_final_freeze(
    request: M336JReadinessRequest,
) -> M336JReadinessResult:
    if not isinstance(request, M336JReadinessRequest):
        raise TypeError("M336J readiness request must be typed")
    repository = request.repository.resolve(strict=True)
    git = request.git_executable.resolve(strict=True)
    head = _git(git, repository, "rev-parse", "HEAD^{commit}")
    parent = _git(git, repository, "rev-parse", "HEAD^1")
    status = _git(git, repository, "status", "--porcelain=v1")
    merge_count = int(
        _git(
            git,
            repository,
            "rev-list",
            "--count",
            "--merges",
            f"{M336J_EXACT_F24_SHA}..HEAD",
        )
    )
    if (
        head != request.exact_r25_sha
        or parent != M336J_EXACT_F24_SHA
        or status
        or merge_count
    ):
        raise ValueError("M336J readiness requires clean exact linear R25")

    capsule = public_execution_capsule_receipt_from_dict(
        _object(request.public_capsule_receipt)
    )
    python = python_environment_identity_from_dict(
        _object(request.python_environment_manifest)
    )
    dependencies = dependency_manifest_from_dict(
        _object(request.executable_dependency_manifest)
    )
    registry = build_m336j_route_registry()
    manifest = build_m336j_route_manifest(
        registry,
        execution_capsule_public_receipt_hash=capsule.receipt_hash,
        remote_command_renderer_hash=command_renderer_identity_hash(),
        executable_dependency_manifest_hash=dependencies.manifest_hash,
        minimal_environment_policy_hash=capsule.minimal_environment_policy_hash,
    )
    if (
        _object(request.route_registry) != json.loads(canonical_json(registry))
        or _object(request.route_manifest) != json.loads(canonical_json(manifest))
        or capsule.python_environment_package_manifest_hash
        != python.package_manifest_hash
        or capsule.executable_dependency_manifest_hash != dependencies.manifest_hash
        or capsule.project_import_smoke_hash != python.project_import_smoke_hash
    ):
        raise ValueError("M336J readiness route/capsule binding changed")

    host = _verified(request.host_preflight_receipt, "receipt_hash")
    materialization = _verified(request.remote_materialization_receipt, "receipt_hash")
    production = _verified(request.remote_production_receipt, "receipt_hash")
    replay = _verified(request.remote_replay_receipt, "receipt_hash")
    evaluation = _verified(request.remote_evaluation_receipt, "receipt_hash")
    runtime = _verified(request.remote_runtime_receipt, "receipt_hash")
    mutation = _mutation_report(request.mutation_report)
    windows_quality = _quality(request.windows_quality_receipt, "WINDOWS", head)
    karina_quality = _quality(request.karina_quality_receipt, "KARINA", head)
    unspent = _verified(request.final_unspent_receipt, "receipt_hash")
    public_values = (
        asdict(capsule),
        asdict(python),
        asdict(dependencies),
        json.loads(canonical_json(registry)),
        json.loads(canonical_json(manifest)),
        host,
        materialization,
        production,
        replay,
        evaluation,
        runtime,
        mutation,
        windows_quality,
        karina_quality,
        unspent,
    )
    provider_source, provider_signature = acquisition_provider_identity()
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336J_PRE_FREEZE_READINESS",
        "exact_f24_sha": M336J_EXACT_F24_SHA,
        "exact_r25_sha": head,
        "r25_implementation_tree_identity": compute_m336i_commit_tree_identity(
            repository, head
        ),
        "q25_evidence_identity": compute_m336j_evidence_tree_identity(
            request.q25_evidence_staging_root
        ),
        "route_registry_hash": registry.registry_hash,
        "route_manifest_hash": manifest.manifest_hash,
        "execution_capsule_public_receipt_hash": capsule.receipt_hash,
        "python_environment_manifest_hash": python.environment_manifest_hash,
        "executable_dependency_manifest_hash": dependencies.manifest_hash,
        "remote_command_renderer_hash": command_renderer_identity_hash(),
        "minimal_environment_policy_hash": capsule.minimal_environment_policy_hash,
        "acquisition_provider_source_hash": provider_source,
        "acquisition_provider_callable_signature_hash": provider_signature,
        "host_preflight_receipt_hash": host["receipt_hash"],
        "remote_materialization_receipt_hash": materialization["receipt_hash"],
        "remote_production_receipt_hash": production["receipt_hash"],
        "remote_replay_receipt_hash": replay["receipt_hash"],
        "remote_evaluation_receipt_hash": evaluation["receipt_hash"],
        "remote_runtime_receipt_hash": runtime["receipt_hash"],
        "mutation_report_hash": mutation["report_hash"],
        "windows_quality_receipt_hash": windows_quality["receipt_hash"],
        "karina_quality_receipt_hash": karina_quality["receipt_hash"],
        "executable_dependency_count": dependencies.dependency_count,
        "rejected_mutation_count": mutation.get("rejected_mutation_count", -1),
        "bare_remote_executable_lookup_count": (
            dependencies.bare_executable_lookup_count
        ),
        "profile_dependent_command_count": host.get(
            "profile_startup_dependency_count", -1
        ),
        "unregistered_ssh_command_count": (
            registry.unregistered_remote_command_call_site_count
        ),
        "remote_rehearsal_failure_count": sum(
            item.get("status") != "PASS"
            for item in (host, materialization, production, replay, evaluation, runtime)
        ),
        "platform_neutral_difference_count": evaluation.get(
            "platform_neutral_difference_count", -1
        ),
        "source_leak_count": sum(
            int(item.get("source_leak_count", 0))
            for item in (production, replay, evaluation, runtime)
        ),
        "absolute_public_path_count": sum(
            public_value_has_private_path(item) for item in public_values
        ),
        "final_acquisition_reservation_count": unspent.get(
            "final_acquisition_reservation_count", -1
        ),
        "final_acquisition_invocation_count": unspent.get(
            "final_acquisition_invocation_count", -1
        ),
        "final_selector_reservation_count": unspent.get(
            "final_selector_reservation_count", -1
        ),
        "final_selector_invocation_count": unspent.get(
            "final_selector_invocation_count", -1
        ),
        "final_evaluator_reservation_count": unspent.get(
            "final_evaluator_reservation_count", -1
        ),
        "final_evaluator_invocation_count": unspent.get(
            "final_evaluator_invocation_count", -1
        ),
        "new_final_source_body_bytes": unspent.get("new_final_source_body_bytes", -1),
        "status": M336J_READINESS_STATUS,
    }
    zero_fields = (
        "bare_remote_executable_lookup_count",
        "profile_dependent_command_count",
        "unregistered_ssh_command_count",
        "remote_rehearsal_failure_count",
        "platform_neutral_difference_count",
        "source_leak_count",
        "absolute_public_path_count",
        "final_acquisition_reservation_count",
        "final_acquisition_invocation_count",
        "final_selector_reservation_count",
        "final_selector_invocation_count",
        "final_evaluator_reservation_count",
        "final_evaluator_invocation_count",
        "new_final_source_body_bytes",
    )
    if (
        any(body[name] for name in zero_fields)
        or body["rejected_mutation_count"] < 40
        or dependencies.dependency_count < 5
        or capsule.verification_status != "PASS"
        or not python.user_site_loading_disabled
        or python.torch_imported
        or unspent.get("status") != "PASS"
    ):
        raise ValueError("M336J readiness acceptance criteria failed")
    return M336JReadinessResult(**body, readiness_hash=content_hash(body))


def readiness_result_from_dict(value: dict) -> M336JReadinessResult:
    if not isinstance(value, dict) or set(value) != set(
        M336JReadinessResult.__dataclass_fields__
    ):
        raise ValueError("M336J readiness result fields changed")
    result = M336JReadinessResult(**value)
    body = asdict(result)
    claimed = body.pop("readiness_hash")
    if content_hash(body) != claimed or result.status != M336J_READINESS_STATUS:
        raise ValueError("M336J readiness result is invalid")
    return result


def _quality(path: Path, platform_role: str, exact_sha: str) -> dict:
    value = _verified(path, "receipt_hash")
    if (
        value.get("contract_role") != "PUBLIC_SAFE_M336J_QUALITY_RECEIPT"
        or value.get("platform_role") != platform_role
        or value.get("exact_sha") != exact_sha
        or value.get("post_check_exact_sha") != exact_sha
        or not value.get("post_check_worktree_clean")
        or value.get("status") != "PASS"
        or any(item.get("exit_code") for item in value.get("checks", ()))
    ):
        raise ValueError("M336J exact quality receipt is invalid")
    return value


def _mutation_report(path: Path) -> dict:
    value = _verified(path, "report_hash")
    rows = value.get("mutations", ())
    identifiers = tuple(item.get("mutation_id") for item in rows)
    if (
        value.get("contract_role") != "PUBLIC_SAFE_M336J_MUTATION_REPORT"
        or value.get("executed_mutation_count") != len(rows)
        or value.get("rejected_mutation_count") != len(rows)
        or value.get("accepted_mutation_count") != 0
        or len(rows) < 40
        or identifiers != M336J_MUTATIONS
        or any(
            set(item)
            != {
                "mutation_id",
                "validator_class",
                "failure_class",
                "failure_message_hash",
                "status",
                "result_hash",
            }
            or item.get("status")
            != (
                "ROBUST_PASS"
                if item.get("mutation_id") in M336J_ROBUST_PASS_MUTATIONS
                else "FAIL_CLOSED"
            )
            or content_hash({k: v for k, v in item.items() if k != "result_hash"})
            != item.get("result_hash")
            for item in rows
        )
    ):
        raise ValueError("M336J mutation report is invalid")
    return value


def _verified(path: Path, hash_field: str) -> dict:
    value = _object(path)
    body = dict(value)
    claimed = body.pop(hash_field, None)
    if content_hash(body) != claimed or value.get("status") != "PASS":
        raise ValueError(f"M336J {hash_field} receipt is invalid")
    return value


def _object(path: Path) -> dict:
    value = strict_json_file(path)
    if not isinstance(value, dict):
        raise TypeError("M336J evidence artifact must be an object")
    return value


def _git(git: Path, repository: Path, *arguments: str) -> str:
    return subprocess.run(
        (str(git), *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
