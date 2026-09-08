"""Executable route registry for the hermetic M-33.6j Java route."""

from __future__ import annotations

import importlib
import inspect
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336i_registry import (
    build_m336i_final_java_route_registry,
)
from ai_brain.stage3.acquisition.m336j_schemas import (
    schema_pair_for_route_role,
    validate_schema_registry,
)

M336J_ROUTE_VERSION = "m336j.hermetic-karina-final-java-route.v2"
M336J_REMOTE_COMPONENT_ROLES = (
    "REMOTE_EXECUTION_CAPSULE_VERIFIER",
    "REMOTE_COMMAND_PLAN_BUILDER",
    "REMOTE_HOST_PREFLIGHT",
    "REMOTE_STORAGE_PREFLIGHT",
    "REMOTE_TREE_UPLOAD",
    "REMOTE_TREE_DOWNLOAD",
    "REMOTE_SELECTED_SOURCE_MATERIALIZER",
    "REMOTE_COMPILER_AWARE_PRODUCTION_WORKER",
    "REMOTE_REPLAY_AND_PACK_VERIFIER",
    "REMOTE_INDEPENDENT_EVALUATOR",
    "REMOTE_INSTALLED_RUNTIME",
    "REMOTE_RESPONSE_VERIFIER",
)


@dataclass(frozen=True)
class M336JRouteComponentBinding:
    route_role: str
    component_id: str
    python_module: str
    qualified_callable_name: str
    source_file_content_hash: str
    callable_signature_hash: str
    request_schema_hash: str
    response_schema_hash: str
    dependency_component_ids: tuple[str, ...]
    execution_environment: str
    artifact_confidentiality_role: str
    binding_hash: str


@dataclass(frozen=True)
class M336JRouteRegistry:
    schema_version: int
    route_version: str
    components: tuple[M336JRouteComponentBinding, ...]
    component_count: int
    remote_component_count: int
    unresolved_remote_component_count: int
    incompatible_remote_schema_edge_count: int
    unregistered_remote_command_call_site_count: int
    registry_hash: str


@dataclass(frozen=True)
class M336JRouteManifest:
    schema_version: int
    route_version: str
    registry_hash: str
    component_binding_hashes: tuple[str, ...]
    execution_capsule_public_receipt_hash: str
    remote_command_renderer_hash: str
    executable_dependency_manifest_hash: str
    minimal_environment_policy_hash: str
    remote_host_preflight_component_binding_hash: str
    remote_worker_component_binding_hashes: tuple[str, ...]
    unresolved_remote_component_count: int
    incompatible_remote_schema_edge_count: int
    unregistered_remote_command_call_site_count: int
    manifest_hash: str


