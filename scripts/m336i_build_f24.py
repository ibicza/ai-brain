"""Build the immutable M-33.6i F24 authority without a future commit SHA."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import urllib.parse
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_jdk_provider import (
    verify_m336_jdk_provider_evidence,
)
from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)
from ai_brain.stage3.acquisition.m336i_acquisition import (
    M336I_FINAL_ACQUISITION_RUN_ID,
    M336I_FREEZE_MANIFEST_PATH,
    M336I_FROZEN_AUTHORIZATION_PATH,
    acquisition_provider_identity,
    build_m336i_final_acquisition_authorization,
    compute_m336i_freeze_tree_identity,
    validate_m336i_candidate_pool,
)
from ai_brain.stage3.acquisition.m336i_readiness import (
    M336I_EXACT_Q23_SHA,
    readiness_result_from_dict,
    verify_m336i_quality_receipt,
)
from ai_brain.stage3.acquisition.m336i_registry import (
    M336I_SELECTOR_SEED,
    build_m336i_final_java_route_manifest,
    build_m336i_final_java_route_registry,
)
from ai_brain.stage3.acquisition.m336i_route import M336I_ROUTE_STATES


def _object(path: Path) -> dict:
    value = strict_json_file(path)
    if not isinstance(value, dict):
        raise TypeError("M336I freeze input must be an object")
    return value


def _verify_hash(value: dict, field: str) -> str:
    body = dict(value)
    claimed = body.pop(field, None)
    if content_hash(body) != claimed:
        raise ValueError(f"M336I freeze input {field} changed")
    return claimed


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source.resolve(strict=True), target)


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in (
        "repository",
        "readiness",
        "candidate_pool",
        "denylist",
        "authority_root",
        "authority_statement",
        "threshold_manifest",
        "publication_boundary_contract",
        "public_artifact_contract",
        "compiler_jdk_identities",
        "karina_host_identity_receipt",
        "frozen_spdx_reference",
        "windows_q24_quality_receipt",
        "karina_q24_quality_receipt",
        "windows_javac",
        "output",
    ):
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, required=True)
    parser.add_argument("--expected-q24-sha", required=True)
    parser.add_argument("--branch-ref", required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    output = args.output.resolve(strict=False)
    required_output = (repository / M336I_FROZEN_AUTHORIZATION_PATH).parent
    if output != required_output:
        raise ValueError("M336I F24 output path is not the frozen authority path")
    if output.exists():
        raise FileExistsError("M336I F24 authority destination must be fresh")
    head = _git(repository, "rev-parse", "HEAD^{commit}")
    status = _git(repository, "status", "--porcelain=v1")
    if head != args.expected_q24_sha or status:
        raise ValueError("M336I F24 builder requires clean exact Q24")
    readiness = readiness_result_from_dict(_object(args.readiness))
    if (
        readiness.exact_q23_sha != M336I_EXACT_Q23_SHA
        or _git(repository, "rev-parse", "HEAD^1") != readiness.exact_r24_sha
    ):
        raise ValueError("M336I F24 parent chain differs from readiness")
    windows_q24_quality = verify_m336i_quality_receipt(
        args.windows_q24_quality_receipt, "WINDOWS", args.expected_q24_sha
    )
    karina_q24_quality = verify_m336i_quality_receipt(
        args.karina_q24_quality_receipt, "KARINA", args.expected_q24_sha
    )

    pool = _object(args.candidate_pool)
    validate_m336i_candidate_pool(pool)
    denylist = _object(args.denylist)
    authority = _object(args.authority_root)
    thresholds = _object(args.threshold_manifest)
    publication = _object(args.publication_boundary_contract)
    public_contract = _object(args.public_artifact_contract)
    jdk = _object(args.compiler_jdk_identities)
    karina_host = _object(args.karina_host_identity_receipt)
    spdx = _object(args.frozen_spdx_reference)
    denylist_hash = _verify_hash(denylist, "denylist_hash")
    authority_hash = _verify_hash(authority, "authority_root_hash")
    threshold_hash = _verify_hash(thresholds, "threshold_manifest_hash")
    publication_hash = _verify_hash(publication, "publication_boundary_policy_hash")
    public_contract_hash = _verify_hash(
        public_contract, "public_artifact_contract_hash"
    )
    _verify_hash(jdk, "compiler_jdk_identities_hash")
    karina_host_hash = _verify_hash(karina_host, "receipt_hash")
    spdx_hash = _verify_hash(spdx, "snapshot_manifest_hash")
    if bytes_hash(args.authority_statement.read_bytes()) != authority.get(
        "authority_statement_sha256"
    ):
        raise ValueError("M336I inherited authority statement bytes changed")
    _private_jdk, windows_jdk = verify_m336_jdk_provider_evidence(
        platform="windows",
        java=args.windows_javac.with_name("java.exe"),
        javac=args.windows_javac,
    )
    if windows_jdk.receipt_hash != jdk.get(
        "windows_public_jdk_receipt_hash"
    ) or karina_host.get("public_jdk_identity_receipt_hash") != jdk.get(
        "karina_public_jdk_receipt_hash"
    ):
        raise ValueError("M336I frozen platform JDK identities changed")

    registry = build_m336i_final_java_route_registry()
    route = build_m336i_final_java_route_manifest(registry)
    if (
        registry.registry_hash != readiness.route_registry_hash
        or route.manifest_hash != readiness.route_manifest_hash
    ):
        raise ValueError("M336I live route differs from qualified R24")
    hosts = tuple(
        sorted(
            {
                urllib.parse.urlsplit(candidate[name]).hostname
                for candidate in pool["candidates"]
                for name in (
                    "source_url",
                    "pom_url",
                    "scm_repository",
                    "scm_archive_head_url",
                )
                if candidate.get(name)
            }
        )
    )
    if None in hosts:
        raise ValueError("M336I frozen candidate contains a hostless URL")
    acquisition_body = {
        "schema_version": 1,
        "acquisition_run_id": M336I_FINAL_ACQUISITION_RUN_ID,
        "acquire_every_frozen_candidate": True,
        "replacement_candidates_allowed": False,
        "adaptive_family_substitution_allowed": False,
        "global_acquisition_count": 1,
        "windows_acquisition_count": 1,
        "karina_acquisition_count": 0,
        "acquisition_reruns_allowed": False,
        "allowed_network_hosts": list(hosts),
    }
    acquisition_policy = {
        **acquisition_body,
        "acquisition_policy_hash": content_hash(acquisition_body),
    }
    selector_body = {
        "schema_version": 1,
        "selector_algorithm": "m336f.compilation-closure-selector.v1",
        "selector_seed": M336I_SELECTOR_SEED,
        "target_selected_files": 180,
        "minimum_selected_roots": 3,
        "maximum_files_per_root": 63,
        "feasibility_before_reservation": True,
        "selector_reservation_count": 1,
        "selector_invocation_count": 1,
        "selector_rerun_count": 0,
    }
    selector = {**selector_body, "selector_policy_hash": content_hash(selector_body)}
    state_body = {
        "schema_version": 1,
        "route_version": route.route_version,
        "states": list(M336I_ROUTE_STATES),
        "state_count": len(M336I_ROUTE_STATES),
        "skipped_states_allowed": False,
        "repeated_states_allowed": False,
    }
    state_contract = {
        **state_body,
        "state_machine_contract_hash": content_hash(state_body),
    }
    commit_body = {
        "schema_version": 1,
        "exact_q23_sha": M336I_EXACT_Q23_SHA,
        "exact_q24_sha": args.expected_q24_sha,
        "required_commit_messages": [
            "M-33.6i freeze authorized final Java acquisition",
            "M-33.6i publish final Java production evidence",
            "M-33.6i publish final Java Outcome A evidence",
        ],
        "merge_commits_allowed": 0,
        "post_f24_implementation_changes_allowed": False,
    }
    commit_protocol = {
        **commit_body,
        "commit_protocol_hash": content_hash(commit_body),
    }
    outcome_body = {
        "schema_version": 1,
        "pre_freeze_failure": "PRE_FREEZE_BLOCKED",
        "post_freeze_failure": "OUTCOME C — BLOCKED",
        "success": "OUTCOME A",
        "acquisition_retry_allowed": False,
        "selector_retry_allowed": False,
        "threshold_tuning_after_final_corpus_allowed": False,
    }
    outcome = {**outcome_body, "outcome_logic_hash": content_hash(outcome_body)}
    spdx_binding_body = {
        "schema_version": 1,
        "snapshot_manifest_hash": spdx_hash,
        "snapshot_bytes_hash": bytes_hash(args.frozen_spdx_reference.read_bytes()),
        "license_list_version": spdx["license_list_version"],
    }
    spdx_binding = {
        **spdx_binding_body,
        "spdx_reference_binding_hash": content_hash(spdx_binding_body),
    }

    output.mkdir(parents=True)
    write_canonical_json(output / "route_component_registry.json", registry)
    write_canonical_json(output / "route_manifest.json", route)
    write_canonical_json(output / "acquisition_policy.json", acquisition_policy)
    write_canonical_json(output / "selector_policy.json", selector)
    write_canonical_json(output / "route_state_machine_contract.json", state_contract)
    write_canonical_json(output / "commit_protocol.json", commit_protocol)
    write_canonical_json(output / "outcome_logic.json", outcome)
    write_canonical_json(output / "spdx_reference_binding.json", spdx_binding)
    for source, name in (
        (args.candidate_pool, "candidate_pool.json"),
        (args.denylist, "denylist.json"),
        (args.authority_root, "authority_root.json"),
        (args.authority_statement, "authority_statement.txt"),
        (args.threshold_manifest, "threshold_manifest.json"),
        (args.publication_boundary_contract, "publication_boundary_contract.json"),
        (args.public_artifact_contract, "public_artifact_contract.json"),
        (args.compiler_jdk_identities, "compiler_jdk_identities.json"),
        (args.karina_host_identity_receipt, "karina_host_identity_receipt.json"),
        (args.windows_q24_quality_receipt, "windows_q24_quality_receipt.json"),
        (args.karina_q24_quality_receipt, "karina_q24_quality_receipt.json"),
    ):
        _copy(source, output / name)

    freeze_tree_identity = compute_m336i_freeze_tree_identity(repository)
    provider_source, provider_signature = acquisition_provider_identity()
    authorization = build_m336i_final_acquisition_authorization(
        acquisition_mode="FINAL",
        exact_q23_sha=M336I_EXACT_Q23_SHA,
        r24_implementation_tree_identity=readiness.r24_implementation_tree_identity,
        q24_evidence_identity=readiness.q24_evidence_identity,
        f24_parent_sha=args.expected_q24_sha,
        f24_freeze_tree_identity=freeze_tree_identity,
        route_registry_hash=registry.registry_hash,
        route_manifest_hash=route.manifest_hash,
        acquisition_provider_source_hash=provider_source,
        acquisition_provider_callable_signature_hash=provider_signature,
        candidate_pool_hash=pool["pool_hash"],
        acquisition_policy_hash=acquisition_policy["acquisition_policy_hash"],
        denylist_hash=denylist_hash,
        authority_root_hash=authority_hash,
        selector_policy_hash=selector["selector_policy_hash"],
        threshold_manifest_hash=threshold_hash,
        publication_boundary_hash=publication_hash,
        public_artifact_contract_hash=public_contract_hash,
        windows_public_jdk_identity_receipt_hash=jdk["windows_public_jdk_receipt_hash"],
        karina_public_jdk_identity_receipt_hash=jdk["karina_public_jdk_receipt_hash"],
        karina_stable_host_identity_receipt_hash=karina_host_hash,
        acquisition_run_id=M336I_FINAL_ACQUISITION_RUN_ID,
        allowed_network_hosts=hosts,
        expected_global_acquisition_count=1,
        expected_windows_acquisition_count=1,
        expected_karina_acquisition_count=0,
        branch_ref=args.branch_ref,
    )
    write_canonical_json(repository / M336I_FROZEN_AUTHORIZATION_PATH, authorization)
    freeze_body = {
        "schema_version": 1,
        "contract_role": "M336I_IMMUTABLE_FINAL_FREEZE",
        "exact_q23_sha": M336I_EXACT_Q23_SHA,
        "f24_parent_sha": args.expected_q24_sha,
        "r24_implementation_tree_identity": readiness.r24_implementation_tree_identity,
        "q24_evidence_identity": readiness.q24_evidence_identity,
        "windows_q24_quality_receipt_hash": windows_q24_quality["receipt_hash"],
        "karina_q24_quality_receipt_hash": karina_q24_quality["receipt_hash"],
        "f24_freeze_tree_identity": freeze_tree_identity,
        "authorization_hash": authorization.authorization_hash,
        "route_registry_hash": registry.registry_hash,
        "route_manifest_hash": route.manifest_hash,
        "acquisition_provider_source_hash": provider_source,
        "acquisition_provider_callable_signature_hash": provider_signature,
        "independent_evaluator_implementation_identity": (
            readiness.independent_evaluator_implementation_identity
        ),
        "candidate_pool_hash": pool["pool_hash"],
        "acquisition_policy_hash": acquisition_policy["acquisition_policy_hash"],
        "denylist_hash": denylist_hash,
        "authority_root_hash": authority_hash,
        "selector_policy_hash": selector["selector_policy_hash"],
        "threshold_manifest_hash": threshold_hash,
        "publication_boundary_hash": publication_hash,
        "public_artifact_contract_hash": public_contract_hash,
        "compiler_jdk_identities_hash": jdk["compiler_jdk_identities_hash"],
        "karina_host_identity_receipt_hash": karina_host_hash,
        "state_machine_contract_hash": state_contract["state_machine_contract_hash"],
        "spdx_reference_binding_hash": spdx_binding["spdx_reference_binding_hash"],
        "commit_protocol_hash": commit_protocol["commit_protocol_hash"],
        "outcome_logic_hash": outcome["outcome_logic_hash"],
    }
    write_canonical_json(
        repository / M336I_FREEZE_MANIFEST_PATH,
        {**freeze_body, "manifest_hash": content_hash(freeze_body)},
    )
    if compute_m336i_freeze_tree_identity(repository) != freeze_tree_identity:
        raise ValueError("M336I prospective F24 tree identity changed while freezing")
    print(
        canonical_json(
            {
                "authorization_hash": authorization.authorization_hash,
                "f24_freeze_tree_identity": freeze_tree_identity,
                "status": "F24_READY_TO_COMMIT",
            }
        )
    )


if __name__ == "__main__":
    main()
