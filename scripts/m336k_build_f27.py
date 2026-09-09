"""Build the metadata-only M-33.6k F27 freeze without spending acquisition."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import urllib.parse
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    load_disclosed_java_registry,
)
from ai_brain.stage3.acquisition.m336i_acquisition import (
    validate_m336i_candidate_pool,
)
from ai_brain.stage3.acquisition.m336k_archive import ArchiveInspectionPolicyV2
from ai_brain.stage3.acquisition.m336k_final_pipeline import (
    M336K_FINAL_RUN_ID,
    build_m336k_final_acquisition_authorization,
    m336k_candidate_terminal_policy,
    m336k_global_continuation_policy,
)

ROUTE_COMPONENTS = (
    "src/ai_brain/stage3/acquisition/java_evidence_transforms.py",
    "src/ai_brain/stage3/acquisition/java_jdk_provider.py",
    "src/ai_brain/stage3/acquisition/java_production_compiler.py",
    "src/ai_brain/stage3/acquisition/java_source_index.py",
    "src/ai_brain/stage3/acquisition/m336f_compilation_closure.py",
    "src/ai_brain/stage3/acquisition/m336g_publication.py",
    "src/ai_brain/stage3/acquisition/m336g_replay.py",
    "src/ai_brain/stage3/acquisition/m336k_archive.py",
    "src/ai_brain/stage3/acquisition/m336k_acquisition.py",
    "src/ai_brain/stage3/acquisition/m336k_final_pipeline.py",
    "src/ai_brain/stage3/acquisition/m336k_publication.py",
    "src/ai_brain/stage3/acquisition/m336k_readiness.py",
    "src/ai_brain/stage3/acquisition/m336e_final_pipeline.py",
    "src/ai_brain/stage3/acquisition/m336d_leak_scan.py",
    "scripts/m336k_run_final_acquisition.py",
    "scripts/m336k_run_r27_qualification.py",
    "scripts/m336k_compare_r27.py",
    "scripts/m336k_build_readiness.py",
    "scripts/m336k_run_exact_quality.py",
    "scripts/m336f_run_disclosed_closure.py",
    "scripts/m336f_run_disclosed_production.py",
    "scripts/m336f_evaluate_disclosed_java.py",
    "scripts/m336_run_oracle_free_production.py",
    "scripts/m336_evaluate_sealed_java.py",
    "scripts/m336d_evaluate_final.py",
    "scripts/m336g_run_sealed_replay.py",
    "scripts/m343_author_semantic_goldens.py",
    "tools/m343_java_oracle/JavaSemanticProposalOracle.java",
)


def _load(path: Path) -> dict:
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _sealed(path: Path, field: str) -> tuple[dict, str]:
    value = _load(path)
    body = dict(value)
    claimed = body.pop(field, None)
    if claimed is None or content_hash(body) != claimed:
        raise ValueError(f"invalid frozen input: {path.name}")
    return value, claimed


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source.resolve(strict=True), destination)


def _tree_rows(root: Path, *, exclude: frozenset[str] = frozenset()):
    return tuple(
        (
            path.relative_to(root).as_posix(),
            bytes_hash(path.read_bytes()),
            path.stat().st_size,
        )
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
        )
        if path.relative_to(root).as_posix() not in exclude
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--exact-r27-sha", required=True)
    parser.add_argument("--exact-q27-sha", required=True)
    parser.add_argument("--candidate-pool", type=Path, required=True)
    parser.add_argument("--q27-evidence", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--inherited-freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError("M336K F27 output must be fresh")
    if output.is_relative_to(repository):
        raise ValueError("M336K F27 prospective output must remain outside Git")
    if (
        _git(repository, "rev-parse", "HEAD^{commit}") != args.exact_q27_sha
        or _git(repository, "rev-parse", "HEAD^1") != args.exact_r27_sha
        or _git(repository, "status", "--porcelain=v1")
        or _git(
            repository,
            "rev-list",
            "--merges",
            "--count",
            f"{args.exact_r27_sha}..{args.exact_q27_sha}",
        )
        != "0"
    ):
        raise ValueError("F27 builder requires clean linear exact Q27")
    branch_ref = _git(repository, "symbolic-ref", "HEAD")
    pool = _load(args.candidate_pool)
    candidates = validate_m336i_candidate_pool(pool)
    inherited = args.inherited_freeze.resolve(strict=True)
    organizations = Counter(item["organization_id"] for item in candidates)
    if (
        len(candidates) < 64
        or len(organizations) < 56
        or max(organizations.values(), default=0) > 2
        or pool["pre_f22_source_body_bytes_received"] != 0
    ):
        raise ValueError("M336K fresh metadata-only pool lacks required diversity")
    freshness = _verify_fresh_pool(
        candidates,
        f26_candidates=tuple(_load(inherited / "candidate_pool.json")["candidates"]),
        disclosed=load_disclosed_java_registry(args.registry.resolve(strict=True)),
    )
    q27_rows = _tree_rows(args.q27_evidence.resolve(strict=True))
    if not q27_rows:
        raise ValueError("M336K Q27 evidence tree is empty")
    registry, registry_hash = _sealed(
        args.registry.resolve(strict=True) / "registry_manifest.json", "manifest_hash"
    )
    thresholds, threshold_hash = _sealed(
        inherited / "threshold_manifest.json", "threshold_manifest_hash"
    )
    archive_policy = ArchiveInspectionPolicyV2.frozen_default()
    terminal_policy = m336k_candidate_terminal_policy()
    continuation_policy = m336k_global_continuation_policy()
    allowed_hosts = tuple(
        sorted(
            {
                host
                for item in candidates
                for key in (
                    "source_url",
                    "pom_url",
                    "scm_repository",
                    "scm_archive_head_url",
                )
                if (host := urllib.parse.urlsplit(item.get(key, "")).hostname)
            }
        )
    )
    acquisition_body = {
        "schema_version": 1,
        "policy_version": "m336k.final-acquisition.v3",
        "acquisition_run_id": M336K_FINAL_RUN_ID,
        "candidate_pool_hash": pool["pool_hash"],
        "archive_policy_hash": archive_policy.policy_hash,
        "candidate_terminal_policy_hash": terminal_policy["policy_hash"],
        "global_continuation_policy_hash": continuation_policy["policy_hash"],
        "allowed_network_hosts": list(allowed_hosts),
        "global_acquisition_count": 1,
        "windows_acquisition_count": 1,
        "karina_acquisition_count": 0,
        "candidate_retries_allowed": False,
        "candidate_replacements_allowed": False,
        "acquire_every_frozen_candidate": True,
        "pre_f27_source_body_bytes": 0,
    }
    acquisition_policy = {
        **acquisition_body,
        "acquisition_policy_hash": content_hash(acquisition_body),
    }
    source_bytes = sum(item["source_content_length"] for item in candidates)
    scm_bytes = sum(item.get("scm_archive_content_length", 0) for item in candidates)
    storage_body = {
        "schema_version": 1,
        "source_jar_content_length_bytes": source_bytes,
        "known_scm_archive_content_length_bytes": scm_bytes,
        "worst_case_extraction_multiplier": 12,
        "temporary_streaming_reserve_bytes": 536_870_912,
        "compiler_replay_reserve_bytes": 2_147_483_648,
        "required_capacity_bytes": (source_bytes + scm_bytes) * 13
        + 536_870_912
        + 2_147_483_648,
        "pre_f27_source_body_bytes": 0,
    }
    storage_budget = {**storage_body, "budget_hash": content_hash(storage_body)}
    route_rows = tuple(
        (path, bytes_hash((repository / path).read_bytes()))
        for path in ROUTE_COMPONENTS
    )
    route_body = {
        "schema_version": 1,
        "route_version": "m336k.candidate-isolated-final-route.v1",
        "exact_r27_sha": args.exact_r27_sha,
        "route_components": route_rows,
        "candidate_acquisition_component": (
            "ai_brain.stage3.acquisition.m336k_acquisition.acquire_candidate_v2"
        ),
        "global_coordinator_component": (
            "ai_brain.stage3.acquisition.m336k_final_pipeline."
            "run_m336k_frozen_final_acquisition"
        ),
        "final_controller": "scripts/m336k_run_final_acquisition.py",
        "candidate_failure_isolation": True,
        "unexpected_failure_is_global": True,
    }
    route = {**route_body, "route_manifest_hash": content_hash(route_body)}
    output.mkdir(parents=True)
    _write(output / "candidate_pool.json", pool)
    _write(output / "acquisition_policy.json", acquisition_policy)
    _write(output / "archive_policy_v2.json", asdict(archive_policy))
    _write(output / "candidate_terminal_policy.json", terminal_policy)
    _write(output / "global_continuation_policy.json", continuation_policy)
    _write(output / "route_manifest.json", route)
    _write(output / "storage_budget.json", storage_budget)
    _write(output / "freshness_exclusion_receipt.json", freshness)
    _write(output / "threshold_manifest.json", thresholds)
    _write(output / "registry_manifest.json", registry)
    for name in (
        "authority_root.json",
        "authority_statement.txt",
        "selector_policy.json",
        "publication_boundary_contract.json",
        "public_artifact_contract.json",
        "compiler_jdk_identities.json",
        "commit_protocol.json",
    ):
        _copy(inherited / name, output / name)
    q27_body = {
        "schema_version": 1,
        "exact_q27_sha": args.exact_q27_sha,
        "file_count": len(q27_rows),
        "tree_hash": content_hash(q27_rows),
    }
    _write(
        output / "q27_evidence_manifest.json",
        {**q27_body, "manifest_hash": content_hash(q27_body)},
    )
    prospective_rows = _tree_rows(output)
    prospective_hash = content_hash(prospective_rows)
    authorization = build_m336k_final_acquisition_authorization(
        exact_r27_sha=args.exact_r27_sha,
        exact_q27_sha=args.exact_q27_sha,
        branch_ref=branch_ref,
        acquisition_run_id=M336K_FINAL_RUN_ID,
        candidate_pool_hash=pool["pool_hash"],
        acquisition_policy_hash=acquisition_policy["acquisition_policy_hash"],
        archive_policy_hash=archive_policy.policy_hash,
        candidate_terminal_policy_hash=terminal_policy["policy_hash"],
        global_continuation_policy_hash=continuation_policy["policy_hash"],
        route_manifest_hash=route["route_manifest_hash"],
        registry_manifest_hash=registry_hash,
        threshold_manifest_hash=threshold_hash,
        allowed_network_hosts=allowed_hosts,
        expected_global_acquisition_count=1,
        expected_windows_acquisition_count=1,
        expected_karina_acquisition_count=0,
        candidate_retries_allowed=False,
        candidate_replacements_allowed=False,
        pre_f27_source_body_bytes=0,
    )
    freeze_body = {
        "schema_version": 1,
        "contract_role": "M336K_F27_FREEZE_MANIFEST",
        "exact_r27_sha": args.exact_r27_sha,
        "exact_q27_sha": args.exact_q27_sha,
        "prospective_freeze_tree_hash": prospective_hash,
        "prospective_file_count": len(prospective_rows),
        "authorization_hash": authorization.authorization_hash,
        "candidate_pool_hash": pool["pool_hash"],
        "acquisition_policy_hash": acquisition_policy["acquisition_policy_hash"],
        "archive_policy_hash": archive_policy.policy_hash,
        "candidate_terminal_policy_hash": terminal_policy["policy_hash"],
        "global_continuation_policy_hash": continuation_policy["policy_hash"],
        "route_manifest_hash": route["route_manifest_hash"],
        "registry_manifest_hash": registry_hash,
        "threshold_manifest_hash": threshold_hash,
        "storage_budget_hash": storage_budget["budget_hash"],
        "q27_evidence_manifest_hash": content_hash(q27_body),
        "final_acquisition_reservation_count": 0,
        "final_acquisition_invocation_count": 0,
        "pre_f27_source_body_bytes": 0,
        "status": "F27_READY_TO_COMMIT",
    }
    freeze = {**freeze_body, "freeze_manifest_hash": content_hash(freeze_body)}
    _write(output / "final_authorization.json", asdict(authorization))
    _write(output / "freeze_manifest.json", freeze)
    receipt_body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K_F27_STAGING_RECEIPT",
        "exact_q27_sha": args.exact_q27_sha,
        "exact_r27_sha": args.exact_r27_sha,
        "prospective_freeze_tree_hash": prospective_hash,
        "authorization_hash": authorization.authorization_hash,
        "freeze_manifest_hash": freeze["freeze_manifest_hash"],
        "candidate_count": len(candidates),
        "organization_count": len(organizations),
        "maximum_candidates_per_organization": max(organizations.values()),
        "pre_f27_source_body_bytes": 0,
        "network_acquisition_count": 0,
        "one_shot_ledger_write_count": 0,
        "status": "F27_READY_TO_COMMIT",
    }
    print(canonical_json({**receipt_body, "receipt_hash": content_hash(receipt_body)}))


def _verify_fresh_pool(candidates, *, f26_candidates, disclosed) -> dict:
    f26_fields = {
        field: {item.get(field) for item in f26_candidates if item.get(field)}
        for field in (
            "family_id",
            "coordinate",
            "source_url",
            "scm_repository",
            "scm_ref",
            "scm_commit",
            "metadata_pom_sha256",
            "source_sha256_sidecar_value",
        )
    }
    disclosed_fields = {
        "coordinate": {item.coordinate for item in disclosed},
        "source_url": {item.source_url for item in disclosed},
        "metadata_pom_sha256": {item.pom_hash for item in disclosed},
        "source_sha256_sidecar_value": {item.archive_hash for item in disclosed},
        "scm_commit": {item.scm_revision for item in disclosed},
    }
    overlaps = []
    for item in candidates:
        for field, values in f26_fields.items():
            if item.get(field) in values:
                overlaps.append((item["family_id"], f"F26_{field}"))
        for field, values in disclosed_fields.items():
            if item.get(field) in values:
                overlaps.append((item["family_id"], f"DISCLOSED_{field}"))
    body = {
        "schema_version": 1,
        "candidate_count": len(candidates),
        "f26_candidate_count": len(f26_candidates),
        "disclosed_entry_count": len(disclosed),
        "identity_overlap_count": len(overlaps),
        "overlap_rows": tuple(sorted(overlaps)),
        "pre_f27_raw_body_bytes": 0,
        "status": "PASS" if not overlaps else "FAIL",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    if overlaps:
        raise ValueError("M336K final pool overlaps F26 or disclosed identities")
    return receipt


if __name__ == "__main__":
    main()
