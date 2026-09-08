"""Executable registry for the authorized M-33.6i final Java route."""

from __future__ import annotations

import importlib
import inspect
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336f_selection import M336F_SELECTOR_VERSION

M336I_ROUTE_VERSION = "m336i.authorized-final-java-route.v1"
M336I_SELECTOR_COMPONENT_ID = "m336i.m336f-compilation-closure-selector.v1"
M336I_SELECTOR_SEED = "m336i-final-java-freeze-v8-180"


@dataclass(frozen=True)
class M336IRouteComponentBinding:
    route_role: str
    component_id: str
    python_module: str
    qualified_callable_name: str
    source_file_content_hash: str
    callable_signature_hash: str
    request_schema_hash: str
    response_schema_hash: str
    allowed_execution_environments: tuple[str, ...]
    dependency_component_ids: tuple[str, ...]
    binding_hash: str


@dataclass(frozen=True)
class M336IRouteRegistry:
    schema_version: int
    route_version: str
    selector_component_id: str
    selector_algorithm_version: str
    selector_seed_hash: str
    components: tuple[M336IRouteComponentBinding, ...]
    component_count: int
    unresolved_component_count: int
    ambiguous_component_count: int
    dependency_cycle_count: int
    registry_hash: str


@dataclass(frozen=True)
class M336IRouteEdge:
    producer_component_id: str
    consumer_component_id: str
    producer_role: str
    consumer_role: str
    schema_hash: str
    edge_hash: str


@dataclass(frozen=True)
class M336IRouteManifest:
    schema_version: int
    route_version: str
    registry_hash: str
    selector_component_id: str
    selector_algorithm_version: str
    selector_seed_hash: str
    component_binding_hashes: tuple[str, ...]
    edges: tuple[M336IRouteEdge, ...]
    edge_count: int
    incompatible_edge_count: int
    unresolved_callable_count: int
    refusal_guard_registered_as_provider: bool
    manifest_hash: str