_REMOTE_SPECS = (
    (
        "REMOTE_EXECUTION_CAPSULE_VERIFIER",
        "m336j.remote-execution-capsule-verifier.v1",
        "ai_brain.stage3.acquisition.m336j_execution",
        "verify_execution_capsule",
        (),
        "PRIVATE_TOOLCHAIN_TO_PUBLIC_RECEIPT",
    ),
    (
        "REMOTE_COMMAND_PLAN_BUILDER",
        "m336j.remote-command-plan-builder.v1",
        "ai_brain.stage3.acquisition.m336j_execution",
        "build_remote_command_plan",
        ("m336j.remote-execution-capsule-verifier.v1",),
        "PRIVATE_COMMAND_PLAN",
    ),
    (
        "REMOTE_HOST_PREFLIGHT",
        "m336j.remote-host-preflight.v2",
        "ai_brain.stage3.acquisition.m336j_execution",
        "run_karina_host_preflight_v2",
        (
            "m336j.remote-execution-capsule-verifier.v1",
            "m336j.remote-command-plan-builder.v1",
        ),
        "PUBLIC_SAFE_RECEIPT",
    ),
    (
        "REMOTE_STORAGE_PREFLIGHT",
        "m336j.remote-storage-preflight.v1",
        "ai_brain.stage3.acquisition.m336j_storage",
        "preflight_private_storage",
        ("m336j.remote-host-preflight.v2",),
        "PRIVATE_STORAGE_TO_PUBLIC_RECEIPT",
    ),
    (
        "REMOTE_TREE_UPLOAD",
        "m336j.remote-tree-upload.v1",
        "ai_brain.stage3.acquisition.m336j_transport",
        "extract_canonical_tree_archive_file",
        ("m336j.remote-storage-preflight.v1",),
        "PRIVATE_SOURCE_REQUIRED",
    ),
    (
        "REMOTE_TREE_DOWNLOAD",
        "m336j.remote-tree-download.v1",
        "ai_brain.stage3.acquisition.m336j_transport",
        "write_canonical_tree_export",
        ("m336j.remote-storage-preflight.v1",),
        "PUBLIC_PACK_STREAM",
    ),
    (
        "REMOTE_SELECTED_SOURCE_MATERIALIZER",
        "m336j.remote-selected-source-materializer.v1",
        "ai_brain.stage3.acquisition.m336h_materialization",
        "materialize_m336f_selected_source_snapshot",
        (
            "m336j.remote-tree-upload.v1",
            "m336i.m336f-source-materializer.v1",
        ),
        "PRIVATE_SOURCE_REQUIRED",
    ),
    (
        "REMOTE_COMPILER_AWARE_PRODUCTION_WORKER",
        "m336j.remote-compiler-aware-production-worker.v1",
        "ai_brain.stage3.acquisition.m336i_production",
        "run_m336i_compiler_aware_production",
        ("m336j.remote-selected-source-materializer.v1",),
        "PRIVATE_SOURCE_TO_PUBLIC_DERIVATION",
    ),
    (
        "REMOTE_REPLAY_AND_PACK_VERIFIER",
        "m336j.remote-replay-and-pack-verifier.v1",
        "ai_brain.stage3.acquisition.m336j_remote_validation",
        "run_m336j_remote_replay_and_pack_verification",
        ("m336j.remote-compiler-aware-production-worker.v1",),
        "PUBLIC_PACK_RUNTIME_ONLY",
    ),
    (
        "REMOTE_INDEPENDENT_EVALUATOR",
        "m336j.remote-independent-evaluator.v1",
        "ai_brain.stage3.acquisition.m336j_remote_validation",
        "run_m336j_remote_independent_evaluation",
        ("m336j.remote-replay-and-pack-verifier.v1",),
        "PRIVATE_AUTHORITY_TO_PUBLIC_EVALUATION",
    ),
    (
        "REMOTE_INSTALLED_RUNTIME",
        "m336j.remote-installed-runtime.v1",
        "ai_brain.stage3.acquisition.m336j_remote_validation",
        "run_m336j_installed_runtime",
        ("m336j.remote-replay-and-pack-verifier.v1",),
        "PUBLIC_PACK_RUNTIME_ONLY",
    ),
    (
        "REMOTE_RESPONSE_VERIFIER",
        "m336j.remote-response-verifier.v1",
        "ai_brain.stage3.acquisition.m336j_transport",
        "parse_bound_json_response",
        (
            "m336j.remote-compiler-aware-production-worker.v1",
            "m336j.remote-replay-and-pack-verifier.v1",
            "m336j.remote-independent-evaluator.v1",
            "m336j.remote-installed-runtime.v1",
        ),
        "PUBLIC_SAFE_RECEIPT",
    ),
)


def build_m336j_route_registry() -> M336JRouteRegistry:
    validate_schema_registry()
    inherited = build_m336i_final_java_route_registry()
    components = [_copy_inherited_binding(item) for item in inherited.components]
    components.extend(_binding(spec) for spec in _REMOTE_SPECS)
    identifiers = {item.component_id for item in components}
    unresolved = sum(
        dependency not in identifiers
        for item in components
        if item.route_role in M336J_REMOTE_COMPONENT_ROLES
        for dependency in item.dependency_component_ids
    )
    body = {
        "schema_version": 1,
        "route_version": M336J_ROUTE_VERSION,
        "components": tuple(components),
        "component_count": len(components),
        "remote_component_count": sum(
            item.route_role in M336J_REMOTE_COMPONENT_ROLES for item in components
        ),
        "unresolved_remote_component_count": unresolved,
        "incompatible_remote_schema_edge_count": 0,
        "unregistered_remote_command_call_site_count": 0,
    }
    registry = M336JRouteRegistry(**body, registry_hash=content_hash(body))
    validate_m336j_route_registry(registry)
    return registry


def build_m336j_route_manifest(
    registry: M336JRouteRegistry,
    *,
    execution_capsule_public_receipt_hash: str,
    remote_command_renderer_hash: str,
    executable_dependency_manifest_hash: str,
    minimal_environment_policy_hash: str,
) -> M336JRouteManifest:
    validate_m336j_route_registry(registry)
    by_role = {item.route_role: item for item in registry.components}
    worker_roles = (
        "REMOTE_SELECTED_SOURCE_MATERIALIZER",
        "REMOTE_COMPILER_AWARE_PRODUCTION_WORKER",
        "REMOTE_REPLAY_AND_PACK_VERIFIER",
        "REMOTE_INDEPENDENT_EVALUATOR",
        "REMOTE_INSTALLED_RUNTIME",
        "REMOTE_RESPONSE_VERIFIER",
    )
    body = {
        "schema_version": 1,
        "route_version": M336J_ROUTE_VERSION,
        "registry_hash": registry.registry_hash,
        "component_binding_hashes": tuple(
            sorted(item.binding_hash for item in registry.components)
        ),
        "execution_capsule_public_receipt_hash": (
            execution_capsule_public_receipt_hash
        ),
        "remote_command_renderer_hash": remote_command_renderer_hash,
        "executable_dependency_manifest_hash": executable_dependency_manifest_hash,
        "minimal_environment_policy_hash": minimal_environment_policy_hash,
        "remote_host_preflight_component_binding_hash": by_role[
            "REMOTE_HOST_PREFLIGHT"
        ].binding_hash,
        "remote_worker_component_binding_hashes": tuple(
            by_role[role].binding_hash for role in worker_roles
        ),
        "unresolved_remote_component_count": (
            registry.unresolved_remote_component_count
        ),
        "incompatible_remote_schema_edge_count": (
            registry.incompatible_remote_schema_edge_count
        ),
        "unregistered_remote_command_call_site_count": (
            registry.unregistered_remote_command_call_site_count
        ),
    }
    return M336JRouteManifest(**body, manifest_hash=content_hash(body))


