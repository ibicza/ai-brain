"""Overlay typed M-33.6k.5 identities onto a freshly built native bundle."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_authorization import (
    M336K5FinalAuthorization,
    build_m336k5_final_authorization,
)
from ai_brain.stage3.acquisition.m336k5_identity import (
    M336K5AcquisitionRunId,
    M336K5EvaluatorRunId,
    M336K5ExecutionMode,
    M336K5ProtocolRunId,
    M336K5RouteIdentityBundle,
    M336K5SelectorRunId,
    build_m336k5_official_identity_bundle,
    build_m336k6_official_identity_bundle,
    build_m336k7_official_identity_bundle,
    build_m336k8_official_identity_bundle,
    build_m336k_identity_bundle_for_profile,
)
from ai_brain.stage3.acquisition.m336k5_registry import (
    build_m336k5_route_manifest,
    build_m336k5_route_registry,
    build_m336k5_schema_registry,
)
from ai_brain.stage3.acquisition.m336k5_request import (
    M336K5_FINAL_REQUEST_BUILDER_HASH,
    M336K5_FINAL_REQUEST_CONTRACT,
)
from ai_brain.stage3.acquisition.m336k5_startup import M336K5PythonStartupPolicy
from ai_brain.stage3.acquisition.m336k6_capsule import (
    M336K6CapsuleContentManifest,
)
from ai_brain.stage3.acquisition.m336k7_contracts import (
    M336K7FrozenContractCompatibilityGate,
    M336K7LegacyCapsuleCompatibilityReceipt,
    M336K7PersistentCapsuleBindingSet,
    M336K7PostFreezeInputBundle,
    M336K7ResourceBudgetPolicy,
    M336K7ResourceGateReceipt,
    M336K7ResourceObservationReceipt,
    M336K7StrictArtifact,
    build_m336k7_persistent_capsule_route_manifest,
    build_m336k7_persistent_capsule_route_registry,
    storage_reservation_from_dict,
    verify_m336k7_capsule_compatibility_binding,
    verify_m336k7_persistent_capsule_route_binding,
    verify_m336k7_resource_gate_binding,
    verify_m336k7_unchanged_candidate_pool,
)
from ai_brain.stage3.acquisition.m336k7_freeze import (
    M336K7_FREEZE_MANIFEST_CONTRACT,
    M336K7_FREEZE_MANIFEST_CONTRACT_HASH,
)
from ai_brain.stage3.acquisition.m336k7_request import (
    M336K7_FINAL_REQUEST_BUILDER_HASH,
    M336K7_FINAL_REQUEST_CONTRACT,
)
from ai_brain.stage3.acquisition.m336k8_contracts import (
    M336K8BridgeSurfaceManifest,
    M336K8ControllerStartupBinding,
    M336K8FreezeAssemblyPlan,
    M336K8FreezeInputAssembler,
    M336K8FrozenContractCompatibilityGateV2,
    M336K8LegacyControllerAliasReceipt,
    M336K8PersistentCapsuleSourceBinding,
    M336K8PostFreezeInputBundleV2,
    M336K8ProjectSourceIdentityPolicy,
    M336K8ProjectSourceIdentityReceipt,
    M336K8SourceDomainCompatibilityReceipt,
    M336K10PostFreezeInputBundle,
    m336k8_semantic_binding_mismatches,
)
from ai_brain.stage3.acquisition.m336k8_request import (
    M336K8_FINAL_REQUEST_BUILDER_HASH,
    M336K8_FINAL_REQUEST_CONTRACT,
)
from ai_brain.stage3.acquisition.m336k8_request import (
    _compatibility_artifacts as _m336k8_compatibility_artifacts,
)
from ai_brain.stage3.acquisition.m336k9_admission import (
    M336K9_CONTROLLER_ADMISSION_CONTRACT,
    M336K9_CONTROLLER_ADMISSION_CONTRACT_HASH,
    run_m336k_official_profile_coverage_gate,
)
from ai_brain.stage3.acquisition.m336k9_authorization import (
    build_m336k9_final_authorization,
    build_m336k10_final_authorization,
    m336k_current_final_authorization_from_dict,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    M336KOfficialRouteProfileStatus,
    m336k_official_profile_registry,
)
from ai_brain.stage3.acquisition.m336k10_binding import (
    M336K10_EXECUTION_SCOPE_HISTORICAL,
    M336K10_EXECUTION_SCOPE_OFFICIAL,
    M336K10_EXECUTION_SCOPE_SHARED,
    M336K10_PROFILE_ID,
    M336K10FreezeOriginEntry,
    M336K10FreezeOriginReceipt,
    build_m336k10_post_authorization_components,
    build_official_acquisition_components,
    build_rehearsal_acquisition_components,
    read_provider_sources,
    verify_m336k10_official_acquisition_binding,
)

_LABEL = re.compile(r"[a-z0-9][a-z0-9-]{3,63}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    request = _object(args.request.resolve(strict=True))
    base_expected = {
        "repository",
        "legacy_bundle",
        "exact_implementation_tip",
        "exact_q30_sha",
        "branch_ref",
        "readiness_hash",
        "q_readiness",
        "q_evidence_manifest",
        "identity_mode",
        "disposable_label",
        "output",
        "python_environment_manifest",
        "python_startup_policy",
        "python_startup_bootstrap",
        "windows_python_launcher",
        "karina_python_launcher",
        "sanitized_environment_policy",
        "startup_receipt_schema",
        "resource_budget",
        "storage_reservation",
        "resource_monitor",
        "cleanup_policy",
        "recovery_checkpoint_policy",
    }
    lifecycle_components = {
        "persistent_capsule_receipt",
        "capsule_content_manifest",
        "capsule_lifecycle_policy",
        "capsule_liveness",
        "preservation_set",
        "cleanup_plan",
        "cleanup_cutoff_state",
    }
    frozen_contract_components = {
        "resource_budget_policy",
        "resource_observation",
        "resource_gate",
        "capsule_binding_set",
        "legacy_capsule_compatibility",
    }
    source_domain_components = {
        "controller_source_identity_policy",
        "controller_source_identity_receipt",
        "controller_python_environment_manifest",
        "controller_executable_dependency_manifest",
        "controller_startup_binding",
        "persistent_capsule_source_binding",
        "persistent_capsule_python_environment_manifest",
        "persistent_capsule_executable_dependency_manifest",
        "bridge_surface_manifest",
        "source_domain_compatibility",
        "legacy_controller_alias_receipt",
        "freeze_assembly_plan",
    }
    identity_namespace = request.get("identity_namespace", "m336k5")
    profile_id = request.get("official_profile_id")
    expected = (
        base_expected - {"resource_budget"}
        if identity_namespace in {"m336k7", "m336k8"}
        else base_expected
    )
    if identity_namespace != "m336k5":
        expected |= {"identity_namespace"} | lifecycle_components
    if identity_namespace in {"m336k7", "m336k8"}:
        expected |= frozen_contract_components | {"candidate_pool"}
    if identity_namespace == "m336k8":
        expected |= source_domain_components
    if profile_id is not None:
        expected |= {"official_profile_id"}
    if set(request) != expected:
        raise M336K2ProtocolError("M336K5 component bundle request fields changed")
    if identity_namespace not in {"m336k5", "m336k6", "m336k7", "m336k8"}:
        raise M336K2ProtocolError("M336K5 component identity namespace is invalid")
    repository = Path(request["repository"]).resolve(strict=True)
    legacy = Path(request["legacy_bundle"]).resolve(strict=True)
    if (
        identity_namespace in {"m336k7", "m336k8"}
        and request["identity_mode"] == "OFFICIAL"
    ):
        verify_m336k7_unchanged_candidate_pool(Path(request["candidate_pool"]))
    output = Path(request["output"]).resolve(strict=False)
    if output.exists() or output.is_relative_to(repository):
        raise M336K2ProtocolError("M336K5 component bundle output is stale or public")
    output.mkdir(parents=True)
    sources = {
        path.stem: path
        for path in legacy.glob("*.json")
        if path.name != "bundle_receipt.json"
    }
    if "candidate_pool" not in sources or "final_authorization" not in sources:
        raise M336K2ProtocolError("M336K5 legacy component closure is incomplete")
    for name, source in sources.items():
        shutil.copyfile(source, output / f"{name}.json")
    for name in (
        "python_environment_manifest",
        "python_startup_policy",
        "python_startup_bootstrap",
        "windows_python_launcher",
        "karina_python_launcher",
        "sanitized_environment_policy",
        "startup_receipt_schema",
        *(
            ("resource_budget",)
            if identity_namespace not in {"m336k7", "m336k8"}
            else ()
        ),
        "storage_reservation",
        "resource_monitor",
        "cleanup_policy",
        "recovery_checkpoint_policy",
        *(("candidate_pool",) if identity_namespace in {"m336k7", "m336k8"} else ()),
        *sorted(lifecycle_components if identity_namespace != "m336k5" else ()),
        *sorted(
            frozen_contract_components
            if identity_namespace in {"m336k7", "m336k8"}
            else ()
        ),
        *sorted(source_domain_components if identity_namespace == "m336k8" else ()),
    ):
        shutil.copyfile(
            Path(request[name]).resolve(strict=True), output / f"{name}.json"
        )
    replacements = {
        "@IMPLEMENTATION_TIP@": request["exact_implementation_tip"],
        "@Q_SHA@": request["exact_q30_sha"],
        "@BRANCH_REF@": request["branch_ref"],
        "@READINESS_HASH@": request["readiness_hash"],
    }
    for path in output.glob("*.json"):
        value = _rehash_top_level(_replace(_object(path), replacements))
        path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")
    if identity_namespace in {"m336k7", "m336k8"}:
        _write_m336k7_legacy_bindings(output, request)
        _write_m336k7_persistent_capsule_route(output)
        if request["identity_mode"] == "OFFICIAL":
            verify_m336k7_unchanged_candidate_pool(output / "candidate_pool.json")
    if identity_namespace == "m336k8":
        shutil.copyfile(
            Path(request["controller_python_environment_manifest"]).resolve(
                strict=True
            ),
            output / "python_environment_manifest.json",
        )
        shutil.copyfile(
            Path(request["controller_executable_dependency_manifest"]).resolve(
                strict=True
            ),
            output / "executable_dependency_manifest.json",
        )
    for name, source in (
        ("q28_readiness", request["q_readiness"]),
        ("q28_evidence_manifest", request["q_evidence_manifest"]),
    ):
        value = _rehash_top_level(_object(Path(source)))
        (output / f"{name}.json").write_text(
            canonical_json(value) + "\n", encoding="utf-8", newline="\n"
        )
    profile_registry = m336k_official_profile_registry()
    profile = profile_registry.profile(profile_id) if profile_id is not None else None
    registry = build_m336k5_route_registry(
        repository, identity_namespace, profile_id=profile_id
    )
    schemas = build_m336k5_schema_registry(identity_namespace, profile_id=profile_id)
    route = build_m336k5_route_manifest(registry, schemas)
    legacy_acquisition = _object(output / "acquisition_policy.json")
    selector = _object(output / "selector_policy.json")
    selector.pop("policy_hash", None)
    threshold = _object(output / "threshold_manifest.json")
    mode = request["identity_mode"]
    label = request["disposable_label"]
    if profile is not None:
        expected_profile_status = {
            "OFFICIAL": M336KOfficialRouteProfileStatus.CURRENT_ACTIVE,
            "DISPOSABLE": M336KOfficialRouteProfileStatus.REHEARSAL_ONLY,
        }.get(mode)
        if profile.profile_status is not expected_profile_status:
            raise M336K2ProtocolError("M336K9 component profile purpose changed")
        acquisition_id = profile.acquisition_run_id
        selector_id = profile.selector_run_id
        evaluator_id = profile.evaluator_run_id
    elif mode == "OFFICIAL":
        acquisition_id = f"{identity_namespace}.final-java.global-acquisition.v1"
        selector_id = f"{identity_namespace}.final-java.selector.v1"
        evaluator_id = f"{identity_namespace}.final-java.evaluator.v1"
    elif mode == "DISPOSABLE" and isinstance(label, str) and _LABEL.fullmatch(label):
        acquisition_id = f"{identity_namespace}.disposable.{label}.acquisition.v1"
        selector_id = f"{identity_namespace}.disposable.{label}.selector.v1"
        evaluator_id = f"{identity_namespace}.disposable.{label}.evaluator.v1"
    else:
        raise M336K2ProtocolError("M336K5 component identity mode is invalid")
    selector.update(
        {
            "contract_role": "M336K5_COUNT_NEUTRAL_SELECTOR_POLICY",
            "selector_run_id": selector_id,
        }
    )
    selector = {**selector, "policy_hash": content_hash(selector)}
    legacy_authorization = _object(output / "final_authorization.json")
    official_components = None
    if profile_id == M336K10_PROFILE_ID and mode == "OFFICIAL":
        pool_path = output / "candidate_pool.json"
        maven_source, scm_source = read_provider_sources(repository)
        official_components = build_official_acquisition_components(
            pool=_object(pool_path),
            pool_bytes=pool_path.read_bytes(),
            profile=profile,
            archive_policy_hash=_object(output / "archive_policy.json")["policy_hash"],
            candidate_terminal_policy_hash=_object(
                output / "candidate_terminal_policy.json"
            )["policy_hash"],
            global_continuation_policy_hash=_object(
                output / "global_continuation_policy.json"
            )["policy_hash"],
            authority_statement_hash=legacy_authorization["authority_statement_hash"],
            disclosure_registry_manifest_hash=bytes_hash(
                (output / "disclosure_registry_manifest.json").read_bytes()
            ),
            selector_policy=selector,
            selector_policy_hash=selector["policy_hash"],
            maven_provider_source=maven_source,
            scm_provider_source=scm_source,
        )
        acquisition = official_components["acquisition_policy"].canonical_object()
    else:
        acquisition = build_rehearsal_acquisition_components(
            acquisition_policy=legacy_acquisition,
            acquisition_run_id=acquisition_id,
        )
    evaluator_body = {
        "schema_version": 1,
        "contract_role": "M336K5_INDEPENDENT_EVALUATOR_POLICY",
        "evaluator_run_id": evaluator_id,
        "threshold_manifest_hash": threshold["threshold_manifest_hash"],
        "reservation_limit": 1,
        "retry_limit": 0,
        "goldens_after_reservation": True,
        "production_evaluator_reads": 0,
    }
    evaluator = {**evaluator_body, "policy_hash": content_hash(evaluator_body)}
    if profile is not None:
        bundle = build_m336k_identity_bundle_for_profile(
            profile_id=profile.profile_id,
            route_registry_hash=registry.registry_hash,
            route_manifest_hash=route.manifest_hash,
            acquisition_policy_hash=acquisition["acquisition_policy_hash"],
            selector_policy_hash=selector["policy_hash"],
            evaluator_policy_hash=evaluator["policy_hash"],
        )
    elif mode == "OFFICIAL":
        official_builders = {
            "m336k5": build_m336k5_official_identity_bundle,
            "m336k6": build_m336k6_official_identity_bundle,
            "m336k7": build_m336k7_official_identity_bundle,
            "m336k8": build_m336k8_official_identity_bundle,
        }
        official_builder = official_builders[identity_namespace]
        bundle = official_builder(
            route_registry_hash=registry.registry_hash,
            route_manifest_hash=route.manifest_hash,
            acquisition_policy_hash=acquisition["acquisition_policy_hash"],
            selector_policy_hash=selector["policy_hash"],
            evaluator_policy_hash=evaluator["policy_hash"],
        )
    else:
        bundle = M336K5RouteIdentityBundle.build(
            route_version=registry.route_version,
            protocol_run_id=M336K5ProtocolRunId(
                f"{identity_namespace}.disposable.{label}.v1"
            ),
            acquisition_run_id=M336K5AcquisitionRunId(acquisition_id),
            selector_run_id=M336K5SelectorRunId(selector_id),
            evaluator_run_id=M336K5EvaluatorRunId(evaluator_id),
            execution_mode=M336K5ExecutionMode("FINAL"),
            route_registry_hash=registry.registry_hash,
            route_manifest_hash=route.manifest_hash,
            acquisition_policy_hash=acquisition["acquisition_policy_hash"],
            selector_policy_hash=selector["policy_hash"],
            evaluator_policy_hash=evaluator["policy_hash"],
        )
    candidate_pool_hash = _object(output / "candidate_pool.json")["pool_hash"]
    if (
        identity_namespace in {"m336k7", "m336k8"}
        and not (profile_id is not None and mode == "OFFICIAL")
        and legacy_authorization["candidate_pool_hash"] != candidate_pool_hash
    ):
        raise M336K2ProtocolError("M336K7 candidate-pool authorization changed")
    python_environment = _object(output / "python_environment_manifest.json")
    startup_policy = _object(output / "python_startup_policy.json")
    bootstrap = _object(output / "python_startup_bootstrap.json")
    windows_launcher = _object(output / "windows_python_launcher.json")
    karina_launcher = _object(output / "karina_python_launcher.json")
    sanitized = _object(output / "sanitized_environment_policy.json")
    startup_schema = _object(output / "startup_receipt_schema.json")
    resource_budget = _object(
        output
        / (
            "resource_budget_policy.json"
            if identity_namespace in {"m336k7", "m336k8"}
            else "resource_budget.json"
        )
    )
    reservation = _object(output / "storage_reservation.json")
    resource_monitor = _object(output / "resource_monitor.json")
    cleanup = _object(output / "cleanup_policy.json")
    recovery = _object(output / "recovery_checkpoint_policy.json")
    authorization_builder = (
        build_m336k10_final_authorization
        if official_components is not None
        else build_m336k9_final_authorization
        if profile is not None
        else build_m336k5_final_authorization
    )
    common_authorization_values = dict(
        bundle=bundle,
        **({"official_profile_id": profile.profile_id} if profile is not None else {}),
        exact_implementation_tip=request["exact_implementation_tip"],
        exact_q30_sha=request["exact_q30_sha"],
        branch_ref=request["branch_ref"],
        archive_policy_hash=legacy_authorization["archive_policy_hash"],
        candidate_terminal_policy_hash=legacy_authorization[
            "candidate_terminal_policy_hash"
        ],
        global_continuation_policy_hash=legacy_authorization[
            "global_continuation_policy_hash"
        ],
        route_manifest_hash=route.manifest_hash,
        route_registry_hash=registry.registry_hash,
        schema_registry_hash=schemas.registry_hash,
        readiness_hash=request["readiness_hash"],
        executable_dependency_manifest_hash=(
            _object(output / "executable_dependency_manifest.json")["manifest_hash"]
            if identity_namespace == "m336k8"
            else legacy_authorization["executable_dependency_manifest_hash"]
        ),
        python_environment_manifest_hash=python_environment[
            "environment_manifest_hash"
        ],
        python_startup_policy_hash=startup_policy["policy_hash"],
        bootstrap_source_hash=bootstrap["source_bytes_hash"],
        windows_launcher_source_hash=windows_launcher["source_bytes_hash"],
        karina_launcher_hash=karina_launcher["launcher_hash"],
        sanitized_environment_hash=sanitized["receipt_hash"],
        startup_receipt_schema_hash=startup_schema["schema_hash"],
        resource_budget_hash=resource_budget[
            "policy_hash"
            if identity_namespace in {"m336k7", "m336k8"}
            else "receipt_hash"
        ],
        storage_reservation_receipt_hash=reservation["receipt_hash"],
        resource_monitor_hash=resource_monitor["source_bytes_hash"],
        cleanup_policy_hash=cleanup["source_bytes_hash"],
        recovery_policy_hash=recovery["source_bytes_hash"],
        authority_statement_hash=legacy_authorization["authority_statement_hash"],
        disclosure_registry_manifest_hash=legacy_authorization[
            "disclosure_registry_manifest_hash"
        ],
        selector_policy_hash=selector["policy_hash"],
        evaluator_policy_hash=evaluator["policy_hash"],
        minimum_candidate_families=legacy_authorization["minimum_candidate_families"],
        minimum_organizations=legacy_authorization["minimum_organizations"],
        maximum_candidates_per_organization=legacy_authorization[
            "maximum_candidates_per_organization"
        ],
        acquisition_reservation_limit=1,
        selector_reservation_limit=1,
        evaluator_reservation_limit=1,
        candidate_retry_limit=0,
        candidate_replacement_limit=0,
        pre_freeze_source_body_bytes=0,
    )
    if official_components is not None:
        authorization = authorization_builder(
            pool_binding=official_components["pool_binding"],
            network_authority=official_components["network_authority"],
            acquisition_policy=official_components["acquisition_policy"],
            provider_configuration=official_components["provider_configuration"],
            acquisition_binding_receipt_hash=official_components[
                "authorization_binding_hash"
            ],
            **common_authorization_values,
        )
    else:
        authorization = authorization_builder(
            candidate_pool_hash=candidate_pool_hash,
            acquisition_policy_hash=acquisition["acquisition_policy_hash"],
            allowed_network_hosts=tuple(legacy_authorization["allowed_network_hosts"]),
            **common_authorization_values,
        )
    if identity_namespace == "m336k8":
        builder = {
            **M336K8_FINAL_REQUEST_CONTRACT,
            "builder_hash": M336K8_FINAL_REQUEST_BUILDER_HASH,
        }
    elif identity_namespace == "m336k7":
        builder = {
            **M336K7_FINAL_REQUEST_CONTRACT,
            "builder_hash": M336K7_FINAL_REQUEST_BUILDER_HASH,
        }
    else:
        builder = {
            **M336K5_FINAL_REQUEST_CONTRACT,
            "builder_hash": M336K5_FINAL_REQUEST_BUILDER_HASH,
        }
    values = {
        "acquisition_policy": acquisition,
        "selector_policy": selector,
        "evaluator_policy": evaluator,
        "typed_route_registry": registry.canonical_object(),
        "typed_schema_registry": schemas.canonical_object(),
        "typed_route_manifest": route.canonical_object(),
        "route_identity_bundle": bundle.canonical_object(),
        "final_authorization": authorization.canonical_object(),
        "canonical_request_builder_identity": builder,
    }
    binding_receipt = None
    if official_components is not None:
        post_authorization = build_m336k10_post_authorization_components(
            pool_binding=official_components["pool_binding"],
            network_authority=official_components["network_authority"],
            policy=official_components["acquisition_policy"],
            profile=profile,
            provider=official_components["provider_configuration"],
            authorization=authorization,
            route_identity_bundle_hash=bundle.bundle_hash,
            authorization_binding_hash=official_components[
                "authorization_binding_hash"
            ],
        )
        binding_receipt = verify_m336k10_official_acquisition_binding(
            pool=_object(output / "candidate_pool.json"),
            pool_bytes=(output / "candidate_pool.json").read_bytes(),
            pool_binding=official_components["pool_binding"],
            network_authority=official_components["network_authority"],
            policy=official_components["acquisition_policy"],
            profile=profile,
            shared_policy=official_components["shared_policy"],
            provider=official_components["provider_configuration"],
            authorization=authorization,
            ledger_context=post_authorization["ledger_context"],
            stage_binding=post_authorization["stage_binding"],
            authority_statement_bytes=(
                repository
                / "artifacts/acquisition/m336i_freeze_v8/authority_statement.txt"
            ).read_bytes(),
            disclosure_registry_manifest_bytes=(
                output / "disclosure_registry_manifest.json"
            ).read_bytes(),
            maven_provider_source=maven_source,
            scm_provider_source=scm_source,
            expected_receipt=post_authorization["receipt"],
        )
        values.update(
            {
                "official_candidate_pool_binding": official_components[
                    "pool_binding"
                ].canonical_object(),
                "official_network_authority_manifest": official_components[
                    "network_authority"
                ].canonical_object(),
                "shared_acquisition_policy_binding": official_components[
                    "shared_policy"
                ].canonical_object(),
                "official_provider_configuration": official_components[
                    "provider_configuration"
                ].canonical_object(),
                "acquisition_ledger_context_template": post_authorization[
                    "ledger_context"
                ].canonical_object(),
                "stage_request_acquisition_binding": post_authorization[
                    "stage_binding"
                ].canonical_object(),
                "official_acquisition_binding_receipt": (
                    binding_receipt.canonical_object()
                ),
            }
        )
    if profile is not None:
        coverage = run_m336k_official_profile_coverage_gate()
        values.update(
            {
                "official_profile_registry": profile_registry.canonical_object(),
                "active_official_profile": profile.canonical_object(),
                "profile_coverage_gate": coverage.canonical_object(),
                "controller_admission_contract": {
                    **M336K9_CONTROLLER_ADMISSION_CONTRACT,
                    "contract_hash": M336K9_CONTROLLER_ADMISSION_CONTRACT_HASH,
                },
            }
        )
    for name, value in values.items():
        (output / f"{name}.json").write_text(
            canonical_json(value) + "\n", encoding="utf-8", newline="\n"
        )
    if identity_namespace == "m336k8":
        execution_capsule = _object(output / "execution_capsule_receipt.json")
        binding = _object(output / "capsule_binding_set.json")
        execution_capsule["karina_public_execution_capsule_receipt_hash"] = binding[
            "legacy_public_capsule_receipt_hash"
        ]
        execution_capsule["karina_executable_dependency_manifest_hash"] = binding[
            "executable_dependency_manifest_hash"
        ]
        _write_rehashed(output / "execution_capsule_receipt.json", execution_capsule)
        _write_m336k8_post_freeze_and_gate(
            repository,
            output,
            authorization,
            bundle,
            official_acquisition_binding_receipt_hash=(
                None if binding_receipt is None else binding_receipt.receipt_hash
            ),
        )
    if identity_namespace == "m336k7":
        execution_capsule = _object(output / "execution_capsule_receipt.json")
        binding = _object(output / "capsule_binding_set.json")
        execution_capsule["karina_public_execution_capsule_receipt_hash"] = binding[
            "legacy_public_capsule_receipt_hash"
        ]
        execution_capsule["karina_executable_dependency_manifest_hash"] = binding[
            "executable_dependency_manifest_hash"
        ]
        execution_capsule = _rehash_top_level(execution_capsule)
        (output / "execution_capsule_receipt.json").write_text(
            canonical_json(execution_capsule) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        post_freeze = M336K7PostFreezeInputBundle.build(
            freeze_manifest_contract_hash=M336K7_FREEZE_MANIFEST_CONTRACT_HASH,
            final_authorization_hash=authorization.authorization_hash,
            route_identity_bundle_hash=bundle.bundle_hash,
            route_registry_hash=registry.registry_hash,
            route_manifest_hash=route.manifest_hash,
            legacy_capsule_route_registry_hash=_object(output / "route_registry.json")[
                "registry_hash"
            ],
            legacy_capsule_route_manifest_hash=_object(output / "route_manifest.json")[
                "manifest_hash"
            ],
            resource_budget_policy_hash=resource_budget["policy_hash"],
            resource_observation_hash=_object(output / "resource_observation.json")[
                "observation_hash"
            ],
            storage_reservation_receipt_hash=reservation["receipt_hash"],
            resource_gate_receipt_hash=_object(output / "resource_gate.json")[
                "receipt_hash"
            ],
            capsule_binding_set_hash=binding["binding_set_hash"],
            legacy_compatibility_receipt_hash=_object(
                output / "legacy_capsule_compatibility.json"
            )["receipt_hash"],
            liveness_receipt_hash=_object(output / "capsule_liveness.json")[
                "receipt_hash"
            ],
            startup_policy_hash=startup_policy["policy_hash"],
            executable_dependency_manifest_hash=_object(
                output / "executable_dependency_manifest.json"
            )["manifest_hash"],
            windows_jdk_identity_hash=_object(output / "windows_jdk_identity.json")[
                "receipt_hash"
            ],
            karina_jdk_identity_hash=_object(output / "karina_jdk_identity.json")[
                "receipt_hash"
            ],
            karina_host_identity_hash=_object(
                output / "karina_stable_host_identity.json"
            )["receipt_hash"],
            candidate_pool_hash=_object(output / "candidate_pool.json")["pool_hash"],
            acquisition_policy_hash=acquisition["acquisition_policy_hash"],
            archive_policy_hash=_object(output / "archive_policy.json")["policy_hash"],
            terminal_policy_hash=_object(output / "candidate_terminal_policy.json")[
                "policy_hash"
            ],
            selector_policy_hash=selector["policy_hash"],
            evaluator_policy_hash=evaluator["policy_hash"],
            threshold_manifest_hash=_object(output / "threshold_manifest.json")[
                "threshold_manifest_hash"
            ],
            publication_contract_hash=content_hash(
                (
                    _object(output / "h28_publication_contract.json")["contract_hash"],
                    _object(output / "e28_publication_contract.json")["contract_hash"],
                )
            ),
        )
        (output / "post_freeze_input_bundle.json").write_text(
            canonical_json(post_freeze.canonical_object()) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        compatibility_inputs = {
            "freeze_manifest_contract": {
                **M336K7_FREEZE_MANIFEST_CONTRACT,
                "contract_hash": M336K7_FREEZE_MANIFEST_CONTRACT_HASH,
            },
            "post_freeze_input_bundle": post_freeze.canonical_object(),
            **{
                name: _object(output / f"{name}.json")
                for name in (
                    "final_authorization",
                    "route_identity_bundle",
                    "typed_route_registry",
                    "typed_route_manifest",
                    "route_registry",
                    "route_manifest",
                    "resource_budget_policy",
                    "resource_observation",
                    "storage_reservation",
                    "resource_gate",
                    "capsule_binding_set",
                    "legacy_capsule_compatibility",
                    "capsule_liveness",
                    "capsule_content_manifest",
                    "python_startup_policy",
                    "executable_dependency_manifest",
                    "windows_jdk_identity",
                    "karina_jdk_identity",
                    "karina_stable_host_identity",
                    "candidate_pool",
                    "acquisition_policy",
                    "archive_policy",
                    "candidate_terminal_policy",
                    "selector_policy",
                    "evaluator_policy",
                    "threshold_manifest",
                    "h28_publication_contract",
                    "e28_publication_contract",
                )
            },
        }
        artifacts = {
            name: (
                value,
                _current_consumer(
                    name,
                    value,
                    hash_field=_artifact_hash_field(name),
                    all_inputs=compatibility_inputs,
                    expected_post_freeze=post_freeze,
                ),
            )
            for name, value in compatibility_inputs.items()
        }
        compatibility_gate = M336K7FrozenContractCompatibilityGate.run(
            artifacts,
            current_route_sources=(
                repository
                / "src"
                / "ai_brain"
                / "stage3"
                / "acquisition"
                / "m336k7_request.py",
            ),
        )
        (output / "frozen_contract_compatibility.json").write_text(
            canonical_json(compatibility_gate.canonical_object()) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if official_components is not None:
        _write_m336k10_freeze_origin_receipt(output)
    pool = _object(output / "candidate_pool.json")
    body = {
        "schema_version": 1,
        "contract_role": {
            "m336k5": "PUBLIC_SAFE_M336K5_COMPONENT_BUNDLE_RECEIPT",
            "m336k6": "PUBLIC_SAFE_M336K6_COMPONENT_BUNDLE_RECEIPT",
            "m336k7": "PUBLIC_SAFE_M336K7_COMPONENT_BUNDLE_RECEIPT",
            "m336k8": "PUBLIC_SAFE_M336K8_COMPONENT_BUNDLE_RECEIPT",
        }[identity_namespace]
        if profile is None
        else "PUBLIC_SAFE_M336K9_COMPONENT_BUNDLE_RECEIPT",
        "component_count": len(tuple(output.glob("*.json"))),
        "candidate_pool_hash": pool["pool_hash"],
        "route_registry_hash": registry.registry_hash,
        "route_manifest_hash": route.manifest_hash,
        "schema_registry_hash": schemas.registry_hash,
        "route_identity_bundle_hash": bundle.bundle_hash,
        "final_authorization_hash": authorization.authorization_hash,
        "canonical_request_builder_hash": (
            M336K8_FINAL_REQUEST_BUILDER_HASH
            if identity_namespace == "m336k8"
            else M336K7_FINAL_REQUEST_BUILDER_HASH
            if identity_namespace == "m336k7"
            else M336K5_FINAL_REQUEST_BUILDER_HASH
        ),
        "status": "PASS",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    (output / "bundle_receipt.json").write_text(
        canonical_json(receipt) + "\n", encoding="utf-8", newline="\n"
    )
    print(canonical_json(receipt))


def _write_m336k10_freeze_origin_receipt(output: Path) -> None:
    official = {
        "acquisition_ledger_context_template",
        "acquisition_policy",
        "active_official_profile",
        "candidate_pool",
        "canonical_request_builder_identity",
        "controller_admission_contract",
        "evaluator_policy",
        "final_authorization",
        "official_acquisition_binding_receipt",
        "official_candidate_pool_binding",
        "official_network_authority_manifest",
        "official_profile_registry",
        "official_provider_configuration",
        "post_freeze_input_bundle",
        "profile_coverage_gate",
        "route_identity_bundle",
        "selector_policy",
        "stage_request_acquisition_binding",
        "typed_route_manifest",
        "typed_route_registry",
        "typed_schema_registry",
    }
    shared = {
        "archive_policy",
        "candidate_terminal_policy",
        "disclosure_registry_manifest",
        "e28_publication_contract",
        "global_continuation_policy",
        "h28_publication_contract",
        "resource_budget_policy",
        "shared_acquisition_policy_binding",
        "threshold_manifest",
    }
    paths = tuple(
        sorted(
            (
                path
                for path in output.glob("*.json")
                if path.stem not in {"bundle_receipt", "official_freeze_origin_receipt"}
            ),
            key=lambda path: path.stem,
        )
    )
    entries = []
    official_bytes = bytearray()
    for path in paths:
        if path.stem in official:
            scope = M336K10_EXECUTION_SCOPE_OFFICIAL
            official_bytes.extend(path.read_bytes())
        elif path.stem in shared:
            scope = M336K10_EXECUTION_SCOPE_SHARED
        else:
            scope = M336K10_EXECUTION_SCOPE_HISTORICAL
        entry = M336K10FreezeOriginEntry(
            component_name=path.stem,
            execution_scope=scope,
            producer_role=f"{path.stem.upper()}_PRODUCER",
            source_artifact_hash=bytes_hash(path.read_bytes()),
            consumer_roles=("F35_FREEZE", "POST_FREEZE_VALIDATOR"),
            status="PASS",
        )
        entry.verify()
        entries.append(entry)
    fixture_count = official_bytes.count(b"fixture.invalid")
    wrong_pool_count = official_bytes.count(
        b"b4128991cdaa118ddac58bb3e87f060028b5794374e75b2b68dca1a8f59cd40e"
    )
    body = {
        "schema_version": 1,
        "contract_role": M336K10FreezeOriginReceipt.ROLE,
        "entries": tuple(entries),
        "component_count": len(entries),
        "rehearsal_scope_component_count": 0,
        "fixture_host_occurrence_count": fixture_count,
        "wrong_pool_occurrence_count": wrong_pool_count,
        "unclassified_component_count": 0,
        "status": "PASS" if fixture_count == wrong_pool_count == 0 else "FAIL",
    }
    receipt = M336K10FreezeOriginReceipt(**body, receipt_hash=content_hash(body))
    receipt.verify()
    (output / "official_freeze_origin_receipt.json").write_text(
        canonical_json(receipt.canonical_object()) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_m336k8_post_freeze_and_gate(
    repository: Path,
    output: Path,
    authorization: M336K5FinalAuthorization,
    bundle: M336K5RouteIdentityBundle,
    *,
    official_acquisition_binding_receipt_hash: str | None = None,
) -> None:
    plan = M336K8FreezeAssemblyPlan.from_dict(
        _object(output / "freeze_assembly_plan.json")
    )
    if plan != M336K8FreezeAssemblyPlan.build():
        raise M336K2ProtocolError("M336K8 freeze assembly plan changed")
    policy = M336K8ProjectSourceIdentityPolicy.from_dict(
        _object(output / "controller_source_identity_policy.json")
    )
    source_identity = M336K8ProjectSourceIdentityReceipt.from_dict(
        _object(output / "controller_source_identity_receipt.json")
    )
    controller_environment = _object(
        output / "controller_python_environment_manifest.json"
    )
    controller_dependencies = _object(
        output / "controller_executable_dependency_manifest.json"
    )
    controller_startup = M336K8ControllerStartupBinding.from_dict(
        _object(output / "controller_startup_binding.json")
    )
    capsule_binding = M336K7PersistentCapsuleBindingSet.from_dict(
        _object(output / "capsule_binding_set.json")
    )
    capsule_source = M336K8PersistentCapsuleSourceBinding.from_dict(
        _object(output / "persistent_capsule_source_binding.json")
    )
    capsule_environment = _object(
        output / "persistent_capsule_python_environment_manifest.json"
    )
    capsule_dependencies = _object(
        output / "persistent_capsule_executable_dependency_manifest.json"
    )
    bridge = M336K8BridgeSurfaceManifest.from_dict(
        _object(output / "bridge_surface_manifest.json")
    )
    source_compatibility = M336K8SourceDomainCompatibilityReceipt.from_dict(
        _object(output / "source_domain_compatibility.json")
    )
    legacy_alias = M336K8LegacyControllerAliasReceipt.from_dict(
        _object(output / "legacy_controller_alias_receipt.json")
    )
    resource_policy = M336K7ResourceBudgetPolicy.from_dict(
        _object(output / "resource_budget_policy.json")
    )
    resource_observation = M336K7ResourceObservationReceipt.from_dict(
        _object(output / "resource_observation.json")
    )
    reservation = storage_reservation_from_dict(
        _object(output / "storage_reservation.json")
    )
    resource_gate = M336K7ResourceGateReceipt.from_dict(
        _object(output / "resource_gate.json")
    )
    legacy_capsule = M336K7LegacyCapsuleCompatibilityReceipt.from_dict(
        _object(output / "legacy_capsule_compatibility.json")
    )
    liveness = _object(output / "capsule_liveness.json")
    post_values = {
        "controller_project_source_identity_policy_hash": policy.policy_hash,
        "controller_project_source_identity_receipt_hash": source_identity.receipt_hash,
        "controller_python_environment_manifest_hash": controller_environment[
            "environment_manifest_hash"
        ],
        "controller_executable_dependency_manifest_hash": controller_dependencies[
            "manifest_hash"
        ],
        "controller_startup_binding_hash": controller_startup.binding_hash,
        "persistent_capsule_binding_set_hash": capsule_binding.binding_set_hash,
        "persistent_capsule_source_binding_hash": capsule_source.binding_hash,
        "persistent_capsule_python_environment_manifest_hash": capsule_environment[
            "identity_hash"
        ],
        "persistent_capsule_executable_dependency_manifest_hash": capsule_dependencies[
            "manifest_hash"
        ],
        "bridge_surface_manifest_hash": bridge.manifest_hash,
        "source_domain_compatibility_receipt_hash": source_compatibility.receipt_hash,
        "freeze_assembly_plan_hash": plan.plan_hash,
        "legacy_controller_alias_receipt_hash": legacy_alias.receipt_hash,
        "startup_policy_hash": _object(output / "python_startup_policy.json")[
            "policy_hash"
        ],
        "resource_budget_policy_hash": resource_policy.policy_hash,
        "resource_observation_hash": resource_observation.observation_hash,
        "storage_reservation_receipt_hash": reservation.receipt_hash,
        "resource_gate_receipt_hash": resource_gate.receipt_hash,
        "capsule_liveness_receipt_hash": liveness["receipt_hash"],
        "capsule_content_manifest_hash": _object(
            output / "capsule_content_manifest.json"
        )["manifest_hash"],
        "capsule_lifecycle_policy_hash": _object(
            output / "capsule_lifecycle_policy.json"
        )["policy_hash"],
        "route_identity_bundle_hash": bundle.bundle_hash,
        "route_registry_hash": _object(output / "typed_route_registry.json")[
            "registry_hash"
        ],
        "route_manifest_hash": _object(output / "typed_route_manifest.json")[
            "manifest_hash"
        ],
        "final_authorization_hash": authorization.authorization_hash,
        "candidate_pool_hash": _object(output / "candidate_pool.json")["pool_hash"],
        "acquisition_policy_hash": _object(output / "acquisition_policy.json")[
            "acquisition_policy_hash"
        ],
        "archive_policy_hash": _object(output / "archive_policy.json")["policy_hash"],
        "terminal_policy_hash": _object(output / "candidate_terminal_policy.json")[
            "policy_hash"
        ],
        "selector_policy_hash": _object(output / "selector_policy.json")["policy_hash"],
        "evaluator_policy_hash": _object(output / "evaluator_policy.json")[
            "policy_hash"
        ],
        "threshold_manifest_hash": _object(output / "threshold_manifest.json")[
            "threshold_manifest_hash"
        ],
        "publication_contract_hash": content_hash(
            (
                _object(output / "h28_publication_contract.json")["contract_hash"],
                _object(output / "e28_publication_contract.json")["contract_hash"],
            )
        ),
    }
    post_type = (
        M336K10PostFreezeInputBundle
        if official_acquisition_binding_receipt_hash is not None
        else M336K8PostFreezeInputBundleV2
    )
    if official_acquisition_binding_receipt_hash is not None:
        post_values.update(
            {
                "official_candidate_pool_binding_hash": _object(
                    output / "official_candidate_pool_binding.json"
                )["binding_hash"],
                "official_network_authority_manifest_hash": _object(
                    output / "official_network_authority_manifest.json"
                )["manifest_hash"],
                "official_acquisition_policy_hash": _object(
                    output / "acquisition_policy.json"
                )["acquisition_policy_hash"],
                "official_acquisition_binding_receipt_hash": (
                    official_acquisition_binding_receipt_hash
                ),
                "official_provider_configuration_hash": _object(
                    output / "official_provider_configuration.json"
                )["configuration_hash"],
                "stage_request_acquisition_binding_hash": _object(
                    output / "stage_request_acquisition_binding.json"
                )["binding_hash"],
                "acquisition_ledger_context_template_hash": _object(
                    output / "acquisition_ledger_context_template.json"
                )["template_hash"],
            }
        )
    provisional = post_type.build(**post_values, freeze_assembly_receipt_hash="0" * 64)
    values = {
        "controller_python_environment_manifest": controller_environment,
        "controller_executable_dependency_manifest": controller_dependencies,
        "controller_source_identity_policy": policy.canonical_object(),
        "controller_source_identity_receipt": source_identity.canonical_object(),
        "controller_startup_binding": controller_startup.canonical_object(),
        "persistent_capsule_python_environment_manifest": capsule_environment,
        "persistent_capsule_executable_dependency_manifest": capsule_dependencies,
        "persistent_capsule_source_binding": capsule_source.canonical_object(),
        "bridge_surface_manifest": bridge.canonical_object(),
        "source_domain_compatibility": source_compatibility.canonical_object(),
        "resource_budget_policy": resource_policy.canonical_object(),
        "resource_observation": resource_observation.canonical_object(),
        "storage_reservation": _object(output / "storage_reservation.json"),
        "resource_gate": resource_gate.canonical_object(),
        "capsule_binding_set": capsule_binding.canonical_object(),
        "legacy_capsule_compatibility": legacy_capsule.canonical_object(),
        "capsule_liveness": liveness,
        "legacy_controller_alias_receipt": legacy_alias.canonical_object(),
        "route_identity_bundle": bundle.canonical_object(),
        "final_authorization": authorization.canonical_object(),
        "post_freeze_input_bundle": provisional.canonical_object(),
    }
    origins = {item.component_name: item.source_domain for item in plan.entries}
    assembly = M336K8FreezeInputAssembler.assemble(
        plan=plan,
        component_values=values,
        component_origins=origins,
        semantic_verifier=m336k8_semantic_binding_mismatches,
    )
    post = post_type.build(
        **post_values, freeze_assembly_receipt_hash=assembly.receipt_hash
    )
    values["post_freeze_input_bundle"] = post.canonical_object()
    repeated = M336K8FreezeInputAssembler.assemble(
        plan=plan,
        component_values=values,
        component_origins=origins,
        semantic_verifier=m336k8_semantic_binding_mismatches,
    )
    if repeated != assembly or assembly.status != "PASS":
        raise M336K2ProtocolError("M336K8 assembly is not fixed-point stable")
    (output / "post_freeze_input_bundle.json").write_text(
        canonical_json(post.canonical_object()) + "\n", encoding="utf-8", newline="\n"
    )
    (output / "freeze_assembly_receipt.json").write_text(
        canonical_json(assembly.canonical_object()) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    artifacts = _m336k8_compatibility_artifacts(
        values, assembly_plan=plan, assembly_receipt=assembly
    )
    gate = M336K8FrozenContractCompatibilityGateV2.run(
        plan=plan,
        artifacts=artifacts,
        semantic_verifier=m336k8_semantic_binding_mismatches,
        current_route_sources=(
            repository
            / "src"
            / "ai_brain"
            / "stage3"
            / "acquisition"
            / "m336k8_request.py",
        ),
    )
    (output / "frozen_contract_compatibility_v2.json").write_text(
        canonical_json(gate.canonical_object()) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _object(path: Path) -> dict:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise M336K2ProtocolError("M336K5 component input is not an object")
    return value


def _replace(value, replacements: dict[str, str]):
    if isinstance(value, dict):
        return {key: _replace(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace(item, replacements) for item in value]
    if isinstance(value, str):
        for old, new in replacements.items():
            value = value.replace(old, new)
    return value


def _rehash_top_level(value: dict) -> dict:
    primary = tuple(
        name
        for name in (
            "authorization_hash",
            "receipt_hash",
            "manifest_hash",
            "registry_hash",
            "policy_hash",
            "contract_hash",
            "threshold_manifest_hash",
            "frozen_file_manifest_hash",
        )
        if name in value
    )
    if len(primary) > 1:
        raise M336K2ProtocolError("M336K5 component hash is ambiguous")
    if primary:
        field = primary[0]
        body = dict(value)
        body.pop(field)
        return {**body, field: content_hash(body)}
    return value


def _artifact_hash_field(name: str) -> str:
    return {
        "freeze_manifest_contract": "contract_hash",
        "post_freeze_input_bundle": "bundle_hash",
        "final_authorization": "authorization_hash",
        "route_identity_bundle": "bundle_hash",
        "typed_route_registry": "registry_hash",
        "typed_route_manifest": "manifest_hash",
        "route_registry": "registry_hash",
        "route_manifest": "manifest_hash",
        "resource_budget_policy": "policy_hash",
        "resource_observation": "observation_hash",
        "storage_reservation": "receipt_hash",
        "resource_gate": "receipt_hash",
        "capsule_binding_set": "binding_set_hash",
        "legacy_capsule_compatibility": "receipt_hash",
        "capsule_liveness": "receipt_hash",
        "capsule_content_manifest": "manifest_hash",
        "python_startup_policy": "policy_hash",
        "executable_dependency_manifest": "manifest_hash",
        "windows_jdk_identity": "receipt_hash",
        "karina_jdk_identity": "receipt_hash",
        "karina_stable_host_identity": "receipt_hash",
        "candidate_pool": "pool_hash",
        "acquisition_policy": "acquisition_policy_hash",
        "archive_policy": "policy_hash",
        "candidate_terminal_policy": "policy_hash",
        "selector_policy": "policy_hash",
        "evaluator_policy": "policy_hash",
        "threshold_manifest": "threshold_manifest_hash",
        "h28_publication_contract": "contract_hash",
        "e28_publication_contract": "contract_hash",
    }[name]


def _write_m336k7_legacy_bindings(output: Path, request: dict) -> None:
    """Retarget unchanged native publication consumers to the current chain."""

    implementation = _object(output / "implementation_tip.json")
    implementation["exact_implementation_tip"] = request["exact_implementation_tip"]
    _write_rehashed(output / "implementation_tip.json", implementation)

    q_commit = _object(output / "q28_commit.json")
    q_commit["exact_q28_sha"] = request["exact_q30_sha"]
    _write_rehashed(output / "q28_commit.json", q_commit)

    namespace = request["identity_namespace"]
    if request.get("official_profile_id") == M336K10_PROFILE_ID:
        publication_values = {
            "branch_ref": request["branch_ref"],
            "q_root": "artifacts/m336k10/q35",
            "f_root": "artifacts/m336k10/f35-freeze",
            "h_root": "artifacts/m336k10/h35",
            "e_root": "artifacts/m336k10/e35",
            "q_subject": "M-33.6k.10 qualify official acquisition authority",
            "f_subject": "M-33.6k.10 freeze final Java execution",
            "h_subject": "M-33.6k.10 publish sealed Java production",
            "e_subject": "M-33.6k.10 publish independent Java evidence",
        }
    elif request.get("official_profile_id") is not None:
        names = (
            "branch_ref",
            "q_root",
            "f_root",
            "h_root",
            "e_root",
            "q_subject",
            "f_subject",
            "h_subject",
            "e_subject",
        )
        h_contract = _object(output / "h28_publication_contract.json")
        e_contract = _object(output / "e28_publication_contract.json")
        publication_values = {name: h_contract[name] for name in names}
        publication_tuple = tuple(
            publication_values[name]
            for name in (
                "q_root",
                "f_root",
                "h_root",
                "e_root",
                "q_subject",
                "f_subject",
                "h_subject",
                "e_subject",
            )
        )
        allowed_publication_tuples = {
            (
                "artifacts/m336k9/q34",
                "artifacts/m336k9/f34-freeze",
                "artifacts/m336k9/h34",
                "artifacts/m336k9/e34",
                "M-33.6k.9 qualify disposable admission route",
                "M-33.6k.9 freeze disposable admission route",
                "M-33.6k.9 publish disposable sealed production",
                "M-33.6k.9 publish disposable independent evidence",
            ),
            (
                "artifacts/m336k9/q34",
                "artifacts/m336k9/f34-freeze",
                "artifacts/m336k9/h34",
                "artifacts/m336k9/e34",
                "M-33.6k.9 qualify official controller admission",
                "M-33.6k.9 freeze final Java execution",
                "M-33.6k.9 publish sealed Java production",
                "M-33.6k.9 publish independent Java evidence",
            ),
            (
                "artifacts/m336k10/disposable/q35-like",
                "artifacts/m336k10/disposable/f35-like-freeze",
                "artifacts/m336k10/disposable/h35-like",
                "artifacts/m336k10/disposable/e35-like",
                "M-33.6k.10 qualify disposable acquisition route",
                "M-33.6k.10 freeze disposable acquisition route",
                "M-33.6k.10 publish disposable sealed production",
                "M-33.6k.10 publish disposable independent evidence",
            ),
        }
        if (
            any(e_contract[name] != value for name, value in publication_values.items())
            or publication_values["branch_ref"] != request["branch_ref"]
            or publication_tuple not in allowed_publication_tuples
        ):
            raise M336K2ProtocolError("M336K9 publication contract changed")
    elif namespace == "m336k8":
        publication_values = {
            "branch_ref": request["branch_ref"],
            "q_root": "artifacts/m336k8/q33",
            "f_root": "artifacts/m336k8/f33-freeze",
            "h_root": "artifacts/m336k8/h33",
            "e_root": "artifacts/m336k8/e33",
            "q_subject": "M-33.6k.8 qualify exact source-domain freeze inputs",
            "f_subject": "M-33.6k.8 freeze final Java execution",
            "h_subject": "M-33.6k.8 publish sealed Java production",
            "e_subject": "M-33.6k.8 publish independent Java evidence",
        }
    else:
        publication_values = {
            "branch_ref": request["branch_ref"],
            "q_root": "artifacts/m336k7/q32",
            "f_root": "artifacts/m336k7/f32-freeze",
            "h_root": "artifacts/m336k7/h32",
            "e_root": "artifacts/m336k7/e32",
            "q_subject": "M-33.6k.7 qualify exact committed freeze inputs",
            "f_subject": "M-33.6k.7 freeze final Java execution",
            "h_subject": "M-33.6k.7 publish sealed Java production",
            "e_subject": "M-33.6k.7 publish independent Java evidence",
        }
    for name in ("h28_publication_contract", "e28_publication_contract"):
        value = _object(output / f"{name}.json")
        value.update(publication_values)
        _write_rehashed(output / f"{name}.json", value)

    protocol = _object(output / "commit_protocol.json")
    protocol.update(
        {
            name: value
            for name, value in publication_values.items()
            if name == "branch_ref" or name.endswith("_subject")
        }
    )
    _write_rehashed(output / "commit_protocol.json", protocol)


def _write_m336k7_persistent_capsule_route(output: Path) -> None:
    """Freeze the legacy remote route against preserved capsule source bytes."""

    content = _object(output / "capsule_content_manifest.json")
    registry = build_m336k7_persistent_capsule_route_registry(content)
    route = build_m336k7_persistent_capsule_route_manifest(
        _object(output / "route_manifest.json"), registry
    )
    (output / "route_registry.json").write_text(
        canonical_json(registry) + "\n", encoding="utf-8", newline="\n"
    )
    (output / "route_manifest.json").write_text(
        canonical_json(route) + "\n", encoding="utf-8", newline="\n"
    )


def _write_rehashed(path: Path, value: dict) -> None:
    path.write_text(
        canonical_json(_rehash_top_level(value)) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _strict_consumer(value: dict, *, hash_field: str):
    expected_fields = frozenset(value)
    semantic_role = value.get("contract_role")

    def consume(candidate: dict):
        return M336K7StrictArtifact.consume(
            candidate,
            expected_fields=expected_fields,
            semantic_role=semantic_role,
            hash_field=hash_field,
        )

    return consume


def _current_consumer(
    name: str,
    value: dict,
    *,
    hash_field: str,
    all_inputs: dict[str, dict],
    expected_post_freeze: M336K7PostFreezeInputBundle,
):
    typed = {
        "final_authorization": lambda candidate: _consume_authorization(
            candidate, all_inputs
        ),
        "route_identity_bundle": M336K5RouteIdentityBundle.from_dict,
        "route_registry": lambda candidate: _consume_capsule_route_registry(
            candidate, all_inputs
        ),
        "route_manifest": lambda candidate: _consume_capsule_route_manifest(
            candidate, all_inputs
        ),
        "resource_budget_policy": M336K7ResourceBudgetPolicy.from_dict,
        "resource_observation": M336K7ResourceObservationReceipt.from_dict,
        "storage_reservation": _consume_storage_reservation,
        "resource_gate": lambda candidate: _consume_resource_gate(
            candidate, all_inputs
        ),
        "capsule_binding_set": M336K7PersistentCapsuleBindingSet.from_dict,
        "capsule_content_manifest": M336K6CapsuleContentManifest.from_dict,
        "legacy_capsule_compatibility": lambda candidate: _consume_compatibility(
            candidate, all_inputs
        ),
        "post_freeze_input_bundle": lambda candidate: _consume_post_freeze(
            candidate, expected_post_freeze
        ),
        "python_startup_policy": M336K5PythonStartupPolicy.from_dict,
    }
    consumer = typed.get(name)
    if consumer is not None:
        return consumer
    return _strict_consumer(value, hash_field=hash_field)


def _consume_capsule_route_registry(value: dict, all_inputs: dict):
    registry, _route = verify_m336k7_persistent_capsule_route_binding(
        content_value=all_inputs["capsule_content_manifest"],
        registry_value=value,
        route_value=all_inputs["route_manifest"],
    )
    return M336K7StrictArtifact(asdict(registry))


def _consume_capsule_route_manifest(value: dict, all_inputs: dict):
    _registry, route = verify_m336k7_persistent_capsule_route_binding(
        content_value=all_inputs["capsule_content_manifest"],
        registry_value=all_inputs["route_registry"],
        route_value=value,
    )
    return M336K7StrictArtifact(asdict(route))


def _consume_storage_reservation(value: dict) -> M336K7StrictArtifact:
    storage_reservation_from_dict(value)
    return M336K7StrictArtifact(dict(value))


def _consume_authorization(
    value: dict, all_inputs: dict[str, dict]
) -> M336K5FinalAuthorization:
    authorization = m336k_current_final_authorization_from_dict(value)
    authorization.verify(
        M336K5RouteIdentityBundle.from_dict(all_inputs["route_identity_bundle"])
    )
    return authorization


def _consume_resource_gate(
    value: dict, all_inputs: dict[str, dict]
) -> M336K7ResourceGateReceipt:
    gate = M336K7ResourceGateReceipt.from_dict(value)
    verify_m336k7_resource_gate_binding(
        M336K7ResourceBudgetPolicy.from_dict(all_inputs["resource_budget_policy"]),
        M336K7ResourceObservationReceipt.from_dict(all_inputs["resource_observation"]),
        storage_reservation_from_dict(all_inputs["storage_reservation"]),
        gate,
    )
    return gate


def _consume_compatibility(
    value: dict, all_inputs: dict[str, dict]
) -> M336K7LegacyCapsuleCompatibilityReceipt:
    compatibility = M336K7LegacyCapsuleCompatibilityReceipt.from_dict(value)
    verify_m336k7_capsule_compatibility_binding(
        M336K7PersistentCapsuleBindingSet.from_dict(all_inputs["capsule_binding_set"]),
        compatibility,
    )
    return compatibility


def _consume_post_freeze(
    value: dict, expected: M336K7PostFreezeInputBundle
) -> M336K7PostFreezeInputBundle:
    consumed = M336K7PostFreezeInputBundle.from_dict(value)
    if consumed != expected:
        raise M336K2ProtocolError("M336K7 post-freeze bundle cross-binding changed")
    return consumed


if __name__ == "__main__":
    main()
