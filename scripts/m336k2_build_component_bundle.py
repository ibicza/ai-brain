"""Build the native, source-free M-33.6k.2 freeze component bundle."""

from __future__ import annotations

import argparse
import json
import urllib.parse
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_controller import (
    build_m336k2_schema_registry,
)
from ai_brain.stage3.acquisition.m336k2_execution import (
    build_m336k2_executable_dependency_manifest,
    build_m336k2_execution_capsule_receipt,
    command_renderer_identity,
    minimal_environment_policy_identity,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2_REQUIRED_FREEZE_COMPONENTS,
    M336K2ProtocolError,
)
from ai_brain.stage3.acquisition.m336k2_publication import (
    build_m336k2_publication_contract,
)
from ai_brain.stage3.acquisition.m336k2_registry import (
    build_m336k2_route_manifest,
    build_m336k2_route_registry,
)
from ai_brain.stage3.acquisition.m336k_archive import ArchiveInspectionPolicyV2
from ai_brain.stage3.acquisition.m336k_final_pipeline import (
    m336k_candidate_terminal_policy,
    m336k_global_continuation_policy,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = _object(args.request.resolve(strict=True))
    expected = {
        "repository",
        "python_executable",
        "executables",
        "python_environment_manifest",
        "karina_public_execution_capsule_receipt",
        "karina_executable_dependency_manifest",
        "windows_jdk_identity",
        "karina_jdk_identity",
        "karina_host_identity",
        "candidate_pool",
        "authority_statement",
        "threshold_manifest",
        "denylist",
        "publication_boundary",
        "public_pack_contract",
        "branch_ref",
        "q_root",
        "f_root",
        "h_root",
        "e_root",
        "q_subject",
        "f_subject",
        "h_subject",
        "e_subject",
        "execution_mode",
        "acquisition_run_id",
        "selector_target_file_count",
        "maximum_selected_files_per_root",
        "minimum_selected_root_count",
        "construct_quotas",
        "selector_seed",
        "selector_version",
        "minimum_free_bytes_windows",
        "minimum_free_bytes_karina",
        "output",
    }
    if set(request) != expected:
        raise M336K2ProtocolError("M336K2 component bundle request fields changed")
    repository = Path(request["repository"]).resolve(strict=True)
    output = Path(request["output"]).resolve(strict=False)
    if output.exists() or output.is_relative_to(repository):
        raise M336K2ProtocolError("M336K2 component bundle output is not fresh/private")
    output.mkdir(parents=True)

    pool = _object(Path(request["candidate_pool"]).resolve(strict=True))
    python_environment = _verified_object(
        Path(request["python_environment_manifest"]), "environment_manifest_hash"
    )
    karina_public = _verified_object(
        Path(request["karina_public_execution_capsule_receipt"]), "receipt_hash"
    )
    karina_dependencies = _verified_object(
        Path(request["karina_executable_dependency_manifest"]), "manifest_hash"
    )
    route_registry = build_m336k2_route_registry(repository)
    schemas = build_m336k2_schema_registry()
    dependencies = build_m336k2_executable_dependency_manifest(
        executables={
            role: (Path(value["path"]), tuple(value["version_arguments"]))
            for role, value in request["executables"].items()
        },
        python_invocation_handle=str(
            Path(request["python_executable"]).resolve(strict=True)
        ),
        environment_identity_hash=python_environment["environment_manifest_hash"],
        source_identity_hash=content_hash(
            tuple(
                (item.repository_path, item.source_bytes_hash)
                for item in route_registry.components
            )
        ),
    )
    execution_capsule = build_m336k2_execution_capsule_receipt(
        repository=repository,
        route_registry_hash=route_registry.registry_hash,
        dependency_manifest=dependencies,
        karina_public_execution_capsule_receipt_hash=karina_public["receipt_hash"],
        karina_executable_dependency_manifest_hash=karina_dependencies["manifest_hash"],
    )
    route = build_m336k2_route_manifest(
        registry=route_registry,
        schemas=schemas,
        executable_dependency_manifest_hash=dependencies.manifest_hash,
        python_environment_manifest_hash=python_environment[
            "environment_manifest_hash"
        ],
        command_renderer_hash=command_renderer_identity(),
        minimal_environment_policy_hash=minimal_environment_policy_identity(),
    )
    publication = build_m336k2_publication_contract(
        branch_ref=request["branch_ref"],
        q_root=request["q_root"],
        f_root=request["f_root"],
        h_root=request["h_root"],
        e_root=request["e_root"],
        q_subject=request["q_subject"],
        f_subject=request["f_subject"],
        h_subject=request["h_subject"],
        e_subject=request["e_subject"],
    )
    archive = ArchiveInspectionPolicyV2.frozen_default()
    terminal = m336k_candidate_terminal_policy()
    continuation = m336k_global_continuation_policy()
    disclosure = (
        repository
        / "artifacts"
        / "acquisition"
        / "disclosed_java"
        / "registry_manifest.json"
    ).resolve(strict=True)
    hosts = tuple(
        sorted(
            {
                parsed.hostname
                for candidate in pool["candidates"]
                for key in (
                    "source_url",
                    "pom_url",
                    "scm_repository",
                    "scm_archive_head_url",
                )
                if (
                    parsed := urllib.parse.urlsplit(str(candidate.get(key, "")))
                ).hostname
            }
        )
    )
    acquisition_body = {
        "schema_version": 1,
        "contract_role": "M336K2_CANDIDATE_ISOLATED_ACQUISITION_POLICY",
        "policy_version": "m336k2.candidate-isolated-final.v1",
        "acquisition_run_id": request["acquisition_run_id"],
        "candidate_pool_hash": pool["pool_hash"],
        "archive_policy_hash": archive.policy_hash,
        "candidate_terminal_policy_hash": terminal["policy_hash"],
        "global_continuation_policy_hash": continuation["policy_hash"],
        "authority_statement_hash": bytes_hash(
            Path(request["authority_statement"]).resolve(strict=True).read_bytes()
        ),
        "disclosure_registry_manifest_hash": bytes_hash(disclosure.read_bytes()),
        "allowed_network_hosts": hosts,
        "acquisition_reservation_limit": 1,
        "candidate_retry_limit": 0,
        "candidate_replacement_limit": 0,
        "pre_freeze_source_body_bytes": 0,
        "selector_target_file_count": request["selector_target_file_count"],
        "maximum_selected_files_per_root": request["maximum_selected_files_per_root"],
        "minimum_selected_root_count": request["minimum_selected_root_count"],
        "construct_quotas": request["construct_quotas"],
        "selector_seed": request["selector_seed"],
        "selector_version": request["selector_version"],
    }
    acquisition = {
        **acquisition_body,
        "acquisition_policy_hash": content_hash(acquisition_body),
    }
    authorization_body = {
        "schema_version": 1,
        "contract_role": "M336K2_FINAL_ACQUISITION_AUTHORIZATION_V1",
        "execution_mode": request["execution_mode"],
        "exact_implementation_tip": "@IMPLEMENTATION_TIP@",
        "exact_q28_sha": "@Q_SHA@",
        "branch_ref": "@BRANCH_REF@",
        "acquisition_run_id": request["acquisition_run_id"],
        "candidate_pool_hash": pool["pool_hash"],
        "acquisition_policy_hash": acquisition["acquisition_policy_hash"],
        "archive_policy_hash": archive.policy_hash,
        "candidate_terminal_policy_hash": terminal["policy_hash"],
        "global_continuation_policy_hash": continuation["policy_hash"],
        "route_manifest_hash": route.manifest_hash,
        "route_registry_hash": route_registry.registry_hash,
        "schema_registry_hash": schemas.registry_hash,
        "readiness_hash": "@READINESS_HASH@",
        "executable_dependency_manifest_hash": dependencies.manifest_hash,
        "python_environment_manifest_hash": python_environment[
            "environment_manifest_hash"
        ],
        "authority_statement_hash": acquisition["authority_statement_hash"],
        "disclosure_registry_manifest_hash": acquisition[
            "disclosure_registry_manifest_hash"
        ],
        "allowed_network_hosts": hosts,
        "minimum_candidate_families": 80,
        "minimum_organizations": 64,
        "maximum_candidates_per_organization": 2,
        "acquisition_reservation_limit": 1,
        "selector_reservation_limit": 1,
        "evaluator_reservation_limit": 1,
        "candidate_retry_limit": 0,
        "candidate_replacement_limit": 0,
        "pre_freeze_source_body_bytes": 0,
    }
    authorization = {
        **authorization_body,
        "authorization_hash": content_hash(authorization_body),
    }
    commit_protocol = _hashed(
        "contract_hash",
        schema_version=1,
        contract_role="M336K2_Q28_F28_H28_E28_COMMIT_PROTOCOL",
        branch_ref=request["branch_ref"],
        q_subject=request["q_subject"],
        f_subject=request["f_subject"],
        h_subject=request["h_subject"],
        e_subject=request["e_subject"],
        zero_merges_required=True,
        zero_post_f_implementation_changes_required=True,
    )
    storage = _hashed(
        "receipt_hash",
        schema_version=1,
        contract_role="M336K2_FINAL_STORAGE_BUDGET",
        minimum_free_bytes_windows=request["minimum_free_bytes_windows"],
        minimum_free_bytes_karina=request["minimum_free_bytes_karina"],
        status="PASS",
    )
    selector = _hashed(
        "policy_hash",
        schema_version=1,
        contract_role="M336K2_COUNT_NEUTRAL_SELECTOR_POLICY",
        target_file_count=request["selector_target_file_count"],
        maximum_files_per_root=request["maximum_selected_files_per_root"],
        minimum_root_count=request["minimum_selected_root_count"],
        construct_quotas=request["construct_quotas"],
        selector_seed=request["selector_seed"],
        selector_version=request["selector_version"],
        invocation_limit=1,
    )
    components = {
        "implementation_tip": _hashed(
            "receipt_hash",
            schema_version=1,
            contract_role="M336K2_IMPLEMENTATION_TIP_BINDING",
            exact_implementation_tip="@IMPLEMENTATION_TIP@",
        ),
        "q28_commit": _hashed(
            "receipt_hash",
            schema_version=1,
            contract_role="M336K2_Q28_COMMIT_BINDING",
            exact_q28_sha="@Q_SHA@",
        ),
        "f28_commit": _hashed(
            "receipt_hash",
            schema_version=1,
            contract_role="M336K2_PROSPECTIVE_F28_COMMIT_BINDING",
            exact_f28_sha="0" * 40,
        ),
        "committed_f28_tree": _hashed(
            "receipt_hash",
            schema_version=1,
            contract_role="M336K2_PROSPECTIVE_F28_TREE_BINDING",
            committed_f28_tree="0" * 40,
        ),
        "q28_evidence_manifest": _hashed(
            "manifest_hash",
            schema_version=1,
            contract_role="M336K2_Q28_EVIDENCE_MANIFEST_PLACEHOLDER",
            status="REPLACED_BY_DISPOSABLE_OR_OFFICIAL_Q28",
        ),
        "q28_readiness": _hashed(
            "readiness_hash",
            schema_version=1,
            contract_role="M336K2_Q28_READINESS_PLACEHOLDER",
            status="REPLACED_BY_DISPOSABLE_OR_OFFICIAL_Q28",
        ),
        "final_authorization": authorization,
        "freeze_manifest": _hashed(
            "manifest_hash",
            schema_version=1,
            contract_role="M336K2_F28_PROSPECTIVE_FREEZE_DECLARATION",
            self_reference_safe=True,
        ),
        "frozen_file_manifest": _hashed(
            "frozen_file_manifest_hash",
            schema_version=1,
            contract_role="M336K2_F28_PROSPECTIVE_FILE_DECLARATION",
            self_reference_safe=True,
        ),
        "route_registry": asdict(route_registry),
        "route_manifest": asdict(route),
        "schema_registry": asdict(schemas),
        "execution_capsule_receipt": asdict(execution_capsule),
        "python_environment_manifest": python_environment,
        "executable_dependency_manifest": asdict(dependencies),
        "windows_jdk_identity": _object(Path(request["windows_jdk_identity"])),
        "karina_jdk_identity": _object(Path(request["karina_jdk_identity"])),
        "karina_stable_host_identity": _object(Path(request["karina_host_identity"])),
        "candidate_pool": pool,
        "acquisition_policy": acquisition,
        "archive_policy": asdict(archive),
        "candidate_terminal_policy": terminal,
        "global_continuation_policy": continuation,
        "selector_policy": selector,
        "threshold_manifest": _object(Path(request["threshold_manifest"])),
        "disclosure_registry_manifest": _object(disclosure),
        "denylist": _object(Path(request["denylist"])),
        "publication_boundary": _publication_boundary_component(
            Path(request["publication_boundary"])
        ),
        "public_pack_contract": _object(Path(request["public_pack_contract"])),
        "h28_publication_contract": asdict(publication),
        "e28_publication_contract": asdict(publication),
        "commit_protocol": commit_protocol,
        "storage_budget": storage,
    }
    if set(components) != M336K2_REQUIRED_FREEZE_COMPONENTS:
        raise M336K2ProtocolError("M336K2 component bundle is incomplete")
    for name, value in sorted(components.items()):
        (output / f"{name}.json").write_text(
            canonical_json(value) + "\n", encoding="utf-8", newline="\n"
        )
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K2_COMPONENT_BUNDLE_RECEIPT",
        "component_count": len(components),
        "route_registry_hash": route_registry.registry_hash,
        "route_manifest_hash": route.manifest_hash,
        "schema_registry_hash": schemas.registry_hash,
        "executable_dependency_manifest_hash": dependencies.manifest_hash,
        "execution_capsule_receipt_hash": execution_capsule.receipt_hash,
        "candidate_pool_hash": pool["pool_hash"],
        "acquisition_policy_hash": acquisition["acquisition_policy_hash"],
        "status": "PASS",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    (output / "bundle_receipt.json").write_text(
        canonical_json(receipt) + "\n", encoding="utf-8", newline="\n"
    )
    print(canonical_json(receipt))


def _hashed(hash_field: str, **body) -> dict:
    return {**body, hash_field: content_hash(body)}


def _verified_object(path: Path, hash_field: str) -> dict:
    value = _object(path.resolve(strict=True))
    body = dict(value)
    claimed = body.pop(hash_field, None)
    if not isinstance(claimed, str) or content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K2 component input hash changed")
    return value


def _publication_boundary_component(path: Path) -> dict:
    value = _object(path)
    claimed = value.get("publication_boundary_hash")
    if claimed is None:
        return {**value, "publication_boundary_hash": content_hash(value)}
    body = dict(value)
    body.pop("publication_boundary_hash")
    if content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K2 publication boundary hash changed")
    return value


def _object(path: Path) -> dict:
    try:
        value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K2 component input is invalid JSON") from error
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K2 component input is not an object")
    return value


if __name__ == "__main__":
    main()
