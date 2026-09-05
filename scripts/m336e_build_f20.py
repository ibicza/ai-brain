"""Assemble the exact metadata-only M-33.6e F20 freeze tree."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_evidence_policy import (
    load_production_java_evidence_policy,
)
from ai_brain.stage3.acquisition.java_parser_artifact import (
    TREE_SITTER_JAVA_SOURCE_SHA256,
    TREE_SITTER_JAVA_VERSION,
    TREE_SITTER_VERSION,
)
from ai_brain.stage3.acquisition.m336d_spdx_reference import REFERENCE_SOURCE
from ai_brain.stage3.acquisition.m336e_authority import (
    M336E_AUTHORITY_STATEMENT_SHA256,
    load_m336e_authority_registry,
)
from ai_brain.stage3.acquisition.m336e_contracts import (
    M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
)
from ai_brain.stage3.acquisition.m336e_disclosed_qualification import (
    M336E_DISCLOSED_CONSTRUCT_QUOTAS,
)
from ai_brain.stage3.acquisition.m336e_final_pipeline import (
    M336E_FINAL_ACQUISITION_RUN_ID,
    M336E_FINAL_ROOT_CAP,
    M336E_FINAL_SELECTOR_SEED,
    M336E_FINAL_SELECTOR_VERSION,
    M336E_FINAL_TARGET,
)
from ai_brain.stage3.acquisition.m336e_metadata_pool import validate_metadata_pool_v4
from ai_brain.stage3.acquisition.m336e_protocol import (
    M336E_PROTOCOL_VERSION,
    RUN_PROTOCOL_EVENT_ORDER,
)

AUTHORITY = (
    b"M336E_USER_AUTHORITY_V1\n"
    b"source_use=PRIVATE_LOCAL_ANALYSIS,LOCAL_RESEARCH_EVALUATION,"
    b"DERIVED_KNOWLEDGE_ONLY,RAW_SOURCE_RETENTION,"
    b"PUBLIC_REPRODUCIBLE_EVALUATION\n"
    b"publication_allow=DERIVED_PACK_PUBLICATION,METRICS_ONLY_PUBLICATION\n"
    b"publication_deny=RAW_SOURCE_PUBLICATION,SOURCE_EXCERPT_PUBLICATION\n"
    b"raw_storage=LOCAL_SEALED_VAULT_ONLY\n"
    b"authority_may_narrow=true\n"
    b"authority_may_widen=false\n"
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--q20-sha", required=True)
    parser.add_argument("--q20-root", type=Path, required=True)
    parser.add_argument("--metadata-root", type=Path, required=True)
    parser.add_argument("--windows-cache", type=Path, required=True)
    parser.add_argument("--karina-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = args.repository.resolve(strict=True)
    if (
        _git(root, "rev-parse", "HEAD^{commit}") != args.q20_sha
        or len(args.q20_sha) != 40
    ):
        raise ValueError("F20 freeze requires exact Q20")
    if _git(root, "status", "--porcelain=v1"):
        raise ValueError("F20 freeze requires a clean exact-Q20 worktree")
    if args.output.exists():
        raise FileExistsError("fresh F20 output already exists")
    q20_root = args.q20_root.resolve(strict=True)
    q20_summary = _load(q20_root / "qualification_summary.json")
    if q20_summary.get("status") != "PASS":
        raise ValueError("F20 cannot freeze a failed disclosed qualification")
    metadata_root = args.metadata_root.resolve(strict=True)
    pool = _load(metadata_root / "candidate_pool.json")
    validate_metadata_pool_v4(pool)
    metadata = _load(metadata_root / "metadata_receipts.json")
    if (
        metadata["source_jar_get_count"] != 0
        or metadata["source_body_bytes_received"] != 0
        or metadata["forbidden_body_request_count"] != 0
        or pool["pre_f20_source_body_bytes_received"] != 0
    ):
        raise ValueError("metadata-only phase received final source-body bytes")
    windows_cache = _load(args.windows_cache.resolve(strict=True))
    karina_cache = _load(args.karina_cache.resolve(strict=True))
    if any(
        report["source_body_bytes_read"] != 0
        for report in (windows_cache, karina_cache)
    ):
        raise ValueError("untouched cache census read source bodies")

    args.output.mkdir(parents=True)
    authority_path = root / "artifacts/authority/m336e_user_authority_v1.txt"
    authority_path.parent.mkdir(parents=True, exist_ok=True)
    authority_path.write_bytes(AUTHORITY)
    if bytes_hash(AUTHORITY) != M336E_AUTHORITY_STATEMENT_SHA256:
        raise AssertionError("exact M-33.6e authority statement hash drifted")
    authority = load_m336e_authority_registry(
        authority_path,
        expected_statement_sha256=M336E_AUTHORITY_STATEMENT_SHA256,
    ).root
    for name in (
        "candidate_pool.json",
        "metadata_receipts.json",
        "failure_simulation.json",
        "denylist_snapshot.json",
    ):
        shutil.copyfile(metadata_root / name, args.output / name)
    shutil.copyfile(args.windows_cache, args.output / "local_cache_windows.json")
    shutil.copyfile(args.karina_cache, args.output / "local_cache_karina.json")

    q20_rows = tuple(
        (
            path.relative_to(q20_root).as_posix(),
            bytes_hash(path.read_bytes()),
        )
        for path in sorted(q20_root.rglob("*"))
        if path.is_file()
    )
    tracked = _git(
        root,
        "ls-files",
        "src",
        "scripts",
        "tools",
        "tests",
        "schemas",
        "pyproject.toml",
        "uv.lock",
    ).splitlines()
    implementation_rows = tuple(
        (path, bytes_hash((root / path).read_bytes())) for path in tracked
    )
    evidence_policy = load_production_java_evidence_policy()
    contracts = M336E_PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY
    source_policy_body = {
        "schema_version": 2,
        "authority_root_hash": authority.root_hash,
        "authority_statement_sha256": M336E_AUTHORITY_STATEMENT_SHA256,
        "raw_source_retention": "LOCAL_SEALED_VAULT_ONLY",
        "raw_source_publication": "DENIED",
        "source_excerpt_publication": "DENIED",
        "derived_pack_publication": "ALLOWED_BY_FROZEN_USER_AUTHORITY",
        "metrics_publication": "ALLOWED_BY_FROZEN_USER_AUTHORITY",
        "authority_may_narrow": True,
        "authority_may_widen": False,
    }
    selector_body = {
        "schema_version": 2,
        "selector_version": M336E_FINAL_SELECTOR_VERSION,
        "selector_seed": M336E_FINAL_SELECTOR_SEED,
        "target_file_count": M336E_FINAL_TARGET,
        "minimum_selected_roots": 3,
        "maximum_files_per_root": M336E_FINAL_ROOT_CAP,
        "construct_quotas": M336E_DISCLOSED_CONSTRUCT_QUOTAS,
        "feasibility_before_reservation": True,
        "ranking_used_by_feasibility": False,
        "evaluator_reads": 0,
        "golden_reads": 0,
        "trust_metric_reads": 0,
    }
    threshold_body = {
        "schema_version": 2,
        "production_reference_spdx_agreement": "1.000000",
        "false_automatic_license_identities": 0,
        "selected_unresolved_license_disagreements": 0,
        "location_precision": "1.000000",
        "minimum_location_recall": "0.950000",
        "semantic_precision": "1.000000",
        "minimum_semantic_recall": "0.950000",
        "automatic_trust_precision": "1.000000",
        "minimum_trust_coverage": "0.850000",
        "wrong_trusted": 0,
        "field_evidence_exactness": "1.000000",
        "resolution_agreement": "1.000000",
        "post_trust_pack_failures": 0,
    }
    provider_body = {
        "schema_version": 2,
        "maven_provider": "MavenCentralProvenanceProvider.v1",
        "scm_provider": "ScmRevisionProvider.v2",
        "tree_sitter_version": TREE_SITTER_VERSION,
        "tree_sitter_java_version": TREE_SITTER_JAVA_VERSION,
        "tree_sitter_java_source_sha256": TREE_SITTER_JAVA_SOURCE_SHA256,
        "production_evidence_policy_hash": evidence_policy.manifest_hash,
        "java_spdx_reference_hash": bytes_hash(REFERENCE_SOURCE.read_bytes()),
        "semantic_jdk_provider": "m343-jdk21-semantic-oracle.v2",
    }
    allowlist_body = {
        "schema_version": 2,
        "https_hosts": ("codeload.github.com", "github.com", "repo.maven.apache.org"),
        "git_hosts": ("github.com",),
        "windows_source_body_acquisition_count": 1,
        "karina_source_body_acquisition_count": 0,
        "production_network_access_count": 0,
        "evaluation_runtime_network_access_count": 0,
    }
    orchestration_body = {
        "schema_version": 2,
        "q20_sha": args.q20_sha,
        "r20_sha": _git(root, "rev-parse", "HEAD^"),
        "implementation_tree_hash": content_hash(implementation_rows),
        "implementation_file_count": len(implementation_rows),
        "q20_evidence_tree_hash": content_hash(q20_rows),
        "q20_evidence_file_count": len(q20_rows),
        "acquisition_run_id": M336E_FINAL_ACQUISITION_RUN_ID,
        "protocol_version": M336E_PROTOCOL_VERSION,
        "protocol_event_order": RUN_PROTOCOL_EVENT_ORDER,
        "global_acquisition_count": 1,
        "selectability_census_count": 1,
        "selector_invocation_count": 1,
        "selector_rerun_count": 0,
        "production_before_evaluator": True,
        "two_production_seals_before_evaluation": True,
    }
    contract_body = {
        "schema_version": 2,
        "registry_hash": contracts.registry_hash,
        "contract_count": len(contracts.contracts),
        "contract_definitions": tuple(asdict(item) for item in contracts.contracts),
    }
    vault_body = {
        "schema_version": 2,
        "contract": "external-read-only-no-links-canonical-vault-path-v2",
        "canonical_order": "canonical_posix_path.encode(utf-8)",
        "portable_tree_from_manifest_rows": True,
        "raw_storage": "OUTSIDE_ALL_GIT_WORKTREES",
    }
    outcome_body = {
        "schema_version": 2,
        "outcome_a": "FRESH_JAVA_PROVEN",
        "outcome_b": "FRESH_JAVA_SEMANTICS_PASS_EXPORT_BLOCKED",
        "outcome_c": "BLOCKED",
        "criteria_may_be_weakened_after_f20": False,
    }
    values = {
        "source_use_policy.json": source_policy_body,
        "selector_policy.json": selector_body,
        "thresholds.json": threshold_body,
        "provider_identities.json": provider_body,
        "network_allowlist.json": allowlist_body,
        "orchestration.json": orchestration_body,
        "public_artifact_contract_v2.json": contract_body,
        "local_vault_contract_v2.json": vault_body,
        "outcome_logic.json": outcome_body,
    }
    for name, body in values.items():
        stem = Path(name).stem
        _write(args.output / name, {**body, f"{stem}_hash": content_hash(body)})
    artifacts = tuple(
        (path.name, bytes_hash(path.read_bytes()))
        for path in sorted(args.output.glob("*.json"), key=lambda item: item.name)
    )
    freeze_body = {
        "schema_version": 2,
        "q20_sha": args.q20_sha,
        "r20_sha": orchestration_body["r20_sha"],
        "authority_statement_sha256": M336E_AUTHORITY_STATEMENT_SHA256,
        "authority_root_hash": authority.root_hash,
        "candidate_pool_hash": pool["pool_hash"],
        "pre_f20_source_body_bytes_received": 0,
        "implementation_tree_hash": orchestration_body["implementation_tree_hash"],
        "q20_evidence_tree_hash": orchestration_body["q20_evidence_tree_hash"],
        "contract_registry_hash": contracts.registry_hash,
        "selector_policy_hash": content_hash(selector_body),
        "thresholds_hash": content_hash(threshold_body),
        "frozen_artifacts": artifacts,
    }
    _write(
        args.output / "m336e_freeze_manifest.json",
        {**freeze_body, "freeze_manifest_hash": content_hash(freeze_body)},
    )


if __name__ == "__main__":
    main()
