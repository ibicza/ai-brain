"""Closed route and schema registries for the M-33.6k.4 recovery route."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336k2_controller import M336K2_ROUTE_STAGES
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k4_identity import (
    M336K4_ROUTE_VERSION,
    M336K4RouteComponentId,
    M336K4RouteVersion,
)

M336K4_ROUTE_COMPONENTS = (
    ("typed-identity", "src/ai_brain/stage3/acquisition/m336k4_identity.py"),
    ("route-registry", "src/ai_brain/stage3/acquisition/m336k4_registry.py"),
    ("final-request", "src/ai_brain/stage3/acquisition/m336k4_request.py"),
    ("typed-authorization", "src/ai_brain/stage3/acquisition/m336k4_authorization.py"),
    ("typed-freeze", "src/ai_brain/stage3/acquisition/m336k4_freeze.py"),
    ("typed-controller", "src/ai_brain/stage3/acquisition/m336k4_controller.py"),
    ("final-cli", "scripts/m336k4_run_final_route.py"),
    ("request-builder-cli", "scripts/m336k4_build_final_route_request.py"),
    ("component-builder-cli", "scripts/m336k4_build_component_bundle.py"),
    ("disposable-qualifier", "scripts/m336k4_qualify_disposable_protocol.py"),
    ("exact-quality", "scripts/m336k4_run_exact_quality.py"),
    ("identity-mutations", "scripts/m336k4_run_identity_mutations.py"),
    ("karina-capsule-preparer", "scripts/m336k4_prepare_karina_capsule.py"),
    (
        "karina-capsule-metadata",
        "scripts/m336k4_export_karina_capsule_metadata.py",
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


@dataclass(frozen=True)
class M336K4RouteComponent:
    component_id: M336K4RouteComponentId
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
class M336K4RouteRegistry:
    schema_version: int
    route_version: M336K4RouteVersion
    components: tuple[M336K4RouteComponent, ...]
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
class M336K4SchemaRegistry:
    schema_version: int
    route_version: M336K4RouteVersion
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
class M336K4RouteManifest:
    schema_version: int
    route_version: M336K4RouteVersion
    route_registry_hash: str
    schema_registry_hash: str
    controller_component_id: M336K4RouteComponentId
    acquisition_component_id: M336K4RouteComponentId
    selector_component_id: M336K4RouteComponentId
    evaluator_component_id: M336K4RouteComponentId
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


def build_m336k4_schema_registry() -> M336K4SchemaRegistry:
    route = M336K4RouteVersion(M336K4_ROUTE_VERSION)
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
    return M336K4SchemaRegistry(
        schema_version=1,
        route_version=route,
        stage_bindings=tuple(bindings),
        incompatible_edge_count=0,
        registry_hash=content_hash(body),
    )


def build_m336k4_route_registry(repository: Path) -> M336K4RouteRegistry:
    root = repository.resolve(strict=True)
    components = []
    missing = []
    for name, relative in M336K4_ROUTE_COMPONENTS:
        path = root.joinpath(*relative.split("/"))
        if not path.is_file():
            missing.append(relative)
            continue
        component_id = M336K4RouteComponentId(f"m336k4.route-component.{name}.v1")
        body = {
            "component_id": component_id.canonical_object(),
            "repository_path": relative,
            "source_bytes_hash": bytes_hash(path.read_bytes()),
            "source_byte_count": path.stat().st_size,
        }
        components.append(
            M336K4RouteComponent(
                component_id=component_id,
                repository_path=relative,
                source_bytes_hash=body["source_bytes_hash"],
                source_byte_count=body["source_byte_count"],
                component_hash=content_hash(body),
            )
        )
    body = {
        "schema_version": 1,
        "route_version": M336K4RouteVersion(M336K4_ROUTE_VERSION).canonical_object(),
        "components": tuple(item.canonical_object() for item in components),
        "missing_component_count": len(missing),
    }
    result = M336K4RouteRegistry(
        schema_version=1,
        route_version=M336K4RouteVersion(M336K4_ROUTE_VERSION),
        components=tuple(components),
        missing_component_count=len(missing),
        registry_hash=content_hash(body),
    )
    if missing:
        raise M336K2ProtocolError(
            f"M336K4 route component registry is incomplete: {len(missing)} missing"
        )
    return result


def build_m336k4_route_manifest(
    registry: M336K4RouteRegistry,
    schemas: M336K4SchemaRegistry,
) -> M336K4RouteManifest:
    if registry.route_version != schemas.route_version:
        raise M336K2ProtocolError("M336K4 route/schema version type binding changed")
    values = {
        "schema_version": 1,
        "route_version": registry.route_version,
        "route_registry_hash": registry.registry_hash,
        "schema_registry_hash": schemas.registry_hash,
        "controller_component_id": M336K4RouteComponentId(
            "m336k4.route-component.typed-controller.v1"
        ),
        "acquisition_component_id": M336K4RouteComponentId(
            "m336k4.route-component.acquisition.v1"
        ),
        "selector_component_id": M336K4RouteComponentId(
            "m336k4.route-component.selector.v1"
        ),
        "evaluator_component_id": M336K4RouteComponentId(
            "m336k4.route-component.evaluator.v1"
        ),
        "candidate_failure_isolation": True,
        "unexpected_failure_is_global": True,
        "count_neutral_acceptance": True,
    }
    temporary = M336K4RouteManifest(**values, manifest_hash="0" * 64)
    return M336K4RouteManifest(**values, manifest_hash=content_hash(temporary._body()))