_SPECS = (
    (
        "METADATA_POOL_LOADER",
        "m336i.metadata-pool-loader.v1",
        "ai_brain.stage3.acquisition.m336i_acquisition",
        "validate_m336i_candidate_pool",
        (),
        ("WINDOWS", "KARINA"),
    ),
    (
        "FINAL_ACQUISITION_AUTHORIZATION_GUARD",
        "m336i.final-acquisition-authorization-guard.v1",
        "ai_brain.stage3.acquisition.m336i_acquisition",
        "verify_m336i_final_acquisition_authorization",
        (),
        ("WINDOWS", "KARINA"),
    ),
    (
        "FINAL_ACQUISITION_LEDGER",
        "m336i.final-acquisition-ledger.v1",
        "ai_brain.stage3.acquisition.m336i_acquisition",
        "M336IFinalAcquisitionLedger",
        (),
        ("WINDOWS",),
    ),
    (
        "FINAL_ACQUISITION_PROVIDER",
        "m336i.frozen-final-acquisition-provider.v1",
        "ai_brain.stage3.acquisition.m336i_acquisition",
        "run_m336i_frozen_final_acquisition",
        (
            "m336i.metadata-pool-loader.v1",
            "m336i.final-acquisition-authorization-guard.v1",
            "m336i.final-acquisition-ledger.v1",
        ),
        ("WINDOWS",),
    ),
    (
        "PERSISTENT_ROUTE_STATE_LEDGER",
        "m336i.route-state-ledger.v1",
        "ai_brain.stage3.acquisition.m336i_route",
        "M336IRouteStateLedger",
        (),
        ("WINDOWS", "KARINA"),
    ),
    (
        "AUTHORITY_VERIFIER",
        "m336i.authority-verifier.v1",
        "ai_brain.stage3.acquisition.m336e_authority",
        "load_m336e_authority_registry",
        ("m336i.frozen-final-acquisition-provider.v1",),
        ("WINDOWS", "KARINA"),
    ),
    (
        "SOURCE_ENTRY_BINDING_BUILDER",
        "m336i.source-entry-binding-builder.v1",
        "ai_brain.stage3.acquisition.m336e_identity",
        "build_source_entry_binding_manifest",
        ("m336i.authority-verifier.v1",),
        ("WINDOWS", "KARINA"),
    ),
    (
        "SELECTABILITY_CENSUS_BUILDER",
        "m336i.selectability-census-builder.v1",
        "ai_brain.stage3.acquisition.m336e_selectability",
        "build_selectable_source_census",
        ("m336i.source-entry-binding-builder.v1",),
        ("WINDOWS", "KARINA"),
    ),
    (
        "COMPILATION_CLOSURE_BUILDER",
        "m336i.compilation-closure-builder.v1",
        "ai_brain.stage3.acquisition.m336f_compilation_closure",
        "build_java_compilation_closure_manifest",
        ("m336i.selectability-census-builder.v1",),
        ("WINDOWS", "KARINA"),
    ),
    (
        "COMPILATION_CLOSURE_FEASIBILITY_PROVER",
        "m336i.compilation-closure-feasibility.v1",
        "ai_brain.stage3.acquisition.m336f_compilation_closure",
        "prove_java_compilation_closure_feasibility",
        ("m336i.compilation-closure-builder.v1",),
        ("WINDOWS", "KARINA"),
    ),
    (
        "COMPILATION_CLOSURE_SELECTOR",
        M336I_SELECTOR_COMPONENT_ID,
        "ai_brain.stage3.acquisition.m336f_selection",
        "select_compilation_closed_sources_once",
        (
            "m336i.compilation-closure-feasibility.v1",
            "m336i.source-entry-binding-builder.v1",
        ),
        ("WINDOWS",),
    ),
    (
        "M336F_SELECTED_SOURCE_MATERIALIZER",
        "m336i.m336f-source-materializer.v1",
        "ai_brain.stage3.acquisition.m336h_materialization",
        "materialize_m336f_selected_source_snapshot",
        (M336I_SELECTOR_COMPONENT_ID,),
        ("WINDOWS", "KARINA"),
    ),
    (
        "COMPILER_AWARE_PRODUCTION",
        "m336i.compiler-aware-production.v1",
        "ai_brain.stage3.acquisition.m336i_production",
        "run_m336i_compiler_aware_production",
        ("m336i.m336f-source-materializer.v1",),
        ("WINDOWS", "KARINA"),
    ),
    (
        "PUBLIC_PACK_VERIFIER",
        "m336i.public-pack-verifier.v1",
        "ai_brain.stage3.acquisition.m336g_publication",
        "verify_java_public_candidate_pack",
        ("m336i.compiler-aware-production.v1",),
        ("WINDOWS", "KARINA"),
    ),
    (
        "SEALED_SOURCE_REPLAY",
        "m336i.sealed-source-replay.v1",
        "ai_brain.stage3.acquisition.m336g_replay",
        "run_sealed_java_production_replay",
        ("m336i.public-pack-verifier.v1",),
        ("WINDOWS", "KARINA"),
    ),
    (
        "PRODUCTION_SEAL",
        "m336i.production-seal.v1",
        "ai_brain.stage3.acquisition.m336i_production",
        "build_m336i_production_seal",
        (
            "m336i.compiler-aware-production.v1",
            "m336i.public-pack-verifier.v1",
            "m336i.sealed-source-replay.v1",
        ),
        ("WINDOWS", "KARINA"),
    ),
    (
        "INDEPENDENT_EVALUATOR",
        "m336i.independent-evaluator.v1",
        "ai_brain.stage3.acquisition.m336i_evaluation",
        "run_m336i_independent_java_evaluation",
        ("m336i.production-seal.v1",),
        ("WINDOWS",),
    ),
    (
        "PUBLIC_STAGING_VALIDATOR",
        "m336i.public-staging-validator.v1",
        "ai_brain.stage3.acquisition.m336g_staging",
        "validate_public_staging",
        ("m336i.independent-evaluator.v1",),
        ("WINDOWS",),
    ),
    (
        "SOURCE_LEAK_SCANNER",
        "m336i.source-leak-scanner.v1",
        "ai_brain.stage3.acquisition.m336d_leak_scan",
        "scan_fresh_source_leaks",
        ("m336i.public-staging-validator.v1",),
        ("WINDOWS",),
    ),
)


def build_m336i_final_java_route_registry() -> M336IRouteRegistry:
    components = tuple(_binding(spec) for spec in _SPECS)
    ids = tuple(item.component_id for item in components)
    unresolved = sum(
        dependency not in ids
        for component in components
        for dependency in component.dependency_component_ids
    )
    body = {
        "schema_version": 1,
        "route_version": M336I_ROUTE_VERSION,
        "selector_component_id": M336I_SELECTOR_COMPONENT_ID,
        "selector_algorithm_version": M336F_SELECTOR_VERSION,
        "selector_seed_hash": content_hash(M336I_SELECTOR_SEED),
        "components": components,
        "component_count": len(components),
        "unresolved_component_count": unresolved,
        "ambiguous_component_count": len(ids) - len(set(ids)),
        "dependency_cycle_count": _cycle_count(components) if not unresolved else 1,
    }
    registry = M336IRouteRegistry(**body, registry_hash=content_hash(body))
    validate_m336i_route_registry(registry)
    return registry


