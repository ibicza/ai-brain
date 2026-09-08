"""Independent pre-freeze readiness verification for M-33.6i."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, fields
from decimal import Decimal
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336d_leak_scan import scan_fresh_source_leaks
from ai_brain.stage3.acquisition.m336f_selection import M336FSelectorLedger
from ai_brain.stage3.acquisition.m336g_publication import (
    verify_java_public_candidate_pack,
)
from ai_brain.stage3.acquisition.m336h_contracts import strict_json_file
from ai_brain.stage3.acquisition.m336h_evaluation import M336HEvaluatorLedger
from ai_brain.stage3.acquisition.m336i_acquisition import (
    M336IFinalAcquisitionLedger,
    acquisition_provider_identity,
    compute_m336i_commit_tree_identity,
)
from ai_brain.stage3.acquisition.m336i_evaluation import (
    independent_evaluator_identity,
)
from ai_brain.stage3.acquisition.m336i_registry import (
    build_m336i_final_java_route_manifest,
    build_m336i_final_java_route_registry,
)
from ai_brain.stage3.acquisition.m336i_route import M336IRouteStateLedger

M336I_EXACT_Q23_SHA = "067855a9c3dfdfd503011444f08896d867beceac"
M336I_READINESS_STATUS = "READY_FOR_FINAL_ACQUISITION"
_REHEARSALS = ("DISCLOSED", "COUNT_NEUTRAL", "AUTHORIZED")
_DISCLOSED_PACK_HASH = (
    "d30aeb58b441c3c454836692a8f923d03cfae47195ee855ea3078f9c6b74ca0c"
)
_DISCLOSED_TREE_HASH = (
    "720893f00c3264df56c3e1d21d57b0ce70d4e568c99d1f24b011fef0a47bdc7d"
)
_DISCLOSED_REPLAY_HASH = (
    "3145879bec1867861f2dac79aaadb95d95dadbd8678dc4a60947d6990003cc51"
)


@dataclass(frozen=True)
class M336IReadinessRequest:
    repository: Path
    exact_r24_sha: str
    frozen_route_registry: Path
    frozen_route_manifest: Path
    disclosed_rehearsal_evidence: Path
    count_neutral_rehearsal_evidence: Path
    authorized_rehearsal_evidence: Path
    windows_quality_receipt: Path
    karina_quality_receipt: Path
    q24_evidence_staging_root: Path
    final_acquisition_ledger: Path
    final_route_state_ledger: Path
    final_selector_ledger: Path
    final_evaluator_ledger: Path
    final_vault_destination: Path
    git_worktrees: tuple[Path, ...]


@dataclass(frozen=True)
class M336IReadinessResult:
    schema_version: int
    contract_role: str
    exact_q23_sha: str
    exact_r24_sha: str
    r24_implementation_tree_identity: str
    q24_evidence_identity: str
    route_registry_hash: str
    route_manifest_hash: str
    acquisition_provider_source_hash: str
    acquisition_provider_callable_signature_hash: str
    independent_evaluator_implementation_identity: str
    disclosed_rehearsal_evidence_hash: str
    count_neutral_rehearsal_evidence_hash: str
    authorized_rehearsal_evidence_hash: str
    windows_quality_receipt_hash: str
    karina_quality_receipt_hash: str
    final_acquisition_reservation_count: int
    final_acquisition_invocation_count: int
    final_selector_reservation_count: int
    final_selector_invocation_count: int
    final_evaluator_reservation_count: int
    final_evaluator_invocation_count: int
    final_route_state_count: int
    new_final_source_body_bytes: int
    synthetic_default_metric_count: int
    unresolved_component_count: int
    incompatible_route_edge_count: int
    refusal_guard_registered_as_provider: bool
    rehearsal_failure_count: int
    quality_failure_count: int
    source_leak_count: int
    absolute_path_count: int
    private_role_public_count: int
    status: str
    readiness_hash: str


def readiness_request_from_dict(value: dict) -> M336IReadinessRequest:
    expected = {item.name for item in fields(M336IReadinessRequest)}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("M336I readiness request fields changed")
    converted = {
        key: tuple(Path(item) for item in item_value)
        if key == "git_worktrees"
        else item_value
        if key == "exact_r24_sha"
        else Path(item_value)
        for key, item_value in value.items()
    }
    return M336IReadinessRequest(**converted)


def compute_m336i_evidence_tree_identity(root: Path) -> str:
    resolved = root.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("M336I evidence staging root is not a directory")
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
        raise ValueError("M336I Q24 evidence staging is empty")
    return content_hash(rows)


def verify_m336i_ready_for_final_freeze(
    request: M336IReadinessRequest,
) -> M336IReadinessResult:
    if not isinstance(request, M336IReadinessRequest):
        raise TypeError("M336I readiness request must be typed")
    repository = request.repository.resolve(strict=True)
    head = _git(repository, "rev-parse", "HEAD^{commit}")
    status = _git(repository, "status", "--porcelain=v1")
    parent = _git(repository, "rev-parse", f"{request.exact_r24_sha}^1")
    merge_count = int(
        _git(
            repository,
            "rev-list",
            "--count",
            "--merges",
            f"{M336I_EXACT_Q23_SHA}..{request.exact_r24_sha}",
        )
    )
    if (
        head != request.exact_r24_sha
        or status
        or parent != M336I_EXACT_Q23_SHA
        or merge_count
    ):
        raise ValueError("M336I readiness requires clean exact linear R24")

    live_registry = build_m336i_final_java_route_registry()
    live_manifest = build_m336i_final_java_route_manifest(live_registry)
    if _object(request.frozen_route_registry) != json.loads(
        canonical_json(live_registry)
    ) or _object(request.frozen_route_manifest) != json.loads(
        canonical_json(live_manifest)
    ):
        raise ValueError("M336I readiness route artifacts differ from live code")
    provider_source, provider_signature = acquisition_provider_identity()

    evidence_paths = (
        request.disclosed_rehearsal_evidence,
        request.count_neutral_rehearsal_evidence,
        request.authorized_rehearsal_evidence,
    )
    rehearsal_results = tuple(
        _verify_rehearsal(path, expected_kind)
        for path, expected_kind in zip(evidence_paths, _REHEARSALS, strict=True)
    )
    quality_results = (
        verify_m336i_quality_receipt(
            request.windows_quality_receipt, "WINDOWS", request.exact_r24_sha
        ),
        verify_m336i_quality_receipt(
            request.karina_quality_receipt, "KARINA", request.exact_r24_sha
        ),
    )

    acquisition = M336IFinalAcquisitionLedger(
        request.final_acquisition_ledger, git_worktrees=request.git_worktrees
    ).receipt()
    route = M336IRouteStateLedger(
        request.final_route_state_ledger, git_worktrees=request.git_worktrees
    ).receipt()
    selector = M336FSelectorLedger(
        request.final_selector_ledger, git_worktrees=request.git_worktrees
    ).receipt()
    evaluator_events = M336HEvaluatorLedger(
        request.final_evaluator_ledger, git_worktrees=request.git_worktrees
    ).events()
    if request.final_vault_destination.exists():
        final_source_bytes = sum(
            path.stat().st_size
            for path in request.final_vault_destination.rglob("*")
            if path.is_file()
        )
    else:
        final_source_bytes = 0
    q24_identity = compute_m336i_evidence_tree_identity(
        request.q24_evidence_staging_root
    )
    source_leaks = sum(item["source_leak_count"] for item in rehearsal_results)
    absolute_paths = sum(item["absolute_path_count"] for item in rehearsal_results)
    private_roles = sum(item["private_role_count"] for item in rehearsal_results)
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336I_PRE_FREEZE_READINESS",
        "exact_q23_sha": M336I_EXACT_Q23_SHA,
        "exact_r24_sha": request.exact_r24_sha,
        "r24_implementation_tree_identity": compute_m336i_commit_tree_identity(
            repository, request.exact_r24_sha
        ),
        "q24_evidence_identity": q24_identity,
        "route_registry_hash": live_registry.registry_hash,
        "route_manifest_hash": live_manifest.manifest_hash,
        "acquisition_provider_source_hash": provider_source,
        "acquisition_provider_callable_signature_hash": provider_signature,
        "independent_evaluator_implementation_identity": independent_evaluator_identity(),
        "disclosed_rehearsal_evidence_hash": rehearsal_results[0]["manifest_hash"],
        "count_neutral_rehearsal_evidence_hash": rehearsal_results[1]["manifest_hash"],
        "authorized_rehearsal_evidence_hash": rehearsal_results[2]["manifest_hash"],
        "windows_quality_receipt_hash": quality_results[0]["receipt_hash"],
        "karina_quality_receipt_hash": quality_results[1]["receipt_hash"],
        "final_acquisition_reservation_count": acquisition.acquisition_reservation_count,
        "final_acquisition_invocation_count": acquisition.acquisition_start_count,
        "final_selector_reservation_count": selector["selector_reservation_count"],
        "final_selector_invocation_count": selector["selector_invocation_count"],
        "final_evaluator_reservation_count": sum(
            item["event"] == "EVALUATOR_RESERVED" for item in evaluator_events
        ),
        "final_evaluator_invocation_count": sum(
            item["event"] == "EVALUATOR_COMPLETED" for item in evaluator_events
        ),
        "final_route_state_count": route.state_count,
        "new_final_source_body_bytes": final_source_bytes,
        "synthetic_default_metric_count": sum(
            item["synthetic_default_metric_count"] for item in rehearsal_results
        ),
        "unresolved_component_count": live_registry.unresolved_component_count,
        "incompatible_route_edge_count": live_manifest.incompatible_edge_count,
        "refusal_guard_registered_as_provider": (
            live_manifest.refusal_guard_registered_as_provider
        ),
        "rehearsal_failure_count": sum(
            item["status"] != "PASS" for item in rehearsal_results
        ),
        "quality_failure_count": sum(
            item["status"] != "PASS" for item in quality_results
        ),
        "source_leak_count": source_leaks,
        "absolute_path_count": absolute_paths,
        "private_role_public_count": private_roles,
        "status": M336I_READINESS_STATUS,
    }
    zero_fields = (
        "final_acquisition_reservation_count",
        "final_acquisition_invocation_count",
        "final_selector_reservation_count",
        "final_selector_invocation_count",
        "final_evaluator_reservation_count",
        "final_evaluator_invocation_count",
        "final_route_state_count",
        "new_final_source_body_bytes",
        "synthetic_default_metric_count",
        "unresolved_component_count",
        "incompatible_route_edge_count",
        "rehearsal_failure_count",
        "quality_failure_count",
        "source_leak_count",
        "absolute_path_count",
        "private_role_public_count",
    )
    if (
        any(body[name] for name in zero_fields)
        or body["refusal_guard_registered_as_provider"]
    ):
        raise ValueError("M336I readiness acceptance criteria failed")
    return M336IReadinessResult(**body, readiness_hash=content_hash(body))


def readiness_result_from_dict(value: dict) -> M336IReadinessResult:
    if not isinstance(value, dict) or set(value) != set(
        M336IReadinessResult.__dataclass_fields__
    ):
        raise ValueError("M336I readiness result fields changed")
    result = M336IReadinessResult(**value)
    body = asdict(result)
    claimed = body.pop("readiness_hash")
    if content_hash(body) != claimed or result.status != M336I_READINESS_STATUS:
        raise ValueError("M336I readiness result is invalid")
    return result


def _verify_rehearsal(path: Path, expected_kind: str) -> dict:
    manifest = _object(path)
    _verify_hash(manifest, "manifest_hash")
    expected_fields = {
        "schema_version",
        "contract_role",
        "rehearsal_kind",
        "windows_rehearsal_receipt",
        "karina_rehearsal_receipt",
        "windows_production_root",
        "karina_production_root",
        "independent_evaluation",
        "staging_root",
        "staging_manifest",
        "staging_receipt",
        "sealed_vault",
        "authorized_acquisition_rehearsal_receipt",
        "manifest_hash",
    }
    if (
        set(manifest) != expected_fields
        or manifest.get("schema_version") != 1
        or manifest.get("contract_role") != "PRIVATE_M336I_REHEARSAL_EVIDENCE_BINDINGS"
        or manifest.get("rehearsal_kind") != expected_kind
    ):
        raise ValueError("M336I rehearsal evidence binding fields changed")
    bound_paths = {
        name: Path(manifest[name])
        for name in expected_fields
        - {
            "schema_version",
            "contract_role",
            "rehearsal_kind",
            "manifest_hash",
            "authorized_acquisition_rehearsal_receipt",
        }
    }
    if any(not item.exists() for item in bound_paths.values()):
        raise ValueError("M336I rehearsal evidence artifact is missing")
    windows_receipt = _verified_receipt(
        bound_paths["windows_rehearsal_receipt"], "receipt_hash"
    )
    karina_receipt = _verified_receipt(
        bound_paths["karina_rehearsal_receipt"], "receipt_hash"
    )
    if any(
        item.get("rehearsal_kind") != expected_kind
        or item.get("status") != "PASS"
        or item.get("platform_role") != platform
        for item, platform in (
            (windows_receipt, "WINDOWS"),
            (karina_receipt, "KARINA"),
        )
    ):
        raise ValueError("M336I platform rehearsal receipt did not pass")
    windows_root = bound_paths["windows_production_root"]
    karina_root = bound_paths["karina_production_root"]
    windows_seal = _verified_receipt(
        windows_root / "m336i_production_seal.json", "seal_hash"
    )
    karina_seal = _verified_receipt(
        karina_root / "m336i_production_seal.json", "seal_hash"
    )
    if (
        windows_seal.get("platform_role") != "WINDOWS"
        or karina_seal.get("platform_role") != "KARINA"
        or _neutral_seal(windows_seal) != _neutral_seal(karina_seal)
    ):
        raise ValueError("M336I rehearsal platform seals differ")
    windows_pack = verify_java_public_candidate_pack(windows_root / "candidate_pack")
    karina_pack = verify_java_public_candidate_pack(karina_root / "candidate_pack")
    if (
        windows_pack.candidate_pack_content_hash
        != karina_pack.candidate_pack_content_hash
        or windows_pack.candidate_pack_tree_hash != karina_pack.candidate_pack_tree_hash
    ):
        raise ValueError("M336I rehearsal candidate packs are not byte-identical")
    evaluation = _verified_receipt(bound_paths["independent_evaluation"], "result_hash")
    required_zero = (
        "wrong_trusted_count",
        "field_evidence_missing_count",
        "field_evidence_extra_count",
        "field_evidence_duplicate_count",
        "field_evidence_wrong_count",
        "false_automatic_spdx_identity_count",
        "platform_neutral_difference_count",
        "evaluator_network_access_count",
        "production_call_count",
        "selector_call_count",
        "source_materialization_call_count",
        "torch_import_count",
        "synthetic_default_metric_count",
    )
    if (
        evaluation.get("status") != "PASS"
        or any(evaluation.get(name) != 0 for name in required_zero)
        or evaluation.get("runtime_status") != "PASS"
        or evaluation.get("public_pack_integrity_status") != "PASS"
        or evaluation.get("sealed_replay_status") != "PASS"
        or evaluation.get("trust_precision") != "1.000000"
        or Decimal(evaluation.get("safe_trust_coverage", "0")) < Decimal("0.950000")
        or evaluation.get("location_precision") != "1.000000"
        or Decimal(evaluation.get("location_recall", "0")) < Decimal("0.950000")
        or evaluation.get("semantic_precision") != "1.000000"
        or Decimal(evaluation.get("semantic_recall", "0")) < Decimal("0.950000")
        or evaluation.get("field_evidence_exactness") != "1.000000"
        or evaluation.get("spdx_agreement") != "1.000000"
    ):
        raise ValueError("M336I independent rehearsal evaluation failed")
    staging_manifest = _verified_receipt(
        bound_paths["staging_manifest"], "manifest_hash"
    )
    staging_receipt = _verified_receipt(bound_paths["staging_receipt"], "receipt_hash")
    staging_root = bound_paths["staging_root"].resolve(strict=True)
    staging_rows = _tree_rows(staging_root)
    if (
        staging_receipt.get("status") != "PASS"
        or staging_receipt.get("staging_manifest_hash")
        != staging_manifest["manifest_hash"]
        or staging_manifest.get("staging_tree_hash") != content_hash(staging_rows)
        or any(
            staging_receipt.get(name) != 0
            for name in (
                "post_scan_modified_file_count",
                "unscanned_committed_file_count",
                "scanned_file_omitted_from_manifest_count",
            )
        )
    ):
        raise ValueError("M336I rehearsal staging evidence changed")
    leak = scan_fresh_source_leaks(bound_paths["sealed_vault"], staging_root)
    if leak["status"] != "PASS" or leak["fresh_source_leak_count"]:
        raise ValueError("M336I readiness independent leak scan failed")

    if expected_kind == "DISCLOSED":
        expected = {
            "selected_file_count": 180,
            "root_distribution": [
                ["errorprone-annotations", 19],
                ["failsafe", 27],
                ["jctools-core", 63],
                ["jetbrains-annotations", 18],
                ["modelmapper", 53],
            ],
            "proposal_count": 1587,
            "trusted_count": 1575,
            "withheld_count": 12,
            "candidate_pack_content_hash": _DISCLOSED_PACK_HASH,
            "candidate_pack_tree_hash": _DISCLOSED_TREE_HASH,
            "public_replay_commitment_hash": _DISCLOSED_REPLAY_HASH,
        }
        if any(windows_receipt.get(name) != value for name, value in expected.items()):
            raise ValueError("M336I disclosed regression rehearsal changed")
    elif expected_kind == "COUNT_NEUTRAL":
        if (
            windows_receipt.get("selected_file_count") != 12
            or windows_receipt.get("selected_root_count") != 3
            or max(value for _root, value in windows_receipt["root_distribution"]) > 5
            or windows_receipt.get("closure_support_file_count", 0) < 1
            or (
                windows_receipt.get("proposal_count"),
                windows_receipt.get("trusted_count"),
                windows_receipt.get("withheld_count"),
            )
            == (1587, 1575, 12)
        ):
            raise ValueError("M336I count-neutral rehearsal constraints failed")
    else:
        acquisition_value = manifest["authorized_acquisition_rehearsal_receipt"]
        if not acquisition_value:
            raise ValueError("M336I authorized rehearsal lacks provider evidence")
        acquisition_receipt = _verified_receipt(Path(acquisition_value), "receipt_hash")
        if (
            acquisition_receipt.get("status") != "PASS"
            or acquisition_receipt.get("final_acquisition_reservation_count") != 0
            or acquisition_receipt.get("final_acquisition_invocation_count") != 0
            or acquisition_receipt.get("rehearsal_acquisition_reservation_count") != 1
            or acquisition_receipt.get("rehearsal_acquisition_invocation_count") != 1
            or acquisition_receipt.get("rehearsal_acquisition_rerun_count") != 0
        ):
            raise ValueError("M336I authorized provider rehearsal counters failed")
    return {
        "manifest_hash": manifest["manifest_hash"],
        "synthetic_default_metric_count": evaluation["synthetic_default_metric_count"],
        "source_leak_count": leak["fresh_source_leak_count"],
        "absolute_path_count": leak["public_absolute_path_count"],
        "private_role_count": leak["private_artifact_role_count"],
        "status": "PASS",
    }


def verify_m336i_quality_receipt(path: Path, platform: str, exact_sha: str) -> dict:
    receipt = _verified_receipt(path, "receipt_hash")
    rows = tuple(receipt.get("checks", ()))
    required = {
        "targeted",
        "ruff_format",
        "ruff_lint",
        "compileall",
        "java_reference",
        "no_network",
        "no_torch",
        "full_suite",
        "route_preflight",
    }
    names = {item.get("name") for item in rows}
    if (
        receipt.get("contract_role") != "PUBLIC_SAFE_M336I_QUALITY_RECEIPT"
        or receipt.get("platform_role") != platform
        or receipt.get("exact_sha") != exact_sha
        or receipt.get("post_check_exact_sha") != exact_sha
        or receipt.get("post_check_worktree_clean") is not True
        or receipt.get("status") != "PASS"
        or receipt.get("check_count") != len(rows)
        or not required.issubset(names)
        or any(item.get("exit_code") != 0 for item in rows)
        or any(
            content_hash(
                {key: value for key, value in item.items() if key != "check_hash"}
            )
            != item.get("check_hash")
            for item in rows
        )
    ):
        raise ValueError("M336I exact quality evidence failed")
    return receipt


def _verified_receipt(path: Path, hash_field: str) -> dict:
    value = _object(path)
    _verify_hash(value, hash_field)
    return value


def _verify_hash(value: dict, field: str) -> None:
    body = dict(value)
    claimed = body.pop(field, None)
    if content_hash(body) != claimed:
        raise ValueError(f"M336I bound {field} differs from content")


def _neutral_seal(value: dict) -> dict:
    excluded = {
        "platform_role",
        "production_request_hash",
        "production_response_hash",
        "seal_hash",
    }
    return {key: item for key, item in value.items() if key not in excluded}


def _tree_rows(root: Path) -> tuple[tuple[str, int, str], ...]:
    return tuple(
        (
            path.relative_to(root).as_posix(),
            path.stat().st_size,
            bytes_hash(path.read_bytes()),
        )
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix().encode(),
        )
    )


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _object(path: Path) -> dict:
    value = strict_json_file(path)
    if not isinstance(value, dict):
        raise TypeError("M336I readiness input must be an object")
    return value
