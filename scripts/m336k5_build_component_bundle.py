"""Overlay typed M-33.6k.5 identities onto a freshly built native bundle."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_execution import (
    M336K2_REQUIRED_EXECUTABLE_ROLES,
)
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
from ai_brain.stage3.acquisition.m336k5_startup import (
    M336K5PythonInvocationPlan,
    M336K5PythonStartupPolicy,
    M336K5PythonStartupReceipt,
)
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
    build_m336k11_final_authorization,
    build_m336k12_final_authorization,
    build_m336k13_final_authorization,
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
from ai_brain.stage3.acquisition.m336k11_execution import (
    M336K11_PROFILE_ID,
    M336K11EffectiveEnvironmentBinding,
    M336K11HermeticExecutableDependencyManifest,
    M336K11NativeExecutionCapsuleReceipt,
    M336K11NativeRouteManifest,
    M336K11OfficialControllerExecutableBinding,
    M336K11PostFreezeInputBundle,
    build_m336k11_final_request_binding,
    m336k11_official_component_scopes,
    verify_m336k11_live_execution_inputs,
    verify_m336k11_official_executable_binding,
)
from ai_brain.stage3.acquisition.m336k12_dispatch import (
    M336K12_PROFILE_ID,
    M336K12NativeExecutionCapsuleReceipt,
    M336K12NativeRouteManifest,
    M336K12NativeStageDispatch,
    M336K12NativeStagePlanBinding,
    M336K12OfficialControllerExecutableBinding,
    M336K12OfficialExecutableBindingReceipt,
    M336K12PostFreezeInputBundle,
    M336K12ProducerConsumerParityReceipt,
    build_m336k12_native_execution_plan,
    build_m336k12_native_stage_dispatches,
    m336k12_native_dispatch_contract_hash,
    verify_m336k12_freeze_plan_admission,
    verify_m336k12_native_stage_plan,
)
from ai_brain.stage3.acquisition.m336k13_plan import (
    M336K13_PROFILE_ID,
    M336K13ActualLauncherPlanReceiptSchema,
    M336K13EffectiveEnvironmentBinding,
    M336K13FinalControllerInvocationPlanV2,
    M336K13FinalControllerPlanBindingReceipt,
    M336K13FinalControllerPlanLifecyclePolicy,
    M336K13FinalControllerPlanPathRoleManifest,
    M336K13FinalControllerPlanTemplate,
    M336K13NativeExecutionCapsuleReceipt,
    M336K13NativeRouteManifest,
    M336K13NativeStagePlanBinding,
    M336K13OfficialControllerExecutableBinding,
    M336K13OfficialExecutableBindingReceipt,
    M336K13PostFreezeInputBundle,
    verify_m336k13_final_controller_plan_binding,
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
    if profile_id in {
        M336K11_PROFILE_ID,
        M336K12_PROFILE_ID,
        M336K13_PROFILE_ID,
    }:
        source_domain_components |= {"effective_environment_binding"}
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
    if profile_id in {
        M336K11_PROFILE_ID,
        M336K12_PROFILE_ID,
        M336K13_PROFILE_ID,
    }:
        expected |= {
            "executable_handles",
            "windows_invocation_plan",
            "windows_startup_receipt",
        }
    if profile_id == M336K13_PROFILE_ID:
        expected |= {
            "final_controller_plan_template",
            "final_controller_plan_lifecycle_receipt",
            "final_controller_plan_binding_receipt",
        }
    if set(request) != expected:
        raise M336K2ProtocolError("M336K5 component bundle request fields changed")
    if identity_namespace not in {"m336k5", "m336k6", "m336k7", "m336k8"}:
        raise M336K2ProtocolError("M336K5 component identity namespace is invalid")
    repository = Path(request["repository"]).resolve(strict=True)
    legacy = Path(request["legacy_bundle"]).resolve(strict=True)
    final_plan_template = None
    final_plan_lifecycle = None
    final_plan_binding = None
    if profile_id == M336K13_PROFILE_ID:
        final_plan_template = M336K13FinalControllerPlanTemplate.from_dict(
            _object(Path(request["final_controller_plan_template"]))
        )
        final_plan_lifecycle = M336K13FinalControllerInvocationPlanV2.from_dict(
            _object(Path(request["final_controller_plan_lifecycle_receipt"]))
        )
        final_plan_binding = M336K13FinalControllerPlanBindingReceipt.from_dict(
            _object(Path(request["final_controller_plan_binding_receipt"]))
        )
        if (
            final_plan_lifecycle.exact_implementation_tip
            != request["exact_implementation_tip"]
            or final_plan_lifecycle.exact_qualification_sha != request["exact_q30_sha"]
        ):
            raise M336K2ProtocolError("M336K13 exact plan lineage changed")
        verify_m336k13_final_controller_plan_binding(
            plan_path=Path(request["windows_invocation_plan"]),
            template=final_plan_template,
            lifecycle=final_plan_lifecycle,
            binding=final_plan_binding,
        )
        if (
            final_plan_template.execution_scope != "OFFICIAL_CONTROLLER"
            or final_plan_lifecycle.execution_scope != "OFFICIAL_CONTROLLER"
            or final_plan_binding.execution_scope != "OFFICIAL_CONTROLLER"
        ):
            raise M336K2ProtocolError("M336K13 official component plan scope changed")
    elif profile_id == M336K12_PROFILE_ID:
        verify_m336k12_freeze_plan_admission(
            plan=M336K5PythonInvocationPlan.from_dict(
                _object(Path(request["windows_invocation_plan"]))
            ),
            exact_implementation_tip=request["exact_implementation_tip"],
            exact_qualification_sha=request["exact_q30_sha"],
        )
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
    denied_legacy_executable_names = (
        {
            "controller_executable_dependency_manifest",
            "executable_dependency_manifest",
            "controller_python_environment_manifest",
            "python_environment_manifest",
            "controller_startup_binding",
            "execution_capsule_receipt",
            "route_manifest",
            "route_registry",
            "typed_route_manifest",
            "typed_route_registry",
            "effective_environment_binding",
            "official_executable_binding_receipt",
            "official_controller_executable_binding",
            "native_route_manifest",
            "native_stage_dispatches",
            "native_stage_plan_binding",
            "producer_consumer_parity_receipt",
        }
        if profile_id in {M336K11_PROFILE_ID, M336K12_PROFILE_ID, M336K13_PROFILE_ID}
        else set()
    )
    for name, source in sources.items():
        if name in denied_legacy_executable_names:
            continue
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
    if profile_id == M336K13_PROFILE_ID:
        public_plan_components = {
            "final_controller_plan_template": final_plan_template.canonical_object(),
            "final_controller_plan_binding_receipt": (
                final_plan_binding.canonical_object()
            ),
            "actual_launcher_plan_receipt_schema": (
                M336K13ActualLauncherPlanReceiptSchema.build().canonical_object()
            ),
            "final_controller_plan_lifecycle_policy": (
                M336K13FinalControllerPlanLifecyclePolicy.build().canonical_object()
            ),
            "final_controller_plan_path_role_manifest": (
                M336K13FinalControllerPlanPathRoleManifest.build(
                    template=final_plan_template,
                    lifecycle=final_plan_lifecycle,
                    binding=final_plan_binding,
                ).canonical_object()
            ),
        }
        for name, value in public_plan_components.items():
            (output / f"{name}.json").write_text(
                canonical_json(value) + "\n", encoding="utf-8", newline="\n"
            )
    if identity_namespace in {"m336k7", "m336k8"}:
        _write_m336k7_legacy_bindings(output, request)
        if profile_id not in {
            M336K11_PROFILE_ID,
            M336K12_PROFILE_ID,
            M336K13_PROFILE_ID,
        }:
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
    if (
        profile_id
        in {
            M336K10_PROFILE_ID,
            M336K11_PROFILE_ID,
            M336K12_PROFILE_ID,
            M336K13_PROFILE_ID,
        }
        and mode == "OFFICIAL"
    ):
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
    executable_binding = None
    native_capsule = None
    native_route = None
    plan_binding = None
    producer_consumer_parity = None
    native_stage_dispatches = None
    if profile_id in {
        M336K11_PROFILE_ID,
        M336K12_PROFILE_ID,
        M336K13_PROFILE_ID,
    }:
        dependency = M336K11HermeticExecutableDependencyManifest.from_dict(
            _object(output / "controller_executable_dependency_manifest.json")
        )
        effective_value = _object(output / "effective_environment_binding.json")
        if profile_id == M336K13_PROFILE_ID:
            effective_environment = (
                M336K13EffectiveEnvironmentBinding.from_dict(effective_value)
                if effective_value.get("contract_role")
                == M336K13EffectiveEnvironmentBinding.ROLE
                else M336K13EffectiveEnvironmentBinding.build(
                    M336K11EffectiveEnvironmentBinding.from_dict(effective_value),
                    final_plan_binding.receipt_hash,
                )
            )
            if (
                effective_environment.final_controller_plan_binding_receipt_hash
                != final_plan_binding.receipt_hash
            ):
                raise M336K2ProtocolError(
                    "M336K13 effective environment plan binding changed"
                )
            (output / "effective_environment_binding.json").write_text(
                canonical_json(effective_environment.canonical_object()) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        else:
            effective_environment = M336K11EffectiveEnvironmentBinding.from_dict(
                effective_value
            )
        base_capsule = M336K11NativeExecutionCapsuleReceipt.build(
            repository=repository,
            route_registry_hash=registry.registry_hash,
            typed_route_manifest_hash=route.manifest_hash,
            dependency_manifest=dependency,
            effective_environment=effective_environment,
        )
        source_identity = _object(output / "controller_source_identity_receipt.json")
        base_profile = (
            profile_registry.profile(M336K11_PROFILE_ID)
            if profile_id in {M336K12_PROFILE_ID, M336K13_PROFILE_ID}
            else profile
        )
        base_binding = M336K11OfficialControllerExecutableBinding.build(
            profile=base_profile,
            source_identity_receipt_hash=source_identity["receipt_hash"],
            source_identity_hash=source_identity["live_project_source_identity"],
            environment_manifest_hash=python_environment["environment_manifest_hash"],
            manifest=dependency,
            effective_environment=effective_environment,
            route_registry_hash=registry.registry_hash,
            typed_route_manifest_hash=route.manifest_hash,
            native_stage_worker_source_hash=base_capsule.stage_worker_bytes_hash,
            native_command_contract_hash=base_capsule.command_contract_hash,
        )
        if profile_id in {M336K12_PROFILE_ID, M336K13_PROFILE_ID}:
            native_stage_dispatches = build_m336k12_native_stage_dispatches(
                repository=repository,
                execution_scope="OFFICIAL_CONTROLLER",
                bootstrap_script=repository / "scripts/m336k5_python_bootstrap.py",
            )
            private_plan = build_m336k12_native_execution_plan(
                repository=repository,
                python_executable=Path(request["executable_handles"]["python"]),
                stage_request=output / "private-stage-request.json",
                stage_receipt_root=output / "private-stage-receipts",
                route_run_id=profile.protocol_run_id,
                exact_f37_sha=request["exact_implementation_tip"],
                route_registry_hash=registry.registry_hash,
                dispatches=native_stage_dispatches,
            )
            base_plan_binding = M336K12NativeStagePlanBinding.build(
                repository=repository,
                exact_implementation_tip=request["exact_implementation_tip"],
                active_profile_hash=profile.profile_hash,
                route_registry_hash=registry.registry_hash,
                typed_route_manifest_hash=route.manifest_hash,
                dispatches=native_stage_dispatches,
                python_executable=Path(request["executable_handles"]["python"]),
                outer_startup_policy_hash=dependency.static_startup_policy_hash,
                native_capsule_receipt_hash=base_capsule.receipt_hash,
            )
            plan_binding = (
                M336K13NativeStagePlanBinding.build(
                    base_plan_binding,
                    final_plan_binding.receipt_hash,
                )
                if profile_id == M336K13_PROFILE_ID
                else base_plan_binding
            )
            producer_consumer_parity = verify_m336k12_native_stage_plan(
                plan=private_plan,
                dispatches=native_stage_dispatches,
                plan_binding=plan_binding,
                repository=repository,
                python_executable=Path(request["executable_handles"]["python"]),
            )
            base_native_capsule = M336K12NativeExecutionCapsuleReceipt.build(
                base_capsule=base_capsule,
                plan_binding=plan_binding,
                parity=producer_consumer_parity,
                dispatches=native_stage_dispatches,
            )
            native_capsule = (
                M336K13NativeExecutionCapsuleReceipt.build(
                    base_native_capsule,
                    final_plan_binding.receipt_hash,
                )
                if profile_id == M336K13_PROFILE_ID
                else base_native_capsule
            )
            base_dispatch_profile = (
                profile_registry.profile(M336K12_PROFILE_ID)
                if profile_id == M336K13_PROFILE_ID
                else profile
            )
            base_executable_binding = (
                M336K12OfficialControllerExecutableBinding.build(
                    base_binding=base_binding,
                    profile=base_dispatch_profile,
                    capsule=base_native_capsule,
                    plan_binding=plan_binding,
                    parity=producer_consumer_parity,
                )
                if profile_id == M336K13_PROFILE_ID
                else None
            )
            executable_binding = (
                M336K13OfficialControllerExecutableBinding.build(
                    base_binding=base_executable_binding,
                    profile=profile,
                    capsule=native_capsule,
                    plan_binding=plan_binding,
                    parity=producer_consumer_parity,
                    final_controller_plan_binding_receipt_hash=(
                        final_plan_binding.receipt_hash
                    ),
                )
                if profile_id == M336K13_PROFILE_ID
                else M336K12OfficialControllerExecutableBinding.build(
                    base_binding=base_binding,
                    profile=profile,
                    capsule=native_capsule,
                    plan_binding=plan_binding,
                    parity=producer_consumer_parity,
                )
            )
            native_route = (
                M336K13NativeRouteManifest.build(
                    profile=profile,
                    binding=executable_binding,
                    capsule=native_capsule,
                    plan_binding=plan_binding,
                    parity=producer_consumer_parity,
                    final_controller_plan_binding_receipt_hash=(
                        final_plan_binding.receipt_hash
                    ),
                )
                if profile_id == M336K13_PROFILE_ID
                else M336K12NativeRouteManifest.build(
                    profile=profile,
                    binding=executable_binding,
                    capsule=native_capsule,
                    plan_binding=plan_binding,
                    parity=producer_consumer_parity,
                )
            )
        else:
            native_capsule = base_capsule
            executable_binding = base_binding
            native_route = M336K11NativeRouteManifest.build(
                profile=profile,
                binding=executable_binding,
                capsule=native_capsule,
            )
        manifest_bytes = (
            output / "controller_executable_dependency_manifest.json"
        ).read_bytes()
        (output / "executable_dependency_manifest.json").write_bytes(manifest_bytes)
        (output / "execution_capsule_receipt.json").write_text(
            canonical_json(native_capsule.canonical_object()) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        route_bytes = (canonical_json(native_route.canonical_object()) + "\n").encode(
            "utf-8"
        )
        (output / "native_route_manifest.json").write_bytes(route_bytes)
        (output / "route_manifest.json").write_bytes(route_bytes)
        registry_bytes = (canonical_json(registry.canonical_object()) + "\n").encode(
            "utf-8"
        )
        (output / "route_registry.json").write_bytes(registry_bytes)
        (output / "official_controller_executable_binding.json").write_text(
            canonical_json(executable_binding.canonical_object()) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    authorization_builder = (
        build_m336k13_final_authorization
        if profile_id == M336K13_PROFILE_ID
        else build_m336k12_final_authorization
        if profile_id == M336K12_PROFILE_ID
        else build_m336k11_final_authorization
        if profile_id == M336K11_PROFILE_ID
        else build_m336k10_final_authorization
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
        official_authorization_values = dict(
            pool_binding=official_components["pool_binding"],
            network_authority=official_components["network_authority"],
            acquisition_policy=official_components["acquisition_policy"],
            provider_configuration=official_components["provider_configuration"],
            acquisition_binding_receipt_hash=official_components[
                "authorization_binding_hash"
            ],
            **common_authorization_values,
        )
        if executable_binding is not None:
            official_authorization_values[
                "official_controller_executable_binding_hash"
            ] = executable_binding.binding_hash
        if profile_id in {M336K12_PROFILE_ID, M336K13_PROFILE_ID}:
            official_authorization_values.update(
                {
                    "native_stage_plan_binding_hash": (plan_binding.plan_binding_hash),
                    "producer_consumer_parity_receipt_hash": (
                        producer_consumer_parity.receipt_hash
                    ),
                    "native_execution_capsule_receipt_hash": (
                        native_capsule.receipt_hash
                    ),
                }
            )
        if profile_id == M336K13_PROFILE_ID:
            official_authorization_values[
                "final_controller_plan_binding_receipt_hash"
            ] = final_plan_binding.receipt_hash
        authorization = authorization_builder(**official_authorization_values)
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
    if (
        executable_binding is not None
        and native_capsule is not None
        and native_route is not None
    ):
        values.update(
            {
                "official_controller_executable_binding": (
                    executable_binding.canonical_object()
                ),
                "effective_environment_binding": _object(
                    output / "effective_environment_binding.json"
                ),
                "execution_capsule_receipt": native_capsule.canonical_object(),
                "native_route_manifest": native_route.canonical_object(),
            }
        )
        if profile_id in {M336K12_PROFILE_ID, M336K13_PROFILE_ID}:
            dispatch_contract_hash = m336k12_native_dispatch_contract_hash(
                native_stage_dispatches
            )
            dispatch_body = {
                "schema_version": 1,
                "contract_role": "M336K12_NATIVE_STAGE_DISPATCH_SET",
                "dispatches": tuple(
                    item.canonical_object() for item in native_stage_dispatches
                ),
                "dispatch_count": len(native_stage_dispatches),
                "dispatch_contract_hash": dispatch_contract_hash,
            }
            values.update(
                {
                    "native_stage_dispatches": {
                        **dispatch_body,
                        "receipt_hash": content_hash(dispatch_body),
                    },
                    "native_stage_plan_binding": plan_binding.canonical_object(),
                    "producer_consumer_parity_receipt": (
                        producer_consumer_parity.canonical_object()
                    ),
                }
            )
    if profile_id == M336K13_PROFILE_ID:
        values.update(public_plan_components)
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
    if identity_namespace == "m336k8" and profile_id not in {
        M336K11_PROFILE_ID,
        M336K12_PROFILE_ID,
        M336K13_PROFILE_ID,
    }:
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
    elif identity_namespace == "m336k8":
        executable_handles = request["executable_handles"]
        if (
            type(executable_handles) is not dict
            or set(executable_handles) != M336K2_REQUIRED_EXECUTABLE_ROLES
        ):
            raise M336K2ProtocolError("M336K11 executable handle roles changed")
        invocation_plan = M336K5PythonInvocationPlan.from_dict(
            _object(Path(request["windows_invocation_plan"]))
        )
        startup_receipt = M336K5PythonStartupReceipt.from_dict(
            _object(Path(request["windows_startup_receipt"]))
        )
        resolved_executable_handles = {
            name: Path(path).resolve(strict=True)
            for name, path in executable_handles.items()
        }
        if profile_id == M336K12_PROFILE_ID:
            _write_m336k12_executable_binding_receipt(
                repository=repository,
                output=output,
                invocation_plan=invocation_plan,
                startup_receipt=startup_receipt,
                executable_handles=resolved_executable_handles,
            )
        if profile_id == M336K13_PROFILE_ID:
            _write_m336k13_executable_binding_receipt(
                repository=repository,
                output=output,
                invocation_plan_path=Path(request["windows_invocation_plan"]),
                lifecycle_path=Path(request["final_controller_plan_lifecycle_receipt"]),
                startup_receipt=startup_receipt,
                executable_handles=resolved_executable_handles,
            )
        _write_m336k8_post_freeze_and_gate(
            repository,
            output,
            authorization,
            bundle,
            official_acquisition_binding_receipt_hash=(
                None if binding_receipt is None else binding_receipt.receipt_hash
            ),
        )
        if profile_id == M336K11_PROFILE_ID:
            _write_m336k11_executable_binding_receipt(
                repository=repository,
                output=output,
                invocation_plan=invocation_plan,
                startup_receipt=startup_receipt,
                executable_handles=resolved_executable_handles,
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
        "official_controller_executable_binding",
        "official_executable_binding_receipt",
        "effective_environment_binding",
        "execution_capsule_receipt",
        "native_route_manifest",
        "controller_executable_dependency_manifest",
        "executable_dependency_manifest",
        "controller_python_environment_manifest",
        "python_environment_manifest",
        "controller_startup_binding",
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
            consumer_roles=(
                (
                    "F36_FREEZE"
                    if (output / "official_controller_executable_binding.json").exists()
                    else "F35_FREEZE"
                ),
                "POST_FREEZE_VALIDATOR",
            ),
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


def _write_m336k11_executable_binding_receipt(
    *,
    repository: Path,
    output: Path,
    invocation_plan: M336K5PythonInvocationPlan,
    startup_receipt: M336K5PythonStartupReceipt,
    executable_handles: dict[str, Path],
) -> None:
    binding = M336K11OfficialControllerExecutableBinding.from_dict(
        _object(output / "official_controller_executable_binding.json")
    )
    manifest = M336K11HermeticExecutableDependencyManifest.from_dict(
        _object(output / "controller_executable_dependency_manifest.json")
    )
    effective = M336K11EffectiveEnvironmentBinding.from_dict(
        _object(output / "effective_environment_binding.json")
    )
    capsule = M336K11NativeExecutionCapsuleReceipt.from_dict(
        _object(output / "execution_capsule_receipt.json")
    )
    route = M336K11NativeRouteManifest.from_dict(
        _object(output / "native_route_manifest.json")
    )
    builder = _object(output / "canonical_request_builder_identity.json")
    final_request_binding = build_m336k11_final_request_binding(
        official_controller_executable_binding_hash=binding.binding_hash,
        builder_identity_hash=builder["builder_hash"],
    )
    receipt = verify_m336k11_official_executable_binding(
        binding=binding,
        manifest=manifest,
        active_alias_bytes=(
            output / "executable_dependency_manifest.json"
        ).read_bytes(),
        canonical_manifest_bytes=(
            output / "controller_executable_dependency_manifest.json"
        ).read_bytes(),
        startup_policy=M336K5PythonStartupPolicy.from_dict(
            _object(output / "python_startup_policy.json")
        ),
        sanitized_environment_policy=_object(
            output / "sanitized_environment_policy.json"
        ),
        controller_environment_manifest=_object(
            output / "controller_python_environment_manifest.json"
        ),
        controller_source_identity=_object(
            output / "controller_source_identity_receipt.json"
        ),
        effective_environment=effective,
        controller_startup_binding=_object(output / "controller_startup_binding.json"),
        native_capsule=capsule,
        native_route=route,
        route_registry=_object(output / "typed_route_registry.json"),
        typed_route_manifest=_object(output / "typed_route_manifest.json"),
        final_authorization=_object(output / "final_authorization.json"),
        post_freeze_input_bundle=_object(output / "post_freeze_input_bundle.json"),
        final_request=final_request_binding,
        component_scopes=m336k11_official_component_scopes(),
        invocation_plan=invocation_plan,
        startup_receipt=startup_receipt,
        executable_handles=executable_handles,
        native_stage_worker_bytes=(
            repository / "scripts/m336k2_run_stage.py"
        ).read_bytes(),
        expected_target=repository / "scripts/m336k11_run_final_route.py",
    )
    (output / "official_executable_binding_receipt.json").write_text(
        canonical_json(receipt.canonical_object()) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_m336k12_executable_binding_receipt(
    *,
    repository: Path,
    output: Path,
    invocation_plan: M336K5PythonInvocationPlan,
    startup_receipt: M336K5PythonStartupReceipt,
    executable_handles: dict[str, Path],
) -> None:
    binding = M336K12OfficialControllerExecutableBinding.from_dict(
        _object(output / "official_controller_executable_binding.json")
    )
    manifest = M336K11HermeticExecutableDependencyManifest.from_dict(
        _object(output / "controller_executable_dependency_manifest.json")
    )
    effective = M336K11EffectiveEnvironmentBinding.from_dict(
        _object(output / "effective_environment_binding.json")
    )
    capsule = M336K12NativeExecutionCapsuleReceipt.from_dict(
        _object(output / "execution_capsule_receipt.json")
    )
    route = M336K12NativeRouteManifest.from_dict(
        _object(output / "native_route_manifest.json")
    )
    plan_binding = M336K12NativeStagePlanBinding.from_dict(
        _object(output / "native_stage_plan_binding.json")
    )
    parity = M336K12ProducerConsumerParityReceipt.from_dict(
        _object(output / "producer_consumer_parity_receipt.json")
    )
    dispatch_value = _object(output / "native_stage_dispatches.json")
    dispatches = tuple(
        M336K12NativeStageDispatch.from_dict(item)
        for item in dispatch_value["dispatches"]
    )
    dispatch_body = dict(dispatch_value)
    dispatch_receipt_hash = dispatch_body.pop("receipt_hash", None)
    if (
        dispatch_value.get("contract_role") != "M336K12_NATIVE_STAGE_DISPATCH_SET"
        or dispatch_value.get("dispatch_count") != len(dispatches)
        or dispatch_value.get("dispatch_contract_hash")
        != m336k12_native_dispatch_contract_hash(dispatches)
        or dispatch_receipt_hash != content_hash(dispatch_body)
    ):
        raise M336K2ProtocolError("M336K12 native dispatch set changed")
    verify_m336k11_live_execution_inputs(
        manifest=manifest,
        effective_environment=effective,
        invocation_plan=invocation_plan,
        startup_receipt=startup_receipt,
        executable_handles=executable_handles,
        native_stage_worker_bytes=(
            repository / "scripts/m336k2_run_stage.py"
        ).read_bytes(),
        native_capsule=capsule,
        expected_target=repository / "scripts/m336k12_run_final_route.py",
    )
    authorization = _object(output / "final_authorization.json")
    relations = (
        (binding.executable_dependency_manifest_hash, manifest.manifest_hash),
        (binding.effective_environment_binding_receipt_hash, effective.receipt_hash),
        (binding.native_execution_capsule_receipt_hash, capsule.receipt_hash),
        (route.native_execution_capsule_receipt_hash, capsule.receipt_hash),
        (
            authorization["official_controller_executable_binding_hash"],
            binding.binding_hash,
        ),
        (
            authorization["native_execution_capsule_receipt_hash"],
            capsule.receipt_hash,
        ),
        (
            authorization["native_stage_plan_binding_hash"],
            plan_binding.plan_binding_hash,
        ),
        (
            authorization["producer_consumer_parity_receipt_hash"],
            parity.receipt_hash,
        ),
    )
    executable_mismatches = sum(left != right for left, right in relations)
    semantic_anchor = content_hash(
        (
            manifest.manifest_hash,
            effective.receipt_hash,
            invocation_plan.invocation_plan_hash,
            startup_receipt.receipt_hash,
            binding.binding_hash,
            capsule.receipt_hash,
            route.manifest_hash,
            plan_binding.plan_binding_hash,
            parity.receipt_hash,
            dispatch_receipt_hash,
        )
    )
    receipt = M336K12OfficialExecutableBindingReceipt.build(
        executable_semantic_anchor_hash=semantic_anchor,
        executable_semantic_mismatch_count=executable_mismatches,
        binding=binding,
        capsule=capsule,
        route=route,
        plan_binding=plan_binding,
        parity=parity,
    )
    (output / "official_executable_binding_receipt.json").write_text(
        canonical_json(receipt.canonical_object()) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_m336k13_executable_binding_receipt(
    *,
    repository: Path,
    output: Path,
    invocation_plan_path: Path,
    lifecycle_path: Path,
    startup_receipt: M336K5PythonStartupReceipt,
    executable_handles: dict[str, Path],
) -> None:
    template = M336K13FinalControllerPlanTemplate.from_dict(
        _object(output / "final_controller_plan_template.json")
    )
    lifecycle = M336K13FinalControllerInvocationPlanV2.from_dict(
        _object(lifecycle_path)
    )
    final_plan_binding = M336K13FinalControllerPlanBindingReceipt.from_dict(
        _object(output / "final_controller_plan_binding_receipt.json")
    )
    invocation_plan = verify_m336k13_final_controller_plan_binding(
        plan_path=invocation_plan_path,
        template=template,
        lifecycle=lifecycle,
        binding=final_plan_binding,
    )
    binding = M336K13OfficialControllerExecutableBinding.from_dict(
        _object(output / "official_controller_executable_binding.json")
    )
    manifest = M336K11HermeticExecutableDependencyManifest.from_dict(
        _object(output / "controller_executable_dependency_manifest.json")
    )
    effective = M336K13EffectiveEnvironmentBinding.from_dict(
        _object(output / "effective_environment_binding.json")
    )
    capsule = M336K13NativeExecutionCapsuleReceipt.from_dict(
        _object(output / "execution_capsule_receipt.json")
    )
    route = M336K13NativeRouteManifest.from_dict(
        _object(output / "native_route_manifest.json")
    )
    plan_binding = M336K13NativeStagePlanBinding.from_dict(
        _object(output / "native_stage_plan_binding.json")
    )
    parity = M336K12ProducerConsumerParityReceipt.from_dict(
        _object(output / "producer_consumer_parity_receipt.json")
    )
    dispatch_value = _object(output / "native_stage_dispatches.json")
    dispatches = tuple(
        M336K12NativeStageDispatch.from_dict(item)
        for item in dispatch_value["dispatches"]
    )
    dispatch_body = dict(dispatch_value)
    dispatch_receipt_hash = dispatch_body.pop("receipt_hash", None)
    if (
        dispatch_value.get("contract_role") != "M336K12_NATIVE_STAGE_DISPATCH_SET"
        or dispatch_value.get("dispatch_count") != len(dispatches)
        or dispatch_value.get("dispatch_contract_hash")
        != m336k12_native_dispatch_contract_hash(dispatches)
        or dispatch_receipt_hash != content_hash(dispatch_body)
    ):
        raise M336K2ProtocolError("M336K13 native dispatch set changed")
    verify_m336k11_live_execution_inputs(
        manifest=manifest,
        effective_environment=effective,
        invocation_plan=invocation_plan,
        startup_receipt=startup_receipt,
        executable_handles=executable_handles,
        native_stage_worker_bytes=(
            repository / "scripts/m336k2_run_stage.py"
        ).read_bytes(),
        native_capsule=capsule,
        expected_target=repository / "scripts/m336k13_run_final_route.py",
        controller_bootstrap_source_hash=template.bootstrap_source_hash,
    )
    authorization = _object(output / "final_authorization.json")
    plan_hash = final_plan_binding.receipt_hash
    relations = (
        (binding.executable_dependency_manifest_hash, manifest.manifest_hash),
        (binding.effective_environment_binding_receipt_hash, effective.receipt_hash),
        (binding.native_execution_capsule_receipt_hash, capsule.receipt_hash),
        (route.native_execution_capsule_receipt_hash, capsule.receipt_hash),
        (
            authorization["official_controller_executable_binding_hash"],
            binding.binding_hash,
        ),
        (authorization["native_execution_capsule_receipt_hash"], capsule.receipt_hash),
        (
            authorization["native_stage_plan_binding_hash"],
            plan_binding.plan_binding_hash,
        ),
        (
            authorization["producer_consumer_parity_receipt_hash"],
            parity.receipt_hash,
        ),
        (authorization["final_controller_plan_binding_receipt_hash"], plan_hash),
        (effective.final_controller_plan_binding_receipt_hash, plan_hash),
        (binding.final_controller_plan_binding_receipt_hash, plan_hash),
        (capsule.final_controller_plan_binding_receipt_hash, plan_hash),
        (route.final_controller_plan_binding_receipt_hash, plan_hash),
        (plan_binding.final_controller_plan_binding_receipt_hash, plan_hash),
    )
    executable_mismatches = sum(left != right for left, right in relations)
    semantic_anchor = content_hash(
        (
            manifest.manifest_hash,
            effective.receipt_hash,
            invocation_plan.invocation_plan_hash,
            startup_receipt.receipt_hash,
            binding.binding_hash,
            capsule.receipt_hash,
            route.manifest_hash,
            plan_binding.plan_binding_hash,
            parity.receipt_hash,
            dispatch_receipt_hash,
            plan_hash,
        )
    )
    receipt = M336K13OfficialExecutableBindingReceipt.build(
        executable_semantic_anchor_hash=semantic_anchor,
        executable_semantic_mismatch_count=executable_mismatches,
        binding=binding,
        capsule=capsule,
        route=route,
        plan_binding=plan_binding,
        parity=parity,
        final_controller_plan_binding_receipt_hash=plan_hash,
    )
    (output / "official_executable_binding_receipt.json").write_text(
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
    active_final_plan_closure = plan.contract_role == M336K8FreezeAssemblyPlan.ROLE_V4
    active_native_dispatch_closure = plan.contract_role in {
        M336K8FreezeAssemblyPlan.ROLE_V3,
        M336K8FreezeAssemblyPlan.ROLE_V4,
    }
    active_executable_closure = plan.contract_role in {
        M336K8FreezeAssemblyPlan.ROLE_V2,
        M336K8FreezeAssemblyPlan.ROLE_V3,
        M336K8FreezeAssemblyPlan.ROLE_V4,
    }
    if plan != M336K8FreezeAssemblyPlan.build(
        active_executable_closure=active_executable_closure,
        native_stage_dispatch_closure=active_native_dispatch_closure,
        final_controller_plan_closure=active_final_plan_closure,
    ):
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
        M336K13PostFreezeInputBundle
        if active_final_plan_closure
        else M336K12PostFreezeInputBundle
        if active_native_dispatch_closure
        else M336K11PostFreezeInputBundle
        if active_executable_closure
        else M336K10PostFreezeInputBundle
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
    if active_executable_closure:
        executable_binding = _object(
            output / "official_controller_executable_binding.json"
        )
        effective_environment = _object(output / "effective_environment_binding.json")
        native_capsule = _object(output / "execution_capsule_receipt.json")
        native_route = _object(output / "native_route_manifest.json")
        post_values.update(
            {
                "official_controller_executable_binding_hash": executable_binding[
                    "binding_hash"
                ],
                "effective_environment_binding_receipt_hash": (
                    effective_environment["receipt_hash"]
                ),
                "native_execution_capsule_receipt_hash": native_capsule["receipt_hash"],
                "native_route_manifest_hash": native_route["manifest_hash"],
                "official_executable_binding_receipt_hash": (
                    _object(output / "official_executable_binding_receipt.json")[
                        "receipt_hash"
                    ]
                    if active_native_dispatch_closure
                    else executable_binding["binding_hash"]
                ),
            }
        )
    if active_native_dispatch_closure:
        plan_binding_value = _object(output / "native_stage_plan_binding.json")
        plan_binding = (
            M336K13NativeStagePlanBinding.from_dict(plan_binding_value)
            if active_final_plan_closure
            else M336K12NativeStagePlanBinding.from_dict(plan_binding_value)
        )
        parity = M336K12ProducerConsumerParityReceipt.from_dict(
            _object(output / "producer_consumer_parity_receipt.json")
        )
        dispatch_set = _object(output / "native_stage_dispatches.json")
        post_values.update(
            {
                "native_stage_plan_binding_hash": plan_binding.plan_binding_hash,
                "producer_consumer_parity_receipt_hash": parity.receipt_hash,
                "dispatch_contract_hash": dispatch_set["dispatch_contract_hash"],
            }
        )
    if active_final_plan_closure:
        post_values["final_controller_plan_binding_receipt_hash"] = _object(
            output / "final_controller_plan_binding_receipt.json"
        )["receipt_hash"]
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
    if active_executable_closure:
        values.update(
            {
                "executable_dependency_manifest": _object(
                    output / "executable_dependency_manifest.json"
                ),
                "effective_environment_binding": effective_environment,
                "official_controller_executable_binding": executable_binding,
                "execution_capsule_receipt": native_capsule,
                "native_route_manifest": native_route,
            }
        )
    if active_native_dispatch_closure:
        values.update(
            {
                "native_stage_dispatches": dispatch_set,
                "native_stage_plan_binding": plan_binding.canonical_object(),
                "producer_consumer_parity_receipt": parity.canonical_object(),
                "official_executable_binding_receipt": _object(
                    output / "official_executable_binding_receipt.json"
                ),
            }
        )
    if active_final_plan_closure:
        values.update(
            {
                name: _object(output / f"{name}.json")
                for name in (
                    "final_controller_plan_template",
                    "final_controller_plan_binding_receipt",
                    "actual_launcher_plan_receipt_schema",
                    "final_controller_plan_lifecycle_policy",
                    "final_controller_plan_path_role_manifest",
                )
            }
        )
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
    if request.get("official_profile_id") == M336K12_PROFILE_ID:
        publication_values = {
            "branch_ref": request["branch_ref"],
            "q_root": "artifacts/m336k12/q37",
            "f_root": "artifacts/m336k12/f37-freeze",
            "h_root": "artifacts/m336k12/h37",
            "e_root": "artifacts/m336k12/e37",
            "q_subject": "M-33.6k.12 qualify native stage dispatch authority",
            "f_subject": "M-33.6k.12 freeze final Java execution",
            "h_subject": "M-33.6k.12 publish sealed Java production",
            "e_subject": "M-33.6k.12 publish independent Java evidence",
        }
    elif request.get("official_profile_id") == M336K11_PROFILE_ID:
        publication_values = {
            "branch_ref": request["branch_ref"],
            "q_root": "artifacts/m336k11/q36",
            "f_root": "artifacts/m336k11/f36-freeze",
            "h_root": "artifacts/m336k11/h36",
            "e_root": "artifacts/m336k11/e36",
            "q_subject": "M-33.6k.11 qualify hermetic executable authority",
            "f_subject": "M-33.6k.11 freeze final Java execution",
            "h_subject": "M-33.6k.11 publish sealed Java production",
            "e_subject": "M-33.6k.11 publish independent Java evidence",
        }
    elif request.get("official_profile_id") == M336K10_PROFILE_ID:
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
