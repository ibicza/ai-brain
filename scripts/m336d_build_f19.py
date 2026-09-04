"""Assemble the exact metadata-only M-33.6d F19 freeze tree."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336d_authority import (
    M336D_AUTHORITY_STATEMENT_SHA256,
    load_pinned_authority_registry_for_development,
)
from ai_brain.stage3.acquisition.m336d_contracts import (
    PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY,
    LocalVaultRole,
)
from ai_brain.stage3.acquisition.m336d_final_pipeline import (
    M336D_MAXIMUM_ROOT_FRACTION,
    M336D_SELECTED_FILE_COUNT,
    M336D_SELECTOR_SEED,
    M336D_SELECTOR_VERSION,
    frozen_prior_identity_denylist,
    validate_candidate_pool,
)
from ai_brain.stage3.acquisition.m336d_spdx_reference import REFERENCE_SOURCE
from ai_brain.stage3.acquisition.spdx_license import SPDXLicenseMatcher

AUTHORITY = (
    b"M336D_USER_AUTHORITY_V1\n"
    b"source_use=PRIVATE_LOCAL_ANALYSIS,LOCAL_RESEARCH_EVALUATION,DERIVED_KNOWLEDGE_ONLY,RAW_SOURCE_RETENTION,PUBLIC_REPRODUCIBLE_EVALUATION\n"
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--r19-sha", required=True)
    parser.add_argument("--metadata-root", type=Path, required=True)
    parser.add_argument("--windows-cache", type=Path, required=True)
    parser.add_argument("--karina-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("fresh F19 output already exists")
    if len(args.r19_sha) != 40:
        raise ValueError("R19 SHA is not exact")
    head = subprocess.run(
        ("git", "rev-parse", "HEAD^{commit}"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ("git", "status", "--porcelain=v1"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if head != args.r19_sha or status:
        raise ValueError("F19 freeze must start from a clean exact-R19 worktree")
    pool = _load(args.metadata_root / "candidate_pool.json")
    validate_candidate_pool(pool)
    metadata = _load(args.metadata_root / "metadata_receipts.json")
    if metadata["source_jar_get_count"] or metadata["source_body_bytes_received"]:
        raise ValueError("metadata phase received source body bytes")
    args.output.mkdir(parents=True)
    authority_path = root / "artifacts/authority/m336d_user_authority_v1.txt"
    authority_path.parent.mkdir(parents=True, exist_ok=True)
    authority_path.write_bytes(AUTHORITY)
    if bytes_hash(AUTHORITY) != M336D_AUTHORITY_STATEMENT_SHA256:
        raise AssertionError("exact authority statement hash drifted")
    authority = load_pinned_authority_registry_for_development(
        authority_path,
        expected_statement_sha256=M336D_AUTHORITY_STATEMENT_SHA256,
    ).root
    for name in (
        "candidate_pool.json",
        "metadata_receipts.json",
        "failure_simulation.json",
    ):
        shutil.copyfile(args.metadata_root / name, args.output / name)
    shutil.copyfile(args.windows_cache, args.output / "local_cache_windows.json")
    shutil.copyfile(args.karina_cache, args.output / "local_cache_karina.json")
    source_policy = {
        "schema_version": 1,
        "authority_root_hash": authority.root_hash,
        "raw_source_retention": "LOCAL_SEALED_VAULT_ONLY",
        "raw_source_publication": "DENIED",
        "source_excerpt_publication": "DENIED",
        "derived_pack_publication": "ALLOWED_BY_FROZEN_USER_AUTHORITY",
        "metrics_publication": "ALLOWED_BY_FROZEN_USER_AUTHORITY",
        "policy_hash": authority.policy.policy_hash,
    }
    selector_body = {
        "schema_version": 1,
        "selector_version": M336D_SELECTOR_VERSION,
        "selector_seed": M336D_SELECTOR_SEED,
        "selected_file_count": M336D_SELECTED_FILE_COUNT,
        "minimum_selected_roots": 3,
        "maximum_one_root_fraction": M336D_MAXIMUM_ROOT_FRACTION,
        "selection_strategy": "round-robin sha256(F19+seed+family+canonical-path+source-hash)",
        "metrics_used": (),
        "oracle_golden_reads": 0,
    }
    selector = {**selector_body, "policy_hash": content_hash(selector_body)}
    threshold_body = {
        "schema_version": 1,
        "license_agreement": "1.000000",
        "false_automatic_license_identities": 0,
        "location_precision": "1.000000",
        "minimum_location_recall": "0.950000",
        "semantic_precision": "1.000000",
        "minimum_semantic_recall": "0.950000",
        "trust_precision": "1.000000",
        "minimum_trust_coverage": "0.850000",
        "wrong_trusted": 0,
        "field_evidence_exactness": "1.000000",
        "resolution_agreement": "1.000000",
        "post_trust_pack_failures": 0,
    }
    thresholds = {**threshold_body, "thresholds_hash": content_hash(threshold_body)}
    matcher = SPDXLicenseMatcher()
    provider_body = {
        "schema_version": 1,
        "maven_provider": "MavenCentralProvenanceProvider.v1",
        "scm_provider": "ScmRevisionProvider.v2",
        "production_matcher_hash": bytes_hash(
            Path(
                __import__(matcher.__class__.__module__, fromlist=["x"]).__file__
            ).read_bytes()
        ),
        "java_spdx_reference_hash": bytes_hash(REFERENCE_SOURCE.read_bytes()),
        "semantic_jdk_provider": "m343-jdk21-semantic-oracle.v2",
        "provider_identity_hash": content_hash(
            (
                "MavenCentralProvenanceProvider.v1",
                "ScmRevisionProvider.v2",
                bytes_hash(REFERENCE_SOURCE.read_bytes()),
            )
        ),
    }
    allowlist_body = {
        "schema_version": 1,
        "https_hosts": ("codeload.github.com", "github.com", "repo.maven.apache.org"),
        "git_hosts": ("github.com",),
        "source_body_acquisition_count": 1,
    }
    allowlist = {**allowlist_body, "allowlist_hash": content_hash(allowlist_body)}
    tracked = subprocess.run(
        (
            "git",
            "ls-files",
            "src",
            "scripts",
            "tools",
            "tests",
            "schemas",
        ),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    implementation_paths = tuple(root / path for path in tracked)
    implementation_rows = tuple(
        (path.relative_to(root).as_posix(), bytes_hash(path.read_bytes()))
        for path in implementation_paths
    )
    orchestration_body = {
        "schema_version": 1,
        "r19_sha": args.r19_sha,
        "implementation_tree_hash": content_hash(implementation_rows),
        "implementation_file_count": len(implementation_rows),
        "global_acquisition_count": 1,
        "selector_invocation_count": 1,
        "selector_rerun_count": 0,
        "production_before_evaluator": True,
        "karina_network_acquisition_count": 0,
    }
    orchestration = {
        **orchestration_body,
        "orchestration_hash": content_hash(orchestration_body),
    }
    contracts = {
        "schema_version": 1,
        "registry_hash": PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.registry_hash,
        "contracts": tuple(
            item.contract_hash
            for item in PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.contracts
        ),
        "contract_definitions": tuple(
            asdict(item) for item in PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.contracts
        ),
        "contract_hash": content_hash(
            PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.contracts
        ),
    }
    local_vault_contract_body = {
        "schema_version": 1,
        "contract": "external-read-only-no-links-hash-bound-v1",
        "roles": tuple(item.value for item in LocalVaultRole),
        "required_row_fields": (
            "candidate_id",
            "relative_canonical_path",
            "role",
            "byte_size",
            "sha256",
            "parent_artifact_identity",
            "source_use_receipt_hash",
            "row_hash",
        ),
    }
    denylist = frozen_prior_identity_denylist()
    denylist["denylist_hash"] = content_hash(denylist)
    values = {
        "source_use_policy.json": source_policy,
        "selector_policy.json": selector,
        "thresholds.json": thresholds,
        "provider_identities.json": provider_body,
        "network_allowlist.json": allowlist,
        "orchestration.json": orchestration,
        "public_artifact_contract.json": contracts,
        "local_vault_contract.json": {
            **local_vault_contract_body,
            "contract_hash": content_hash(local_vault_contract_body),
        },
        "denylist_snapshot.json": denylist,
    }
    for name, value in values.items():
        _write(args.output / name, value)
    artifacts = tuple(
        (path.name, bytes_hash(path.read_bytes()))
        for path in sorted(args.output.glob("*.json"), key=lambda item: item.name)
    )
    freeze_body = {
        "schema_version": 1,
        "r19_sha": args.r19_sha,
        "authority_statement_sha256": M336D_AUTHORITY_STATEMENT_SHA256,
        "authority_root_hash": authority.root_hash,
        "candidate_pool_hash": pool["pool_hash"],
        "selector_policy_hash": selector["policy_hash"],
        "thresholds_hash": thresholds["thresholds_hash"],
        "contract_registry_hash": PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.registry_hash,
        "frozen_artifacts": artifacts,
    }
    _write(
        args.output / "m336d_freeze_manifest.json",
        {**freeze_body, "freeze_manifest_hash": content_hash(freeze_body)},
    )
    PUBLIC_FINAL_ARTIFACT_CONTRACT_REGISTRY.validate(
        "freeze/m336d_freeze_manifest.json",
        (args.output / "m336d_freeze_manifest.json").read_bytes(),
    )


if __name__ == "__main__":
    main()
