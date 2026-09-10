"""Closed source/component registry for the M-33.6k.2 final route."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336k2_controller import (
    M336K2SchemaRegistry,
    build_m336k2_schema_registry,
)
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError

M336K2_ROUTE_COMPONENTS = (
    ("PROTOCOL", "src/ai_brain/stage3/acquisition/m336k2_protocol.py"),
    ("CONTROLLER", "src/ai_brain/stage3/acquisition/m336k2_controller.py"),
    ("ACQUISITION", "src/ai_brain/stage3/acquisition/m336k2_acquisition.py"),
    ("READINESS", "src/ai_brain/stage3/acquisition/m336k2_readiness.py"),
    ("PUBLICATION", "src/ai_brain/stage3/acquisition/m336k2_publication.py"),
    ("REGISTRY", "src/ai_brain/stage3/acquisition/m336k2_registry.py"),
    ("FREEZE", "src/ai_brain/stage3/acquisition/m336k2_freeze.py"),
    ("EXECUTION", "src/ai_brain/stage3/acquisition/m336k2_execution.py"),
    ("NATIVE_ROUTE", "src/ai_brain/stage3/acquisition/m336k2_stage.py"),
    ("ARCHIVE_INSPECTOR", "src/ai_brain/stage3/acquisition/m336k_archive.py"),
    ("CANDIDATE_ISOLATION", "src/ai_brain/stage3/acquisition/m336k_acquisition.py"),
    (
        "COMPILATION_CLOSURE",
        "src/ai_brain/stage3/acquisition/m336f_compilation_closure.py",
    ),
    ("SELECTOR", "src/ai_brain/stage3/acquisition/m336f_selection.py"),
    ("COMPILER_PRODUCTION", "src/ai_brain/stage3/acquisition/m336i_production.py"),
    ("INDEPENDENT_EVALUATION", "src/ai_brain/stage3/acquisition/m336i_evaluation.py"),
    ("EVALUATOR_LEDGER", "src/ai_brain/stage3/acquisition/m336j_evaluator_v2.py"),
    ("REMOTE_CAPSULE", "src/ai_brain/stage3/acquisition/m336j_execution.py"),
    ("REMOTE_TRANSPORT", "src/ai_brain/stage3/acquisition/m336j_transport.py"),
    ("FINAL_CLI", "scripts/m336k2_run_final_route.py"),
    ("NATIVE_STAGE_WORKER", "scripts/m336k2_run_stage.py"),
    ("READINESS_CLI", "scripts/m336k2_build_readiness.py"),
    ("FREEZE_CLI", "scripts/m336k2_build_f28.py"),
    ("F28_ATTESTER", "scripts/m336k2_attest_f28.py"),
    ("H28_PUBLISHER", "scripts/m336k2_publish_h28.py"),
    ("E28_PUBLISHER", "scripts/m336k2_publish_e28.py"),
    ("COMMIT_VERIFIER", "scripts/m336k2_verify_commits.py"),
    ("METADATA_POOL_BUILDER", "scripts/m336k2_build_metadata_pool.py"),
    ("COMPONENT_BUNDLE_BUILDER", "scripts/m336k2_build_component_bundle.py"),
    ("DISPOSABLE_PROTOCOL", "scripts/m336k2_qualify_disposable_protocol.py"),
    ("DISPOSABLE_POOL_BUILDER", "scripts/m336k2_build_disposable_pool.py"),
)


@dataclass(frozen=True)
class M336K2RouteComponent:
    role: str
    repository_path: str
    source_bytes_hash: str
    source_byte_count: int
    component_hash: str


@dataclass(frozen=True)
class M336K2RouteRegistry:
    schema_version: int
    route_version: str
    components: tuple[M336K2RouteComponent, ...]
    native_h28_publisher_registered: bool
    native_e28_publisher_registered: bool
    final_commit_verifier_registered: bool
    missing_component_count: int
    registry_hash: str


@dataclass(frozen=True)
class M336K2RouteManifest:
    schema_version: int
    route_version: str
    route_registry_hash: str
    schema_registry_hash: str
    executable_dependency_manifest_hash: str
    python_environment_manifest_hash: str
    command_renderer_hash: str
    minimal_environment_policy_hash: str
    controller_role: str
    acquisition_role: str
    h28_publisher_role: str
    e28_publisher_role: str
    commit_verifier_role: str
    candidate_failure_isolation: bool
    unexpected_failure_is_global: bool
    count_neutral_acceptance: bool
    manifest_hash: str


def build_m336k2_route_registry(repository: Path) -> M336K2RouteRegistry:
    root = repository.resolve(strict=True)
    components = []
    missing = []
    for role, relative in M336K2_ROUTE_COMPONENTS:
        path = root.joinpath(*relative.split("/"))
        if not path.is_file():
            missing.append(relative)
            continue
        body = {
            "role": role,
            "repository_path": relative,
            "source_bytes_hash": bytes_hash(path.read_bytes()),
            "source_byte_count": path.stat().st_size,
        }
        components.append(
            M336K2RouteComponent(**body, component_hash=content_hash(body))
        )
    roles = {item.role for item in components}
    body = {
        "schema_version": 1,
        "route_version": "m336k2.candidate-isolated-java-final-route.v1",
        "components": tuple(components),
        "native_h28_publisher_registered": "H28_PUBLISHER" in roles,
        "native_e28_publisher_registered": "E28_PUBLISHER" in roles,
        "final_commit_verifier_registered": "COMMIT_VERIFIER" in roles,
        "missing_component_count": len(missing),
    }
    result = M336K2RouteRegistry(**body, registry_hash=content_hash(body))
    if (
        missing
        or not result.native_h28_publisher_registered
        or not result.native_e28_publisher_registered
        or not result.final_commit_verifier_registered
    ):
        raise M336K2ProtocolError(
            f"M336K2 route component registry is incomplete: {len(missing)} missing"
        )
    return result


def build_m336k2_route_manifest(
    *,
    registry: M336K2RouteRegistry,
    schemas: M336K2SchemaRegistry | None = None,
    executable_dependency_manifest_hash: str,
    python_environment_manifest_hash: str,
    command_renderer_hash: str,
    minimal_environment_policy_hash: str,
) -> M336K2RouteManifest:
    schemas = schemas or build_m336k2_schema_registry()
    hashes = (
        registry.registry_hash,
        schemas.registry_hash,
        executable_dependency_manifest_hash,
        python_environment_manifest_hash,
        command_renderer_hash,
        minimal_environment_policy_hash,
    )
    if any(len(item) != 64 for item in hashes):
        raise M336K2ProtocolError("M336K2 route manifest hash binding is invalid")
    body = {
        "schema_version": 1,
        "route_version": registry.route_version,
        "route_registry_hash": registry.registry_hash,
        "schema_registry_hash": schemas.registry_hash,
        "executable_dependency_manifest_hash": executable_dependency_manifest_hash,
        "python_environment_manifest_hash": python_environment_manifest_hash,
        "command_renderer_hash": command_renderer_hash,
        "minimal_environment_policy_hash": minimal_environment_policy_hash,
        "controller_role": "CONTROLLER",
        "acquisition_role": "ACQUISITION",
        "h28_publisher_role": "H28_PUBLISHER",
        "e28_publisher_role": "E28_PUBLISHER",
        "commit_verifier_role": "COMMIT_VERIFIER",
        "candidate_failure_isolation": True,
        "unexpected_failure_is_global": True,
        "count_neutral_acceptance": True,
    }
    return M336K2RouteManifest(**body, manifest_hash=content_hash(body))