def build_m336i_final_java_route_manifest(
    registry: M336IRouteRegistry,
) -> M336IRouteManifest:
    validate_m336i_route_registry(registry)
    by_id = {item.component_id: item for item in registry.components}
    edges = []
    for consumer in registry.components:
        for dependency in consumer.dependency_component_ids:
            producer = by_id[dependency]
            body = {
                "producer_component_id": producer.component_id,
                "consumer_component_id": consumer.component_id,
                "producer_role": producer.route_role,
                "consumer_role": consumer.route_role,
                "schema_hash": content_hash(
                    (producer.response_schema_hash, consumer.request_schema_hash)
                ),
            }
            edges.append(M336IRouteEdge(**body, edge_hash=content_hash(body)))
    ordered = tuple(
        sorted(
            edges,
            key=lambda item: (
                item.consumer_component_id,
                item.producer_component_id,
            ),
        )
    )
    provider = next(
        item
        for item in registry.components
        if item.route_role == "FINAL_ACQUISITION_PROVIDER"
    )
    body = {
        "schema_version": 1,
        "route_version": registry.route_version,
        "registry_hash": registry.registry_hash,
        "selector_component_id": registry.selector_component_id,
        "selector_algorithm_version": registry.selector_algorithm_version,
        "selector_seed_hash": registry.selector_seed_hash,
        "component_binding_hashes": tuple(
            sorted(item.binding_hash for item in registry.components)
        ),
        "edges": ordered,
        "edge_count": len(ordered),
        "incompatible_edge_count": 0,
        "unresolved_callable_count": registry.unresolved_component_count,
        "refusal_guard_registered_as_provider": provider.qualified_callable_name.startswith(
            "refuse_"
        ),
    }
    manifest = M336IRouteManifest(**body, manifest_hash=content_hash(body))
    if manifest.refusal_guard_registered_as_provider:
        raise ValueError("M336I refusal guard occupies the acquisition provider role")
    return manifest


def validate_m336i_route_registry(registry: M336IRouteRegistry) -> None:
    ids = tuple(item.component_id for item in registry.components)
    roles = tuple(item.route_role for item in registry.components)
    if (
        registry.route_version != M336I_ROUTE_VERSION
        or registry.selector_component_id != M336I_SELECTOR_COMPONENT_ID
        or registry.selector_algorithm_version != M336F_SELECTOR_VERSION
        or registry.component_count != len(registry.components)
        or len(ids) != len(set(ids))
        or registry.unresolved_component_count
        or registry.ambiguous_component_count
        or registry.dependency_cycle_count
        or roles.count("FINAL_ACQUISITION_PROVIDER") != 1
        or roles.count("FINAL_ACQUISITION_AUTHORIZATION_GUARD") != 1
    ):
        raise ValueError("M336I route registry is not closed")
    for component in registry.components:
        value = _resolve(component.python_module, component.qualified_callable_name)
        body = asdict(component)
        claimed = body.pop("binding_hash")
        if (
            _source_hash(value) != component.source_file_content_hash
            or content_hash(str(inspect.signature(value)))
            != component.callable_signature_hash
            or content_hash(body) != claimed
        ):
            raise ValueError("M336I route component binding changed")
    body = asdict(registry)
    claimed = body.pop("registry_hash")
    if content_hash(body) != claimed:
        raise ValueError("M336I route registry hash changed")


def _binding(spec) -> M336IRouteComponentBinding:
    role, component_id, module, name, dependencies, environments = spec
    value = _resolve(module, name)
    body = {
        "route_role": role,
        "component_id": component_id,
        "python_module": module,
        "qualified_callable_name": name,
        "source_file_content_hash": _source_hash(value),
        "callable_signature_hash": content_hash(str(inspect.signature(value))),
        "request_schema_hash": content_hash((role, "request", name)),
        "response_schema_hash": content_hash((role, "response", name)),
        "allowed_execution_environments": tuple(environments),
        "dependency_component_ids": tuple(dependencies),
    }
    return M336IRouteComponentBinding(**body, binding_hash=content_hash(body))


def _resolve(module_name: str, callable_name: str):
    value = importlib.import_module(module_name)
    for part in callable_name.split("."):
        value = getattr(value, part)
    if not callable(value):
        raise TypeError("M336I route component is not callable")
    return value


def _source_hash(value) -> str:
    source = inspect.getsourcefile(value)
    if source is None:
        raise ValueError("M336I route component has no source")
    return bytes_hash(Path(source).resolve(strict=True).read_bytes())


def _cycle_count(components) -> int:
    graph = {item.component_id: item.dependency_component_ids for item in components}
    visiting = set()
    visited = set()

    def visit(node):
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        found = any(visit(dependency) for dependency in graph[node])
        visiting.remove(node)
        visited.add(node)
        return found

    return sum(visit(node) for node in graph if node not in visited)
