"""Canonical V4 request and side-effect-free validation for M-33.6k.8."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, ClassVar, Self

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_execution import (
    executable_dependency_manifest_from_dict,
    verify_m336k2_executable_handles,
)
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2ProtocolError,
    m336k2_minimal_environment,
)
from ai_brain.stage3.acquisition.m336k5_authorization import M336K5FinalAuthorization
from ai_brain.stage3.acquisition.m336k5_identity import (
    M336K8_PROTOCOL_RUN_ID,
    M336K5RouteIdentityBundle,
)
from ai_brain.stage3.acquisition.m336k5_registry import build_m336k5_route_registry
from ai_brain.stage3.acquisition.m336k5_request import (
    _verify_destination_set,
    _verify_identity_policy_components,
)
from ai_brain.stage3.acquisition.m336k5_startup import (
    M336K5PythonStartupPolicy,
    startup_receipt_from_path,
)
from ai_brain.stage3.acquisition.m336k7_contracts import (
    M336K7LegacyCapsuleCompatibilityReceipt,
    M336K7PersistentCapsuleBindingSet,
    M336K7ResourceBudgetPolicy,
    M336K7ResourceGateReceipt,
    M336K7ResourceObservationReceipt,
    storage_reservation_from_dict,
    verify_m336k7_capsule_compatibility_binding,
    verify_m336k7_resource_gate_binding,
)
from ai_brain.stage3.acquisition.m336k7_request import (
    _legacy_stage_karina,
    _strict_liveness,
    _verify_capsule_bindings,
    _verify_live_karina,
    _verify_live_windows_resources,
)
from ai_brain.stage3.acquisition.m336k8_contracts import (
    CURRENT_IMPLEMENTATION_CONTROLLER,
    M336K8_POST_FREEZE_CONSUMED_COMPONENTS,
    M336K8BridgeSurfaceManifest,
    M336K8ControllerStartupBinding,
    M336K8FreezeAssemblyPlan,
    M336K8FreezeAssemblyReceipt,
    M336K8FreezeInputAssembler,
    M336K8FrozenContractCompatibilityGateV2,
    M336K8LegacyControllerAliasReceipt,
    M336K8PersistentCapsuleSourceBinding,
    M336K8PostFreezeInputBundleV2,
    M336K8ProjectSourceIdentityPolicy,
    M336K8ProjectSourceIdentityReceipt,
    M336K8SourceDomainCompatibilityReceipt,
    build_m336k8_project_source_identity_receipt,
    m336k8_semantic_binding_mismatches,
    require_m336k8_frozen_bytes,
)
from ai_brain.stage3.acquisition.m336k8_freeze import (
    M336K8CommittedFreezeAttestation,
    M336K8FreezeManifest,
)

M336K8_FINAL_REQUEST_CONTRACT = {
    "schema_version": 4,
    "contract_role": "M336K8_CANONICAL_FINAL_ROUTE_REQUEST_V4",
    "identity_derivation": (
        "typed_final_authorization",
        "typed_source_domain_freeze_manifest",
        "route_identity_bundle",
        "post_freeze_input_bundle_v2",
        "freeze_assembly_plan",
        "source_domain_compatibility",
    ),
    "historical_current_authority_calls": 0,
    "canonical_serialization": "UTF-8/LF/RFC8785-compatible-project-canonical-json",
}
M336K8_FINAL_REQUEST_BUILDER_HASH = content_hash(M336K8_FINAL_REQUEST_CONTRACT)


def _is_hash(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_sha(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True)
class M336K8FinalRouteRequestV4:
    schema_version: int
    contract_role: str
    purpose: str
    repository: str
    git_executable: str
    python_executable: str
    exact_implementation_tip: str
    exact_freeze_sha: str
    freeze_manifest: str
    freeze_attestation: str | None
    final_authorization: str
    route_identity_bundle: str
    post_freeze_input_bundle: str
    freeze_assembly_plan: str
    freeze_assembly_receipt: str
    controller_source_identity_policy: str
    controller_source_identity_receipt: str
    controller_python_environment_manifest: str
    controller_executable_dependency_manifest: str
    controller_startup_binding: str
    persistent_capsule_binding_set: str
    persistent_capsule_source_binding: str
    persistent_capsule_python_environment_manifest: str
    persistent_capsule_executable_dependency_manifest: str
    legacy_capsule_compatibility: str
    legacy_controller_alias_receipt: str
    bridge_surface_manifest: str
    source_domain_compatibility: str
    frozen_contract_compatibility_v2: str
    resource_budget_policy: str
    resource_observation_receipt: str
    storage_reservation_receipt: str
    storage_reservation_file: str
    resource_gate_receipt: str
    capsule_liveness_receipt: str
    publication_contract: str
    route_ledger: str
    route_receipt: str
    stage_state: str
    stage_receipt_root: str
    private_root: str
    authority_statement: str
    frozen_spdx_reference: str
    windows_java: str
    windows_javac: str
    final_destinations: dict[str, str]
    karina: dict[str, str]
    executable_handles: dict[str, str]
    builder_identity_hash: str
    request_hash: str

    ROLE: ClassVar[str] = "M336K8_CANONICAL_FINAL_ROUTE_REQUEST_V4"

    @property
    def exact_f32_sha(self) -> str:
        """Private compatibility alias for unchanged capsule-binding helpers."""

        return self.exact_freeze_sha

    @property
    def exact_f30_sha(self) -> str:
        """Private compatibility alias for unchanged resource helpers."""

        return self.exact_freeze_sha

    @property
    def capsule_binding_set(self) -> str:
        return self.persistent_capsule_binding_set

    @property
    def legacy_compatibility_receipt(self) -> str:
        return self.legacy_capsule_compatibility

    def _body(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("request_hash")
        return value

    def canonical_object(self) -> dict[str, Any]:
        return {**self._body(), "request_hash": self.request_hash}

    def verify(self) -> None:
        field_names = set(type(self).__dataclass_fields__)
        phase_tokens = ("f30", "f31", "f32", "f33", "pre_f", "post_f")
        if (
            self.schema_version != 4
            or self.contract_role != self.ROLE
            or self.purpose not in {"DISPOSABLE", "OFFICIAL", "QUALIFICATION"}
            or not _is_sha(self.exact_implementation_tip)
            or not _is_sha(self.exact_freeze_sha)
            or any(
                token in name.casefold()
                for name in field_names
                for token in phase_tokens
            )
            or self.builder_identity_hash != M336K8_FINAL_REQUEST_BUILDER_HASH
            or not _is_hash(self.request_hash)
            or self.request_hash != content_hash(self._body())
        ):
            raise M336K2ProtocolError("M336K8 canonical final request is invalid")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Self:
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise M336K2ProtocolError("M336K8 final request fields changed")
        result = cls(**value)
        result.verify()
        return result


@dataclass(frozen=True)
class M336K8PreLedgerInvocationReceipt:
    schema_version: int
    contract_role: str
    exact_implementation_tip: str
    exact_freeze_sha: str
    route_identity_bundle_hash: str
    canonical_final_request_hash: str
    freeze_hash: str
    post_freeze_input_bundle_hash: str
    authorization_hash: str
    source_identity_receipt_hash: str
    controller_startup_binding_hash: str
    persistent_capsule_source_binding_hash: str
    bridge_surface_manifest_hash: str
    source_domain_compatibility_receipt_hash: str
    freeze_assembly_plan_hash: str
    producer_origin_map_hash: str
    freeze_assembly_receipt_hash: str
    compatibility_gate_v2_hash: str
    resource_budget_policy_hash: str
    resource_observation_hash: str
    storage_reservation_receipt_hash: str
    resource_gate_receipt_hash: str
    capsule_binding_set_hash: str
    capsule_liveness_receipt_hash: str
    startup_receipt_hash: str
    karina_startup_receipt_hash: str
    acquisition_reservations: int
    acquisition_invocations: int
    selector_reservations: int
    selector_invocations: int
    evaluator_reservations: int
    evaluator_invocations: int
    route_ledger_writes: int
    source_requests: int
    vault_files: int
    cleanup_operations_after_freeze: int
    karina_host_preflight_hash: str
    karina_storage_preflight_hash: str
    status: str
    receipt_hash: str


@dataclass(frozen=True)
class M336K8ValidatedInvocation:
    request: M336K8FinalRouteRequestV4
    bundle: M336K5RouteIdentityBundle
    authorization: M336K5FinalAuthorization
    freeze: M336K8FreezeManifest
    post_freeze_inputs: M336K8PostFreezeInputBundleV2
    resource_policy: M336K7ResourceBudgetPolicy
    resource_observation: M336K7ResourceObservationReceipt
    storage_reservation: Any
    resource_gate: M336K7ResourceGateReceipt
    capsule_binding_set: M336K7PersistentCapsuleBindingSet
    source_identity: M336K8ProjectSourceIdentityReceipt
    controller_startup: M336K8ControllerStartupBinding
    capsule_source: M336K8PersistentCapsuleSourceBinding
    bridge: M336K8BridgeSurfaceManifest
    source_compatibility: M336K8SourceDomainCompatibilityReceipt
    assembly_plan: M336K8FreezeAssemblyPlan
    assembly_receipt: M336K8FreezeAssemblyReceipt
    compatibility_gate: M336K8FrozenContractCompatibilityGateV2
    receipt: M336K8PreLedgerInvocationReceipt


def build_m336k8_final_route_request(**values: Any) -> M336K8FinalRouteRequestV4:
    body = {
        "schema_version": 4,
        "contract_role": M336K8FinalRouteRequestV4.ROLE,
        **values,
        "builder_identity_hash": M336K8_FINAL_REQUEST_BUILDER_HASH,
    }
    if set(body) != set(M336K8FinalRouteRequestV4.__dataclass_fields__) - {
        "request_hash"
    }:
        raise M336K2ProtocolError("M336K8 request builder arguments changed")
    result = M336K8FinalRouteRequestV4(**body, request_hash=content_hash(body))
    result.verify()
    return result


def write_m336k8_final_route_request(
    request: M336K8FinalRouteRequestV4, output: Path
) -> None:
    request.verify()
    if output.exists():
        raise FileExistsError("M336K8 canonical request output must be fresh")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        canonical_json(request.canonical_object()) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_m336k8_final_route_request(path: Path) -> M336K8FinalRouteRequestV4:
    raw = path.resolve(strict=True).read_bytes()
    value = _strict_object(raw)
    request = M336K8FinalRouteRequestV4.from_dict(value)
    require_m336k8_frozen_bytes((canonical_json(value) + "\n").encode("utf-8"), raw)
    return request


def validate_m336k8_final_invocation(
    request_path: Path,
    *,
    startup_receipt_path: Path,
) -> M336K8ValidatedInvocation:
    """Validate exact committed V4 inputs without writing any route state."""

    request = load_m336k8_final_route_request(request_path)
    startup = startup_receipt_from_path(startup_receipt_path)
    root = Path(request.repository).resolve(strict=True)
    git = Path(request.git_executable).resolve(strict=True)
    freeze_path = Path(request.freeze_manifest).resolve(strict=True)
    freeze = M336K8FreezeManifest.from_dict(_object(freeze_path))
    freeze.verify(root, allow_prospective=True)
    components = {item.name: item for item in freeze.components}
    _verify_frozen_component_handles(root, components, request)

    bundle = M336K5RouteIdentityBundle.from_dict(
        _object(Path(request.route_identity_bundle).resolve(strict=True))
    )
    authorization = M336K5FinalAuthorization.from_dict(
        _object(Path(request.final_authorization).resolve(strict=True))
    )
    authorization.verify(bundle)
    post = M336K8PostFreezeInputBundleV2.from_dict(
        _object(Path(request.post_freeze_input_bundle).resolve(strict=True))
    )
    policy = M336K8ProjectSourceIdentityPolicy.from_dict(
        _object(Path(request.controller_source_identity_policy).resolve(strict=True))
    )
    source_identity = M336K8ProjectSourceIdentityReceipt.from_dict(
        _object(Path(request.controller_source_identity_receipt).resolve(strict=True))
    )
    actual_source_identity = build_m336k8_project_source_identity_receipt(
        repository=root,
        git_executable=git,
        exact_implementation_tip=request.exact_implementation_tip,
        policy=policy,
    )
    if source_identity != actual_source_identity or source_identity.status != "PASS":
        raise M336K2ProtocolError("M336K8 committed/live source identity changed")

    controller_environment = _verified_object(
        Path(request.controller_python_environment_manifest),
        "environment_manifest_hash",
    )
    controller_dependencies = executable_dependency_manifest_from_dict(
        _object(Path(request.controller_executable_dependency_manifest))
    )
    controller_startup = M336K8ControllerStartupBinding.from_dict(
        _object(Path(request.controller_startup_binding))
    )
    capsule_binding = M336K7PersistentCapsuleBindingSet.from_dict(
        _object(Path(request.persistent_capsule_binding_set))
    )
    capsule_source = M336K8PersistentCapsuleSourceBinding.from_dict(
        _object(Path(request.persistent_capsule_source_binding))
    )
    capsule_environment = _verified_object(
        Path(request.persistent_capsule_python_environment_manifest), "identity_hash"
    )
    capsule_dependencies = _verified_object(
        Path(request.persistent_capsule_executable_dependency_manifest), "manifest_hash"
    )
    legacy_capsule = M336K7LegacyCapsuleCompatibilityReceipt.from_dict(
        _object(Path(request.legacy_capsule_compatibility))
    )
    legacy_alias = M336K8LegacyControllerAliasReceipt.from_dict(
        _object(Path(request.legacy_controller_alias_receipt))
    )
    bridge = M336K8BridgeSurfaceManifest.from_dict(
        _object(Path(request.bridge_surface_manifest))
    )
    source_compatibility = M336K8SourceDomainCompatibilityReceipt.from_dict(
        _object(Path(request.source_domain_compatibility))
    )
    assembly_plan = M336K8FreezeAssemblyPlan.from_dict(
        _object(Path(request.freeze_assembly_plan))
    )
    assembly_receipt = M336K8FreezeAssemblyReceipt.from_dict(
        _object(Path(request.freeze_assembly_receipt))
    )
    frozen_gate = M336K8FrozenContractCompatibilityGateV2.from_dict(
        _object(Path(request.frozen_contract_compatibility_v2))
    )
    resource_policy = M336K7ResourceBudgetPolicy.from_dict(
        _object(Path(request.resource_budget_policy))
    )
    resource_observation = M336K7ResourceObservationReceipt.from_dict(
        _object(Path(request.resource_observation_receipt))
    )
    reservation = storage_reservation_from_dict(
        _object(Path(request.storage_reservation_receipt))
    )
    resource_gate = M336K7ResourceGateReceipt.from_dict(
        _object(Path(request.resource_gate_receipt))
    )
    liveness = _strict_liveness(_object(Path(request.capsule_liveness_receipt)))

    if (
        request.exact_implementation_tip != freeze.implementation_tip
        or authorization.exact_implementation_tip != freeze.implementation_tip
        or authorization.exact_q30_sha != freeze.exact_qualification_sha
        or request.purpose == "OFFICIAL"
        and bundle.protocol_run_id.value != M336K8_PROTOCOL_RUN_ID
        or bundle.route_version.value.split(".", 1)[0] != "m336k8"
        or freeze.route_identity_bundle_hash != bundle.bundle_hash
        or freeze.authorization_hash != authorization.authorization_hash
        or freeze.route_hash != bundle.route_manifest_hash
        or freeze.canonical_request_builder_hash != request.builder_identity_hash
        or freeze.post_freeze_input_bundle_hash != post.bundle_hash
        or freeze.source_identity_receipt_hash != source_identity.receipt_hash
        or freeze.controller_startup_binding_hash != controller_startup.binding_hash
        or freeze.persistent_capsule_source_binding_hash != capsule_source.binding_hash
        or freeze.bridge_surface_manifest_hash != bridge.manifest_hash
        or freeze.source_domain_compatibility_receipt_hash
        != source_compatibility.receipt_hash
        or freeze.freeze_assembly_plan_hash != assembly_plan.plan_hash
        or freeze.freeze_assembly_receipt_hash != assembly_receipt.receipt_hash
        or freeze.compatibility_gate_v2_hash != frozen_gate.report_hash
    ):
        raise M336K2ProtocolError("M336K8 request/freeze identity binding changed")

    registry = build_m336k5_route_registry(root, "m336k8")
    if registry.registry_hash != bundle.route_registry_hash:
        raise M336K2ProtocolError("M336K8 executable route registry changed")
    _verify_identity_policy_components(root, components, bundle)
    verify_m336k7_resource_gate_binding(
        resource_policy, resource_observation, reservation, resource_gate
    )
    _verify_live_windows_resources(
        request, resource_policy, reservation, reservation_released=False
    )
    _verify_controller_domain(
        request,
        startup,
        policy,
        source_identity,
        controller_environment,
        controller_dependencies,
        controller_startup,
        legacy_alias,
        authorization,
    )
    verify_m336k7_capsule_compatibility_binding(capsule_binding, legacy_capsule)
    _verify_capsule_source_domain(
        capsule_binding,
        capsule_source,
        capsule_environment,
        capsule_dependencies,
        bridge,
        liveness,
    )
    _verify_source_domain_compatibility(
        source_identity,
        controller_startup,
        capsule_source,
        bridge,
        source_compatibility,
    )
    values, origins = _assembly_values(
        root,
        components,
        policy=policy,
        source_identity=source_identity,
        controller_environment=controller_environment,
        controller_dependencies=asdict(controller_dependencies),
        controller_startup=controller_startup,
        capsule_environment=capsule_environment,
        capsule_dependencies=capsule_dependencies,
        capsule_source=capsule_source,
        bridge=bridge,
        source_compatibility=source_compatibility,
        resource_policy=resource_policy,
        resource_observation=resource_observation,
        reservation=reservation,
        resource_gate=resource_gate,
        capsule_binding=capsule_binding,
        legacy_capsule=legacy_capsule,
        liveness=liveness,
        legacy_alias=legacy_alias,
        bundle=bundle,
        authorization=authorization,
        post=post,
    )
    actual_assembly = M336K8FreezeInputAssembler.assemble(
        plan=assembly_plan,
        component_values=values,
        component_origins=origins,
        semantic_verifier=m336k8_semantic_binding_mismatches,
    )
    if actual_assembly != assembly_receipt or assembly_receipt.status != "PASS":
        raise M336K2ProtocolError("M336K8 freeze assembly receipt changed")
    gate_artifacts = _compatibility_artifacts(
        values,
        assembly_plan=assembly_plan,
        assembly_receipt=assembly_receipt,
    )
    actual_gate = M336K8FrozenContractCompatibilityGateV2.run(
        plan=assembly_plan,
        artifacts=gate_artifacts,
        semantic_verifier=m336k8_semantic_binding_mismatches,
        current_route_sources=(Path(__file__).resolve(strict=True),),
    )
    if actual_gate != frozen_gate or frozen_gate.status != "PASS":
        raise M336K2ProtocolError("M336K8 compatibility gate V2 changed")
    _verify_post_bundle(
        root,
        components,
        post,
        policy,
        source_identity,
        controller_environment,
        controller_dependencies,
        controller_startup,
        capsule_binding,
        capsule_source,
        capsule_environment,
        capsule_dependencies,
        bridge,
        source_compatibility,
        assembly_plan,
        assembly_receipt,
        legacy_alias,
        resource_policy,
        resource_observation,
        reservation,
        resource_gate,
        liveness,
        bundle,
        authorization,
    )
    _verify_destination_set(root, git, request)
    _verify_lineage(root, git, request, freeze, bundle, post)
    capsule, legacy_public, karina_dependencies, capsule_identity = (
        _verify_capsule_bindings(
            root,
            request,
            components,
            freeze=freeze,
            binding=capsule_binding,
            compatibility=legacy_capsule,
            liveness=liveness,
        )
    )
    host, storage = _verify_live_karina(
        root,
        request,
        freeze=freeze,
        capsule=capsule,
        public=legacy_public,
        dependencies=karina_dependencies,
        capsule_source_identity=capsule_identity,
    )
    body = {
        "schema_version": 4,
        "contract_role": "M336K8_SIDE_EFFECT_FREE_PRELEDGER_INVOCATION_RECEIPT",
        "exact_implementation_tip": request.exact_implementation_tip,
        "exact_freeze_sha": request.exact_freeze_sha,
        "route_identity_bundle_hash": bundle.bundle_hash,
        "canonical_final_request_hash": request.request_hash,
        "freeze_hash": freeze.manifest_hash,
        "post_freeze_input_bundle_hash": post.bundle_hash,
        "authorization_hash": authorization.authorization_hash,
        "source_identity_receipt_hash": source_identity.receipt_hash,
        "controller_startup_binding_hash": controller_startup.binding_hash,
        "persistent_capsule_source_binding_hash": capsule_source.binding_hash,
        "bridge_surface_manifest_hash": bridge.manifest_hash,
        "source_domain_compatibility_receipt_hash": source_compatibility.receipt_hash,
        "freeze_assembly_plan_hash": assembly_plan.plan_hash,
        "producer_origin_map_hash": assembly_plan.producer_origin_map_hash,
        "freeze_assembly_receipt_hash": assembly_receipt.receipt_hash,
        "compatibility_gate_v2_hash": frozen_gate.report_hash,
        "resource_budget_policy_hash": resource_policy.policy_hash,
        "resource_observation_hash": resource_observation.observation_hash,
        "storage_reservation_receipt_hash": reservation.receipt_hash,
        "resource_gate_receipt_hash": resource_gate.receipt_hash,
        "capsule_binding_set_hash": capsule_binding.binding_set_hash,
        "capsule_liveness_receipt_hash": liveness.receipt_hash,
        "startup_receipt_hash": startup.receipt_hash,
        "karina_startup_receipt_hash": host["startup_receipt_hash"],
        "acquisition_reservations": 0,
        "acquisition_invocations": 0,
        "selector_reservations": 0,
        "selector_invocations": 0,
        "evaluator_reservations": 0,
        "evaluator_invocations": 0,
        "route_ledger_writes": 0,
        "source_requests": 0,
        "vault_files": 0,
        "cleanup_operations_after_freeze": 0,
        "karina_host_preflight_hash": host["receipt_hash"],
        "karina_storage_preflight_hash": content_hash(
            {
                "required_free_bytes": storage["required_free_bytes"],
                "minimum_free_inodes": 100_000,
                "qualification_margin": True,
                "status": storage["status"],
            }
        ),
        "status": "FINAL_INVOCATION_ACCEPTED_PRE_LEDGER",
    }
    receipt = M336K8PreLedgerInvocationReceipt(**body, receipt_hash=content_hash(body))
    return M336K8ValidatedInvocation(
        request,
        bundle,
        authorization,
        freeze,
        post,
        resource_policy,
        resource_observation,
        reservation,
        resource_gate,
        capsule_binding,
        source_identity,
        controller_startup,
        capsule_source,
        bridge,
        source_compatibility,
        assembly_plan,
        assembly_receipt,
        frozen_gate,
        receipt,
    )


def _verify_frozen_component_handles(
    root: Path, components: dict[str, Any], request: M336K8FinalRouteRequestV4
) -> None:
    mappings = {
        "final_authorization": request.final_authorization,
        "route_identity_bundle": request.route_identity_bundle,
        "post_freeze_input_bundle": request.post_freeze_input_bundle,
        "freeze_assembly_plan": request.freeze_assembly_plan,
        "freeze_assembly_receipt": request.freeze_assembly_receipt,
        "controller_source_identity_policy": request.controller_source_identity_policy,
        "controller_source_identity_receipt": request.controller_source_identity_receipt,
        "controller_python_environment_manifest": request.controller_python_environment_manifest,
        "controller_executable_dependency_manifest": request.controller_executable_dependency_manifest,
        "controller_startup_binding": request.controller_startup_binding,
        "capsule_binding_set": request.persistent_capsule_binding_set,
        "persistent_capsule_source_binding": request.persistent_capsule_source_binding,
        "persistent_capsule_python_environment_manifest": request.persistent_capsule_python_environment_manifest,
        "persistent_capsule_executable_dependency_manifest": request.persistent_capsule_executable_dependency_manifest,
        "legacy_capsule_compatibility": request.legacy_capsule_compatibility,
        "legacy_controller_alias_receipt": request.legacy_controller_alias_receipt,
        "bridge_surface_manifest": request.bridge_surface_manifest,
        "source_domain_compatibility": request.source_domain_compatibility,
        "frozen_contract_compatibility_v2": request.frozen_contract_compatibility_v2,
        "resource_budget_policy": request.resource_budget_policy,
        "resource_observation": request.resource_observation_receipt,
        "storage_reservation": request.storage_reservation_receipt,
        "resource_gate": request.resource_gate_receipt,
        "capsule_liveness": request.capsule_liveness_receipt,
    }
    for name, supplied_value in mappings.items():
        component = components[name]
        frozen = root.joinpath(*Path(component.relative_path).parts).resolve(
            strict=True
        )
        supplied = Path(supplied_value).resolve(strict=True)
        if frozen != supplied:
            raise M336K2ProtocolError(f"M336K8 frozen handle changed: {name}")
    controller_environment = Path(
        request.controller_python_environment_manifest
    ).read_bytes()
    controller_dependencies = Path(
        request.controller_executable_dependency_manifest
    ).read_bytes()
    require_m336k8_frozen_bytes(
        controller_environment,
        _component_path(root, components, "python_environment_manifest").read_bytes(),
    )
    require_m336k8_frozen_bytes(
        controller_dependencies,
        _component_path(
            root, components, "executable_dependency_manifest"
        ).read_bytes(),
    )


def _verify_controller_domain(
    request,
    startup,
    policy,
    source_identity,
    environment,
    dependency,
    binding,
    alias,
    authorization,
) -> None:
    expected_environment_fields = {
        "schema_version",
        "contract_role",
        "source_domain",
        "exact_implementation_tip",
        "startup_policy_hash",
        "project_source_identity_policy_hash",
        "project_source_identity_receipt_hash",
        "project_source_identity_hash",
        "sanitized_environment_policy_hash",
        "python_path_inherited",
        "python_home_inherited",
        "python_user_base_inherited",
        "user_site_effective_state_required",
        "torch_at_startup_allowed",
        "environment_manifest_hash",
    }
    handles = {name: Path(value) for name, value in request.executable_handles.items()}
    verify_m336k2_executable_handles(dependency, handles)
    startup_policy_value = _component_object(
        Path(request.repository),
        _component_map(request),
        "python_startup_policy",
    )
    startup_policy = M336K5PythonStartupPolicy.from_dict(startup_policy_value)
    bootstrap = _component_object(
        Path(request.repository), _component_map(request), "python_startup_bootstrap"
    )
    launcher = _component_object(
        Path(request.repository), _component_map(request), "windows_python_launcher"
    )
    sanitized = _component_object(
        Path(request.repository),
        _component_map(request),
        "sanitized_environment_policy",
    )
    startup_schema = _component_object(
        Path(request.repository), _component_map(request), "startup_receipt_schema"
    )
    if (
        set(environment) != expected_environment_fields
        or environment["schema_version"] != 2
        or environment["contract_role"]
        != "M336K8_CONTROLLER_PYTHON_ENVIRONMENT_MANIFEST"
        or environment["source_domain"] != CURRENT_IMPLEMENTATION_CONTROLLER
        or environment["exact_implementation_tip"] != request.exact_implementation_tip
        or environment["project_source_identity_policy_hash"] != policy.policy_hash
        or environment["project_source_identity_receipt_hash"]
        != source_identity.receipt_hash
        or environment["project_source_identity_hash"]
        != source_identity.live_project_source_identity
        or environment["startup_policy_hash"] != startup_policy.policy_hash
        or environment["sanitized_environment_policy_hash"] != sanitized["receipt_hash"]
        or environment["python_path_inherited"] is not False
        or environment["python_home_inherited"] is not False
        or environment["python_user_base_inherited"] is not False
        or environment["user_site_effective_state_required"] is not True
        or environment["torch_at_startup_allowed"] is not False
        or dependency.environment_identity_hash
        != environment["environment_manifest_hash"]
        or dependency.source_identity_hash
        != source_identity.live_project_source_identity
        or dependency.python_invocation_handle_hash
        != content_hash(str(Path(request.python_executable).absolute()))
        or handles["git"] != Path(request.git_executable)
        or handles["python"] != Path(request.python_executable)
        or handles["java"] != Path(request.windows_java)
        or handles["javac"] != Path(request.windows_javac)
        or startup.project_source_identity
        != source_identity.live_project_source_identity
        or startup.startup_policy_hash != startup_policy.policy_hash
        or authorization.python_startup_policy_hash != startup_policy.policy_hash
        or authorization.python_environment_manifest_hash
        != environment["environment_manifest_hash"]
        or binding.exact_implementation_tip != request.exact_implementation_tip
        or binding.project_source_identity_policy_hash != policy.policy_hash
        or binding.project_source_identity_receipt_hash != source_identity.receipt_hash
        or binding.controller_project_source_identity
        != source_identity.live_project_source_identity
        or binding.controller_python_environment_manifest_hash
        != environment["environment_manifest_hash"]
        or binding.controller_executable_dependency_manifest_hash
        != dependency.manifest_hash
        or binding.startup_policy_hash != startup_policy.policy_hash
        or binding.sanitized_environment_policy_hash != sanitized["receipt_hash"]
        or binding.startup_receipt_schema_hash != startup_schema["schema_hash"]
        or binding.bootstrap_source_hash != bootstrap["source_bytes_hash"]
        or binding.windows_launcher_source_hash != launcher["source_bytes_hash"]
        or binding.validate_only_target_source_hash
        != bytes_hash(
            (
                Path(request.repository) / "scripts/m336k8_run_final_route.py"
            ).read_bytes()
        )
        or binding.final_controller_target_source_hash
        != binding.validate_only_target_source_hash
        or alias.controller_python_environment_manifest_hash
        != environment["environment_manifest_hash"]
        or alias.legacy_python_environment_manifest_alias_hash
        != environment["environment_manifest_hash"]
        or alias.controller_executable_dependency_manifest_hash
        != dependency.manifest_hash
        or alias.legacy_executable_dependency_manifest_alias_hash
        != dependency.manifest_hash
    ):
        raise M336K2ProtocolError("M336K8 controller source domain changed")


def _verify_capsule_source_domain(
    binding,
    capsule,
    environment,
    dependencies,
    bridge,
    liveness,
) -> None:
    relations = (
        (capsule.persistent_capsule_binding_set_hash, binding.binding_set_hash),
        (capsule.capsule_implementation_tip, binding.implementation_tip),
        (
            capsule.capsule_project_source_identity,
            environment["project_source_identity"],
        ),
        (
            capsule.capsule_python_environment_manifest_hash,
            environment["identity_hash"],
        ),
        (
            capsule.capsule_executable_dependency_manifest_hash,
            dependencies["manifest_hash"],
        ),
        (capsule.capsule_identity_hash, binding.capsule_identity_hash),
        (capsule.capsule_content_manifest_hash, binding.capsule_content_manifest_hash),
        (
            capsule.capsule_lifecycle_policy_hash,
            binding.capsule_lifecycle_policy_hash,
        ),
        (capsule.capsule_liveness_receipt_hash, liveness.receipt_hash),
        (
            capsule.persistent_public_receipt_hash,
            binding.persistent_capsule_public_receipt_hash,
        ),
        (
            capsule.legacy_public_receipt_hash,
            binding.legacy_public_capsule_receipt_hash,
        ),
        (capsule.stable_host_identity_hash, binding.stable_karina_host_identity_hash),
        (capsule.bridge_surface_manifest_hash, bridge.manifest_hash),
    )
    if (
        any(left != right for left, right in relations)
        or liveness.status != "PASS"
        or liveness.missing_file_count != 0
        or liveness.changed_file_count != 0
        or liveness.unexpected_file_count != 0
        or liveness.mutable_quality_dependency_count != 0
        or liveness.symlink_target_change_count != 0
    ):
        raise M336K2ProtocolError("M336K8 persistent capsule source domain changed")


def _verify_source_domain_compatibility(
    source_identity, controller, capsule, bridge, compatibility
) -> None:
    compatibility.verify()
    if (
        compatibility.controller_startup_binding_hash != controller.binding_hash
        or compatibility.persistent_capsule_source_binding_hash != capsule.binding_hash
        or compatibility.controller_project_source_identity
        != source_identity.live_project_source_identity
        or compatibility.capsule_project_source_identity
        != capsule.capsule_project_source_identity
        or compatibility.full_project_identity_equality_required is not False
        or compatibility.full_project_identity_difference_count
        != int(
            source_identity.live_project_source_identity
            != capsule.capsule_project_source_identity
        )
        or compatibility.bridge_surface_manifest_hash != bridge.manifest_hash
        or compatibility.bridge_changed_entry_count != 0
        or compatibility.bridge_schema_incompatibility_count != 0
        or compatibility.controller_manifest_origin_valid is not True
        or compatibility.capsule_manifest_origin_valid is not True
        or compatibility.status != "PASS"
    ):
        raise M336K2ProtocolError("M336K8 source-domain compatibility changed")


def _assembly_values(
    root: Path,
    components: dict[str, Any],
    **objects: Any,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    plan = M336K8FreezeAssemblyPlan.build()
    values = {
        "controller_python_environment_manifest": dict(
            objects["controller_environment"]
        ),
        "controller_executable_dependency_manifest": dict(
            objects["controller_dependencies"]
        ),
        "controller_source_identity_policy": objects["policy"].canonical_object(),
        "controller_source_identity_receipt": objects[
            "source_identity"
        ].canonical_object(),
        "controller_startup_binding": objects["controller_startup"].canonical_object(),
        "persistent_capsule_python_environment_manifest": dict(
            objects["capsule_environment"]
        ),
        "persistent_capsule_executable_dependency_manifest": dict(
            objects["capsule_dependencies"]
        ),
        "persistent_capsule_source_binding": objects[
            "capsule_source"
        ].canonical_object(),
        "bridge_surface_manifest": objects["bridge"].canonical_object(),
        "source_domain_compatibility": objects[
            "source_compatibility"
        ].canonical_object(),
        "resource_budget_policy": objects["resource_policy"].canonical_object(),
        "resource_observation": objects["resource_observation"].canonical_object(),
        "storage_reservation": asdict(objects["reservation"]),
        "resource_gate": objects["resource_gate"].canonical_object(),
        "capsule_binding_set": objects["capsule_binding"].canonical_object(),
        "legacy_capsule_compatibility": objects["legacy_capsule"].canonical_object(),
        "capsule_liveness": asdict(objects["liveness"]),
        "legacy_controller_alias_receipt": objects["legacy_alias"].canonical_object(),
        "route_identity_bundle": objects["bundle"].canonical_object(),
        "final_authorization": objects["authorization"].canonical_object(),
        "post_freeze_input_bundle": objects["post"].canonical_object(),
    }
    expected_names = {item.component_name for item in plan.entries}
    if set(values) != expected_names:
        raise M336K2ProtocolError("M336K8 assembly value registry changed")
    origins = {item.component_name: item.source_domain for item in plan.entries}
    for name, value in values.items():
        frozen = _component_path(root, components, name)
        require_m336k8_frozen_bytes(
            frozen.read_bytes(), (canonical_json(value) + "\n").encode("utf-8")
        )
    return values, origins


@dataclass(frozen=True)
class _CanonicalArtifact:
    value: dict[str, Any]

    def canonical_object(self) -> dict[str, Any]:
        return self.value


def _consume_hashed(value: dict[str, Any], hash_field: str) -> _CanonicalArtifact:
    body = dict(value)
    claimed = body.pop(hash_field)
    if not _is_hash(claimed) or content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K8 compatibility artifact hash changed")
    return _CanonicalArtifact(value)


def _compatibility_artifacts(
    values: dict[str, dict[str, Any]],
    *,
    assembly_plan: M336K8FreezeAssemblyPlan,
    assembly_receipt: M336K8FreezeAssemblyReceipt,
) -> dict[str, tuple[dict[str, Any], Any]]:
    consumers = {
        "controller_python_environment_manifest": lambda value: _consume_hashed(
            value, "environment_manifest_hash"
        ),
        "controller_executable_dependency_manifest": executable_dependency_manifest_from_dict,
        "controller_source_identity_policy": M336K8ProjectSourceIdentityPolicy.from_dict,
        "controller_source_identity_receipt": M336K8ProjectSourceIdentityReceipt.from_dict,
        "controller_startup_binding": M336K8ControllerStartupBinding.from_dict,
        "persistent_capsule_python_environment_manifest": lambda value: _consume_hashed(
            value, "identity_hash"
        ),
        "persistent_capsule_executable_dependency_manifest": lambda value: (
            _consume_hashed(value, "manifest_hash")
        ),
        "persistent_capsule_source_binding": M336K8PersistentCapsuleSourceBinding.from_dict,
        "bridge_surface_manifest": M336K8BridgeSurfaceManifest.from_dict,
        "source_domain_compatibility": M336K8SourceDomainCompatibilityReceipt.from_dict,
        "resource_budget_policy": M336K7ResourceBudgetPolicy.from_dict,
        "resource_observation": M336K7ResourceObservationReceipt.from_dict,
        "storage_reservation": storage_reservation_from_dict,
        "resource_gate": M336K7ResourceGateReceipt.from_dict,
        "capsule_binding_set": M336K7PersistentCapsuleBindingSet.from_dict,
        "legacy_capsule_compatibility": M336K7LegacyCapsuleCompatibilityReceipt.from_dict,
        "capsule_liveness": lambda value: _CanonicalArtifact(
            asdict(_strict_liveness(value))
        ),
        "legacy_controller_alias_receipt": M336K8LegacyControllerAliasReceipt.from_dict,
        "route_identity_bundle": M336K5RouteIdentityBundle.from_dict,
        "final_authorization": M336K5FinalAuthorization.from_dict,
        "post_freeze_input_bundle": M336K8PostFreezeInputBundleV2.from_dict,
        "freeze_assembly_plan": M336K8FreezeAssemblyPlan.from_dict,
        "freeze_assembly_receipt": M336K8FreezeAssemblyReceipt.from_dict,
    }
    artifacts = {name: (value, consumers[name]) for name, value in values.items()}
    artifacts["freeze_assembly_plan"] = (
        assembly_plan.canonical_object(),
        consumers["freeze_assembly_plan"],
    )
    artifacts["freeze_assembly_receipt"] = (
        assembly_receipt.canonical_object(),
        consumers["freeze_assembly_receipt"],
    )
    expected = set(M336K8_POST_FREEZE_CONSUMED_COMPONENTS) - {
        "frozen_contract_compatibility_v2"
    }
    if set(artifacts) != expected:
        raise M336K2ProtocolError("M336K8 compatibility consumer registry changed")
    return artifacts


def _verify_post_bundle(
    root,
    components,
    post,
    policy,
    source_identity,
    controller_environment,
    controller_dependencies,
    controller_startup,
    capsule_binding,
    capsule_source,
    capsule_environment,
    capsule_dependencies,
    bridge,
    source_compatibility,
    assembly_plan,
    assembly_receipt,
    legacy_alias,
    resource_policy,
    resource_observation,
    reservation,
    resource_gate,
    liveness,
    bundle,
    authorization,
) -> None:
    expected = {
        "controller_project_source_identity_policy_hash": policy.policy_hash,
        "controller_project_source_identity_receipt_hash": source_identity.receipt_hash,
        "controller_python_environment_manifest_hash": controller_environment[
            "environment_manifest_hash"
        ],
        "controller_executable_dependency_manifest_hash": controller_dependencies.manifest_hash,
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
        "freeze_assembly_plan_hash": assembly_plan.plan_hash,
        "freeze_assembly_receipt_hash": assembly_receipt.receipt_hash,
        "legacy_controller_alias_receipt_hash": legacy_alias.receipt_hash,
        "startup_policy_hash": _component_hash(
            root, components, "python_startup_policy", "policy_hash"
        ),
        "resource_budget_policy_hash": resource_policy.policy_hash,
        "resource_observation_hash": resource_observation.observation_hash,
        "storage_reservation_receipt_hash": reservation.receipt_hash,
        "resource_gate_receipt_hash": resource_gate.receipt_hash,
        "capsule_liveness_receipt_hash": liveness.receipt_hash,
        "capsule_content_manifest_hash": _component_hash(
            root, components, "capsule_content_manifest", "manifest_hash"
        ),
        "capsule_lifecycle_policy_hash": _component_hash(
            root, components, "capsule_lifecycle_policy", "policy_hash"
        ),
        "route_identity_bundle_hash": bundle.bundle_hash,
        "route_registry_hash": _component_hash(
            root, components, "typed_route_registry", "registry_hash"
        ),
        "route_manifest_hash": _component_hash(
            root, components, "typed_route_manifest", "manifest_hash"
        ),
        "final_authorization_hash": authorization.authorization_hash,
        "candidate_pool_hash": _component_hash(
            root, components, "candidate_pool", "pool_hash"
        ),
        "acquisition_policy_hash": _component_hash(
            root, components, "acquisition_policy", "acquisition_policy_hash"
        ),
        "archive_policy_hash": _component_hash(
            root, components, "archive_policy", "policy_hash"
        ),
        "terminal_policy_hash": _component_hash(
            root, components, "candidate_terminal_policy", "policy_hash"
        ),
        "selector_policy_hash": _component_hash(
            root, components, "selector_policy", "policy_hash"
        ),
        "evaluator_policy_hash": _component_hash(
            root, components, "evaluator_policy", "policy_hash"
        ),
        "threshold_manifest_hash": _component_hash(
            root, components, "threshold_manifest", "threshold_manifest_hash"
        ),
        "publication_contract_hash": content_hash(
            (
                _component_hash(
                    root, components, "h28_publication_contract", "contract_hash"
                ),
                _component_hash(
                    root, components, "e28_publication_contract", "contract_hash"
                ),
            )
        ),
    }
    if any(getattr(post, name) != value for name, value in expected.items()):
        raise M336K2ProtocolError("M336K8 post-freeze input binding changed")


def _verify_lineage(root, git, request, freeze, bundle, post) -> None:
    if request.exact_freeze_sha == "0" * 40:
        if request.freeze_attestation is not None or request.purpose == "OFFICIAL":
            raise M336K2ProtocolError("M336K8 official request lacks exact freeze")
        return
    if request.freeze_attestation is None:
        raise M336K2ProtocolError("M336K8 exact freeze attestation is absent")
    attestation = M336K8CommittedFreezeAttestation.from_dict(
        _object(Path(request.freeze_attestation).resolve(strict=True))
    )
    branch = subprocess.run(
        (str(git), "symbolic-ref", "HEAD"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=m336k2_minimal_environment(),
    ).stdout.strip()
    head = _git(git, root, "rev-parse", "HEAD^{commit}")
    upstream = _git(git, root, "rev-parse", "@{upstream}^{commit}")
    remote_rows = _git(git, root, "ls-remote", "--exit-code", "origin", branch).split()
    remote = remote_rows[0] if remote_rows else ""
    if (
        attestation.exact_freeze_sha != request.exact_freeze_sha
        or attestation.exact_qualification_parent != freeze.exact_qualification_sha
        or attestation.route_identity_bundle_hash != bundle.bundle_hash
        or attestation.post_freeze_input_bundle_hash != post.bundle_hash
        or attestation.source_identity_receipt_hash
        != freeze.source_identity_receipt_hash
        or attestation.freeze_assembly_plan_hash != freeze.freeze_assembly_plan_hash
        or attestation.producer_origin_map_hash
        != _object(Path(request.freeze_assembly_plan))["producer_origin_map_hash"]
        or head != upstream
        or head != remote
        or head != request.exact_freeze_sha
        or branch != _authorization_branch_ref(request)
        or _git(git, root, "status", "--porcelain=v1")
    ):
        raise M336K2ProtocolError("M336K8 exact final lineage is not clean/pushed")


def build_m336k8_internal_stage_request(validated: M336K8ValidatedInvocation) -> dict:
    """Render the private schema-v3 adapter consumed by the native stage worker."""

    request = validated.request
    bundle = validated.bundle
    return {
        "schema_version": 3,
        "repository": request.repository,
        "git_executable": request.git_executable,
        "python_executable": request.python_executable,
        "exact_f28_sha": request.exact_freeze_sha,
        "freeze_manifest": request.freeze_manifest,
        "f28_attestation": request.freeze_attestation,
        "final_authorization": request.final_authorization,
        "publication_contract": request.publication_contract,
        "route_run_id": bundle.protocol_run_id.value,
        "execution_mode": bundle.execution_mode.value,
        "execution_purpose": request.purpose,
        "route_identity_bundle": request.route_identity_bundle,
        "route_identity_bundle_hash": bundle.bundle_hash,
        "startup_receipt_hash": validated.receipt.startup_receipt_hash,
        "karina_startup_receipt_hash": validated.receipt.karina_startup_receipt_hash,
        "stage_state": request.stage_state,
        "stage_receipt_root": request.stage_receipt_root,
        "private_root": request.private_root,
        "authority_statement": request.authority_statement,
        "frozen_spdx_reference": request.frozen_spdx_reference,
        "windows_java": request.windows_java,
        "windows_javac": request.windows_javac,
        "final_destinations": request.final_destinations,
        "karina": _legacy_stage_karina(request.karina),
        "executable_handles": request.executable_handles,
    }


def load_m336k8_preledger_receipt(path: Path) -> M336K8PreLedgerInvocationReceipt:
    value = _object(path.resolve(strict=True))
    if set(value) != set(M336K8PreLedgerInvocationReceipt.__dataclass_fields__):
        raise M336K2ProtocolError("M336K8 preledger receipt fields changed")
    receipt = M336K8PreLedgerInvocationReceipt(**value)
    body = asdict(receipt)
    claimed = body.pop("receipt_hash")
    counters = (
        receipt.acquisition_reservations,
        receipt.acquisition_invocations,
        receipt.selector_reservations,
        receipt.selector_invocations,
        receipt.evaluator_reservations,
        receipt.evaluator_invocations,
        receipt.route_ledger_writes,
        receipt.source_requests,
        receipt.vault_files,
        receipt.cleanup_operations_after_freeze,
    )
    if (
        content_hash(body) != claimed
        or any(counters)
        or receipt.status != "FINAL_INVOCATION_ACCEPTED_PRE_LEDGER"
    ):
        raise M336K2ProtocolError("M336K8 preledger receipt is invalid")
    return receipt


def _component_map(request: M336K8FinalRouteRequestV4) -> dict[str, Any]:
    freeze = M336K8FreezeManifest.from_dict(_object(Path(request.freeze_manifest)))
    return {item.name: item for item in freeze.components}


def _component_path(root: Path, components: dict[str, Any], name: str) -> Path:
    component = components[name]
    path = root.resolve(strict=True).joinpath(*Path(component.relative_path).parts)
    resolved = path.resolve(strict=True)
    if (
        resolved.stat().st_size != component.byte_count
        or bytes_hash(resolved.read_bytes()) != component.bytes_hash
    ):
        raise M336K2ProtocolError(f"M336K8 frozen component bytes changed: {name}")
    return resolved


def _component_object(
    root: Path, components: dict[str, Any], name: str
) -> dict[str, Any]:
    return _object(_component_path(root, components, name))


def _component_hash(
    root: Path, components: dict[str, Any], name: str, field: str
) -> str:
    value = _component_object(root, components, name)
    body = dict(value)
    claimed = body.pop(field)
    if not _is_hash(claimed) or content_hash(body) != claimed:
        raise M336K2ProtocolError(f"M336K8 component hash changed: {name}")
    return claimed


def _verified_object(path: Path, hash_field: str) -> dict[str, Any]:
    value = _object(path.resolve(strict=True))
    body = dict(value)
    claimed = body.pop(hash_field)
    if not _is_hash(claimed) or content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K8 object hash changed")
    return value


def _authorization_branch_ref(request: M336K8FinalRouteRequestV4) -> str:
    authorization = M336K5FinalAuthorization.from_dict(
        _object(Path(request.final_authorization))
    )
    return authorization.branch_ref


def _strict_object(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M336K2ProtocolError("M336K8 JSON input is invalid") from error
    if type(value) is not dict:
        raise M336K2ProtocolError("M336K8 JSON input is not an object")
    return value


def _object(path: Path) -> dict[str, Any]:
    return _strict_object(path.resolve(strict=True).read_bytes())


def _git(git: Path, root: Path, *arguments: str) -> str:
    return subprocess.run(
        (str(git), *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env=m336k2_minimal_environment(),
    ).stdout.strip()
