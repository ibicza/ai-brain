"""Closed route and schema registries for the M-33.6k.5 recovery route."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336k2_controller import M336K2_ROUTE_STAGES
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_identity import (
    M336K5_ROUTE_VERSION,
    M336K6_ROUTE_VERSION,
    M336K7_ROUTE_VERSION,
    M336K8_ROUTE_VERSION,
    M336K5RouteComponentId,
    M336K5RouteVersion,
)
from ai_brain.stage3.acquisition.m336k9_profiles import (
    m336k_official_profile_registry,
)

M336K5_ROUTE_COMPONENTS = (
    ("typed-identity", "src/ai_brain/stage3/acquisition/m336k5_identity.py"),
    ("route-registry", "src/ai_brain/stage3/acquisition/m336k5_registry.py"),
    ("final-request", "src/ai_brain/stage3/acquisition/m336k5_request.py"),
    ("typed-authorization", "src/ai_brain/stage3/acquisition/m336k5_authorization.py"),
    ("typed-freeze", "src/ai_brain/stage3/acquisition/m336k5_freeze.py"),
    ("typed-controller", "src/ai_brain/stage3/acquisition/m336k5_controller.py"),
    ("hermetic-execution", "src/ai_brain/stage3/acquisition/m336k5_execution.py"),
    ("startup-policy", "src/ai_brain/stage3/acquisition/m336k5_startup.py"),
    ("resource-monitor", "src/ai_brain/stage3/acquisition/m336k5_resources.py"),
    ("cleanup-policy", "src/ai_brain/stage3/acquisition/m336k5_cleanup.py"),
    ("recovery-policy", "src/ai_brain/stage3/acquisition/m336k5_recovery.py"),
    ("final-cli", "scripts/m336k5_run_final_route.py"),
    ("stdlib-bootstrap", "scripts/m336k5_python_bootstrap.py"),
    ("windows-launcher", "scripts/m336k5_launch_python.ps1"),
    ("request-builder-cli", "scripts/m336k5_build_final_route_request.py"),
    ("component-builder-cli", "scripts/m336k5_build_component_bundle.py"),
    ("startup-component-builder-cli", "scripts/m336k5_build_startup_components.py"),
    ("resource-manager-cli", "scripts/m336k5_manage_resources.py"),
    ("recovery-manager-cli", "scripts/m336k5_manage_recovery.py"),
    ("cleanup-manager-cli", "scripts/m336k5_cleanup_root.py"),
    ("disposable-qualifier", "scripts/m336k5_qualify_disposable_protocol.py"),
    ("exact-quality", "scripts/m336k5_run_exact_quality.py"),
    ("identity-mutations", "scripts/m336k5_run_identity_mutations.py"),
    ("karina-capsule-preparer", "scripts/m336k5_prepare_karina_capsule.py"),
    (
        "karina-capsule-metadata",
        "scripts/m336k5_export_karina_capsule_metadata.py",
    ),
    ("native-stage", "src/ai_brain/stage3/acquisition/m336k2_stage.py"),
    ("native-stage-cli", "scripts/m336k2_run_stage.py"),
    ("acquisition", "src/ai_brain/stage3/acquisition/m336k2_acquisition.py"),
    ("route-ledger", "src/ai_brain/stage3/acquisition/m336k2_protocol.py"),
    ("execution", "src/ai_brain/stage3/acquisition/m336k2_execution.py"),
    ("publication", "src/ai_brain/stage3/acquisition/m336k2_publication.py"),
    ("selector", "src/ai_brain/stage3/acquisition/m336f_selection.py"),
    ("evaluator", "src/ai_brain/stage3/acquisition/m336i_evaluation.py"),
)
M336K6_ROUTE_COMPONENTS = M336K5_ROUTE_COMPONENTS + (
    ("persistent-capsule", "src/ai_brain/stage3/acquisition/m336k6_capsule.py"),
    ("preservation-cleanup", "src/ai_brain/stage3/acquisition/m336k6_cleanup.py"),
    (
        "extended-resource-monitor",
        "src/ai_brain/stage3/acquisition/m336k6_resources.py",
    ),
    ("persistent-capsule-preparer", "scripts/m336k6_prepare_karina_capsule.py"),
    ("persistent-capsule-verifier", "scripts/m336k6_verify_persistent_capsule.py"),
)
M336K7_ROUTE_COMPONENTS = M336K6_ROUTE_COMPONENTS + (
    ("frozen-contracts", "src/ai_brain/stage3/acquisition/m336k7_contracts.py"),
    ("current-final-request", "src/ai_brain/stage3/acquisition/m336k7_request.py"),
    ("current-freeze", "src/ai_brain/stage3/acquisition/m336k7_freeze.py"),
    ("current-final-cli", "scripts/m336k7_run_final_route.py"),
    ("current-request-builder", "scripts/m336k7_build_final_route_request.py"),
    ("frozen-contract-builder", "scripts/m336k7_build_frozen_contracts.py"),
    ("current-freeze-builder", "scripts/m336k7_materialize_f32.py"),
    ("frozen-contract-mutations", "scripts/m336k7_run_contract_mutations.py"),
)
M336K8_ROUTE_COMPONENTS = M336K7_ROUTE_COMPONENTS + (
    (
        "official-acquisition-binding",
        "src/ai_brain/stage3/acquisition/m336k10_binding.py",
    ),
    ("official-route-profiles", "src/ai_brain/stage3/acquisition/m336k9_profiles.py"),
    ("controller-admission", "src/ai_brain/stage3/acquisition/m336k9_admission.py"),
    (
        "profile-authorization",
        "src/ai_brain/stage3/acquisition/m336k9_authorization.py",
    ),
    ("source-domain-contracts", "src/ai_brain/stage3/acquisition/m336k8_contracts.py"),
    ("current-final-request", "src/ai_brain/stage3/acquisition/m336k8_request.py"),
    ("current-freeze", "src/ai_brain/stage3/acquisition/m336k8_freeze.py"),
    ("current-final-cli", "scripts/m336k8_run_final_route.py"),
    ("current-request-builder", "scripts/m336k8_build_final_route_request.py"),
    ("source-domain-builder", "scripts/m336k8_build_source_domain_contracts.py"),
    ("current-component-builder", "scripts/m336k8_build_component_bundle.py"),
    ("current-freeze-builder", "scripts/m336k8_materialize_f33.py"),
    ("source-domain-mutations", "scripts/m336k8_run_contract_mutations.py"),
    ("source-domain-schema", "schemas/m336k8_source_domain_contracts.schema.json"),
    ("official-profile-schema", "schemas/m336k9_official_route_profiles.schema.json"),
    ("official-profile-builder", "scripts/m336k9_build_profile_components.py"),
    ("controller-admission-mutations", "scripts/m336k9_run_admission_mutations.py"),
    ("official-acquisition-schema", "schemas/m336k10_acquisition_binding.schema.json"),
    ("official-acquisition-mutations", "scripts/m336k10_run_binding_mutations.py"),
    ("official-component-builder", "scripts/m336k10_build_component_bundle.py"),
    ("official-freeze-builder", "scripts/m336k10_materialize_f35.py"),
    ("official-final-cli", "scripts/m336k10_run_final_route.py"),
)
M336K11_ROUTE_COMPONENTS = M336K8_ROUTE_COMPONENTS + (
    (
        "hermetic-executable-binding",
        "src/ai_brain/stage3/acquisition/m336k11_execution.py",
    ),
    ("hermetic-component-builder", "scripts/m336k11_build_component_bundle.py"),
    ("hermetic-freeze-builder", "scripts/m336k11_materialize_f36.py"),
    (
        "hermetic-prospective-freeze-builder",
        "scripts/m336k11_materialize_prospective_freeze.py",
    ),
    ("hermetic-final-cli", "scripts/m336k11_run_final_route.py"),
)
M336K12_ROUTE_COMPONENTS = M336K11_ROUTE_COMPONENTS + (
    (
        "native-stage-dispatch",
        "src/ai_brain/stage3/acquisition/m336k12_dispatch.py",
    ),
    ("native-stage-freeze-builder", "scripts/m336k12_materialize_f37.py"),
    (
        "native-stage-prospective-freeze-builder",
        "scripts/m336k12_materialize_prospective_freeze.py",
    ),
    ("native-stage-mutations", "scripts/m336k12_run_dispatch_mutations.py"),
    ("native-stage-final-cli", "scripts/m336k12_run_final_route.py"),
)


def _namespace_values(
    namespace: str, profile_id: str | None = None
) -> tuple[str, tuple[tuple[str, str], ...]]:
    if profile_id is not None:
        profile = m336k_official_profile_registry().profile(profile_id)
        if profile.route_version.split(".", 1)[0] != namespace:
            raise M336K2ProtocolError("M336K route profile namespace changed")
        route_value = profile.route_version
    else:
        route_value = None
    if namespace == "m336k5":
        return route_value or M336K5_ROUTE_VERSION, M336K5_ROUTE_COMPONENTS
    if namespace == "m336k6":
        return route_value or M336K6_ROUTE_VERSION, M336K6_ROUTE_COMPONENTS
    if namespace == "m336k7":
        return route_value or M336K7_ROUTE_VERSION, M336K7_ROUTE_COMPONENTS
    if namespace == "m336k8":
        components = (
            M336K12_ROUTE_COMPONENTS
            if profile_id == "m336k8-final-v5"
            else M336K11_ROUTE_COMPONENTS
            if profile_id == "m336k8-final-v4"
            else M336K8_ROUTE_COMPONENTS
        )
        return route_value or M336K8_ROUTE_VERSION, components
    raise M336K2ProtocolError("M336K5 route registry namespace is invalid")


@dataclass(frozen=True)
class M336K5RouteComponent:
    component_id: M336K5RouteComponentId
    repository_path: str
    source_bytes_hash: str
    source_byte_count: int
    component_hash: str

    def canonical_object(self) -> dict:
        return {
            "component_id": self.component_id.canonical_object(),
            "repository_path": self.repository_path,
            "source_bytes_hash": self.source_bytes_hash,
            "source_byte_count": self.source_byte_count,
            "component_hash": self.component_hash,
        }


@dataclass(frozen=True)
class M336K5RouteRegistry:
    schema_version: int
    route_version: M336K5RouteVersion
    components: tuple[M336K5RouteComponent, ...]
    missing_component_count: int
    registry_hash: str

    def _body(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "route_version": self.route_version.canonical_object(),
            "components": tuple(item.canonical_object() for item in self.components),
            "missing_component_count": self.missing_component_count,
        }

    def canonical_object(self) -> dict:
        return {**self._body(), "registry_hash": self.registry_hash}


@dataclass(frozen=True)
class M336K5SchemaRegistry:
    schema_version: int
    route_version: M336K5RouteVersion
    stage_bindings: tuple[dict, ...]
    incompatible_edge_count: int
    registry_hash: str

    def _body(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "route_version": self.route_version.canonical_object(),
            "stage_bindings": self.stage_bindings,
            "incompatible_edge_count": self.incompatible_edge_count,
        }

    def canonical_object(self) -> dict:
        return {**self._body(), "registry_hash": self.registry_hash}


@dataclass(frozen=True)
class M336K5RouteManifest:
    schema_version: int
    route_version: M336K5RouteVersion
    route_registry_hash: str
    schema_registry_hash: str
    controller_component_id: M336K5RouteComponentId
    acquisition_component_id: M336K5RouteComponentId
    selector_component_id: M336K5RouteComponentId
    evaluator_component_id: M336K5RouteComponentId
    candidate_failure_isolation: bool
    unexpected_failure_is_global: bool
    count_neutral_acceptance: bool
    manifest_hash: str

    def _body(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "route_version": self.route_version.canonical_object(),
            "route_registry_hash": self.route_registry_hash,
            "schema_registry_hash": self.schema_registry_hash,
            "controller_component_id": self.controller_component_id.canonical_object(),
            "acquisition_component_id": self.acquisition_component_id.canonical_object(),
            "selector_component_id": self.selector_component_id.canonical_object(),
            "evaluator_component_id": self.evaluator_component_id.canonical_object(),
            "candidate_failure_isolation": self.candidate_failure_isolation,
            "unexpected_failure_is_global": self.unexpected_failure_is_global,
            "count_neutral_acceptance": self.count_neutral_acceptance,
        }

    def canonical_object(self) -> dict:
        return {**self._body(), "manifest_hash": self.manifest_hash}


def build_m336k5_schema_registry(
    namespace: str = "m336k5", *, profile_id: str | None = None
) -> M336K5SchemaRegistry:
    route_value, _components = _namespace_values(namespace, profile_id)
    route = M336K5RouteVersion(route_value)
    bindings = []
    for stage in M336K2_ROUTE_STAGES:
        body = {
            "schema_version": 1,
            "stage": stage,
            "request_identity_fields": (
                "protocol_run_id",
                "route_identity_bundle_hash",
                "execution_mode",
            ),
            "response_identity_fields": (
                "protocol_run_id",
                "route_identity_bundle_hash",
            ),
            "additional_properties": False,
        }
        bindings.append({**body, "binding_hash": content_hash(body)})
    body = {
        "schema_version": 1,
        "route_version": route.canonical_object(),
        "stage_bindings": tuple(bindings),
        "incompatible_edge_count": 0,
    }
    return M336K5SchemaRegistry(
        schema_version=1,
        route_version=route,
        stage_bindings=tuple(bindings),
        incompatible_edge_count=0,
        registry_hash=content_hash(body),
    )


def build_m336k5_route_registry(
    repository: Path, namespace: str = "m336k5", *, profile_id: str | None = None
) -> M336K5RouteRegistry:
    root = repository.resolve(strict=True)
    route_value, route_components = _namespace_values(namespace, profile_id)
    components = []
    missing = []
    for name, relative in route_components:
        path = root.joinpath(*relative.split("/"))
        if not path.is_file():
            missing.append(relative)
            continue
        component_id = M336K5RouteComponentId(f"{namespace}.route-component.{name}.v1")
        body = {
            "component_id": component_id.canonical_object(),
            "repository_path": relative,
            "source_bytes_hash": bytes_hash(path.read_bytes()),
            "source_byte_count": path.stat().st_size,
        }
        components.append(
            M336K5RouteComponent(
                component_id=component_id,
                repository_path=relative,
                source_bytes_hash=body["source_bytes_hash"],
                source_byte_count=body["source_byte_count"],
                component_hash=content_hash(body),
            )
        )
    body = {
        "schema_version": 1,
        "route_version": M336K5RouteVersion(route_value).canonical_object(),
        "components": tuple(item.canonical_object() for item in components),
        "missing_component_count": len(missing),
    }
    result = M336K5RouteRegistry(
        schema_version=1,
        route_version=M336K5RouteVersion(route_value),
        components=tuple(components),
        missing_component_count=len(missing),
        registry_hash=content_hash(body),
    )
    if missing:
        raise M336K2ProtocolError(
            f"M336K5 route component registry is incomplete: {len(missing)} missing"
        )
    return result


def build_m336k5_route_manifest(
    registry: M336K5RouteRegistry,
    schemas: M336K5SchemaRegistry,
) -> M336K5RouteManifest:
    if registry.route_version != schemas.route_version:
        raise M336K2ProtocolError("M336K5 route/schema version type binding changed")
    namespace = registry.route_version.value.split(".", 1)[0]
    values = {
        "schema_version": 1,
        "route_version": registry.route_version,
        "route_registry_hash": registry.registry_hash,
        "schema_registry_hash": schemas.registry_hash,
        "controller_component_id": M336K5RouteComponentId(
            f"{namespace}.route-component.typed-controller.v1"
        ),
        "acquisition_component_id": M336K5RouteComponentId(
            f"{namespace}.route-component.acquisition.v1"
        ),
        "selector_component_id": M336K5RouteComponentId(
            f"{namespace}.route-component.selector.v1"
        ),
        "evaluator_component_id": M336K5RouteComponentId(
            f"{namespace}.route-component.evaluator.v1"
        ),
        "candidate_failure_isolation": True,
        "unexpected_failure_is_global": True,
        "count_neutral_acceptance": True,
    }
    temporary = M336K5RouteManifest(**values, manifest_hash="0" * 64)
    return M336K5RouteManifest(**values, manifest_hash=content_hash(temporary._body()))