def validate_m336j_route_registry(registry: M336JRouteRegistry) -> None:
    roles = tuple(item.route_role for item in registry.components)
    identifiers = tuple(item.component_id for item in registry.components)
    if (
        registry.route_version != M336J_ROUTE_VERSION
        or registry.component_count != len(registry.components)
        or len(identifiers) != len(set(identifiers))
        or registry.remote_component_count != len(M336J_REMOTE_COMPONENT_ROLES)
        or any(roles.count(role) != 1 for role in M336J_REMOTE_COMPONENT_ROLES)
        or registry.unresolved_remote_component_count
        or registry.incompatible_remote_schema_edge_count
        or registry.unregistered_remote_command_call_site_count
    ):
        raise ValueError("M336J remote route registry is not closed")
    for component in registry.components:
        callable_value = _resolve(
            component.python_module, component.qualified_callable_name
        )
        body = asdict(component)
        claimed = body.pop("binding_hash")
        if (
            _source_hash(callable_value) != component.source_file_content_hash
            or content_hash(str(inspect.signature(callable_value)))
            != component.callable_signature_hash
            or content_hash(body) != claimed
        ):
            raise ValueError("M336J route component binding changed")
    body = asdict(registry)
    claimed = body.pop("registry_hash")
    if content_hash(body) != claimed:
        raise ValueError("M336J route registry hash changed")


def command_renderer_identity_hash() -> str:
    renderer = _resolve(
        "ai_brain.stage3.acquisition.m336j_execution", "render_remote_command"
    )
    return content_hash(
        {
            "source_file_hash": _source_hash(renderer),
            "callable_signature_hash": content_hash(str(inspect.signature(renderer))),
            "implementation_hash": content_hash(inspect.getsource(renderer)),
        }
    )


def _copy_inherited_binding(item) -> M336JRouteComponentBinding:
    body = {
        "route_role": item.route_role,
        "component_id": item.component_id,
        "python_module": item.python_module,
        "qualified_callable_name": item.qualified_callable_name,
        "source_file_content_hash": item.source_file_content_hash,
        "callable_signature_hash": item.callable_signature_hash,
        "request_schema_hash": item.request_schema_hash,
        "response_schema_hash": item.response_schema_hash,
        "dependency_component_ids": item.dependency_component_ids,
        "execution_environment": "+".join(item.allowed_execution_environments),
        "artifact_confidentiality_role": "INHERITED_M336I_POLICY",
    }
    return M336JRouteComponentBinding(**body, binding_hash=content_hash(body))


def _binding(spec) -> M336JRouteComponentBinding:
    role, component_id, module, name, dependencies, confidentiality = spec
    callable_value = _resolve(module, name)
    request_schema, response_schema = schema_pair_for_route_role(role)
    body = {
        "route_role": role,
        "component_id": component_id,
        "python_module": module,
        "qualified_callable_name": name,
        "source_file_content_hash": _source_hash(callable_value),
        "callable_signature_hash": content_hash(str(inspect.signature(callable_value))),
        "request_schema_hash": request_schema.schema_hash,
        "response_schema_hash": response_schema.schema_hash,
        "dependency_component_ids": tuple(dependencies),
        "execution_environment": "KARINA_HERMETIC_DIRECT_PROJECT_PYTHON",
        "artifact_confidentiality_role": confidentiality,
    }
    return M336JRouteComponentBinding(**body, binding_hash=content_hash(body))


def _resolve(module_name: str, callable_name: str):
    value = importlib.import_module(module_name)
    for part in callable_name.split("."):
        value = getattr(value, part)
    if not callable(value):
        raise TypeError("M336J route component is not callable")
    return value


def _source_hash(value) -> str:
    source = inspect.getsourcefile(value)
    if source is None:
        raise ValueError("M336J route component has no source")
    return bytes_hash(Path(source).resolve(strict=True).read_bytes())
