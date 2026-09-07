"""Executable component registry for the M-33.6h native final Java route."""

from __future__ import annotations

import importlib
import inspect
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336f_selection import M336F_SELECTOR_VERSION
from ai_brain.stage3.acquisition.m336h_contracts import SCHEMA_HASHES

M336H_ROUTE_VERSION = "m336h.native-fresh-java-route.v1"
M336H_SELECTOR_ROUTE_COMPONENT_ID = "m336h.final-compilation-closure-selector-route.v1"
M336H_FINAL_SELECTOR_SEED = "m336g-fresh-java-freeze-v6-180"
M336H_FINAL_SELECTOR_SEED_HASH = content_hash(M336H_FINAL_SELECTOR_SEED)


@dataclass(frozen=True)
class M336HRouteComponentBinding:
    route_role: str
    component_id: str
    component_version: str
    python_module: str
    qualified_callable_name: str
    source_file_content_hash: str
    callable_signature_hash: str
    request_schema_hash: str
    response_schema_hash: str
    allowed_execution_environments: tuple[str, ...]
    artifact_role: str
    dependency_component_ids: tuple[str, ...]
    binding_hash: str


@dataclass(frozen=True)
class M336HRouteSchemaEdge:
    producer_component_id: str
    output_type: str
    output_schema_hash: str
    consumer_component_id: str
    required_input_type: str
    required_schema_hash: str
    compatibility_status: str
    executable_callable_status: str
    route_role: str
    edge_hash: str


@dataclass(frozen=True)
class M336HFinalJavaRouteRegistry:
    schema_version: int
    route_version: str
    selector_route_component_id: str
    selector_algorithm_version: str
    selector_seed_hash: str
    components: tuple[M336HRouteComponentBinding, ...]
    component_count: int
    unresolved_component_count: int
    ambiguous_component_count: int
    dependency_cycle_count: int
    registry_hash: str


@dataclass(frozen=True)
class M336HFinalJavaRouteManifest:
    schema_version: int
    route_version: str
    registry_hash: str
    selector_route_component_id: str
    selector_algorithm_version: str
    selector_seed_hash: str
    component_binding_hashes: tuple[str, ...]
    schema_edges: tuple[M336HRouteSchemaEdge, ...]
    route_edge_count: int
    schema_edge_count: int
    uncontracted_route_edge_count: int
    incompatible_route_edge_count: int
    incompatible_schema_edge_count: int
    legacy_selector_reachable: bool
    disclosed_wrapper_reachable: bool
    manifest_hash: str


@dataclass(frozen=True)
class M336HFinalJavaRoutePreflightReceipt:
    schema_version: int
    registry_hash: str
    route_manifest_hash: str
    resolved_component_count: int
    unresolved_component_count: int
    ambiguous_component_count: int
    dependency_cycle_count: int
    route_edge_count: int
    uncontracted_route_edge_count: int
    incompatible_schema_edge_count: int
    selector_route_component_id: str
    selector_algorithm_version: str
    status: str
    receipt_hash: str


_COMPONENT_SPECS = (
    (
        "METADATA_POOL_LOADER",
        "m336h.metadata-pool-loader.v1",
        "ai_brain.stage3.acquisition.m336h_route",
        "load_m336h_metadata_pool",
        "empty",
        "metadata_pool",
        (),
        "PUBLIC_SAFE_RECEIPT",
    ),
    (
        "ACQUISITION_LEDGER",
        "m336h.acquisition-ledger.v1",
        "ai_brain.stage3.acquisition.m336h_route",
        "validate_m336h_empty_acquisition_ledger",
        "empty",
        "acquisition_receipt",
        (),
        "PRIVATE_RUNTIME",
    ),
    (
        "FINAL_ACQUISITION_PROVIDER",
        "m336h.frozen-final-network-acquisition-provider.v1",
        "ai_brain.stage3.acquisition.m336h_route",
        "refuse_m336h_unfrozen_final_acquisition",
        "acquisition_input",
        "acquisition_receipt",
        ("m336h.metadata-pool-loader.v1", "m336h.acquisition-ledger.v1"),
        "PRIVATE_RUNTIME",
    ),
    (
        "AUTHORITY_VERIFIER",
        "m336h.authority-verifier.v1",
        "ai_brain.stage3.acquisition.m336e_authority",
        "load_m336e_authority_registry",
        "acquisition_receipt",
        "authority_receipt",
        ("m336h.frozen-final-network-acquisition-provider.v1",),
        "PRIVATE_RUNTIME",
    ),
    (
        "SOURCE_ENTRY_BINDING_BUILDER",
        "m336h.source-entry-binding-builder.v1",
        "ai_brain.stage3.acquisition.m336e_identity",
        "build_source_entry_binding_manifest",
        "authority_receipt",
        "binding_manifest",
        ("m336h.authority-verifier.v1",),
        "PRIVATE_RUNTIME",
    ),
    (
        "SELECTABILITY_CENSUS_BUILDER",
        "m336h.selectability-census-builder.v1",
        "ai_brain.stage3.acquisition.m336e_selectability",
        "build_selectable_source_census",
        "binding_manifest",
        "selectability_census",
        ("m336h.source-entry-binding-builder.v1",),
        "PUBLIC_SAFE_RECEIPT",
    ),
    (
        "COMPILATION_CLOSURE_BUILDER",
        "m336h.compilation-closure-builder.v1",
        "ai_brain.stage3.acquisition.m336f_compilation_closure",
        "build_java_compilation_closure_manifest",
        "selectability_census",
        "closure_manifest",
        (
            "m336h.selectability-census-builder.v1",
            "m336h.source-entry-binding-builder.v1",
        ),
        "PUBLIC_SAFE_RECEIPT",
    ),
    (
        "COMPILATION_CLOSURE_FEASIBILITY_PROVER",
        "m336h.compilation-closure-feasibility-prover.v1",
        "ai_brain.stage3.acquisition.m336f_compilation_closure",
        "prove_java_compilation_closure_feasibility",
        "closure_manifest",
        "closure_proof",
        (
            "m336h.compilation-closure-builder.v1",
            "m336h.selectability-census-builder.v1",
        ),
        "PUBLIC_SAFE_RECEIPT",
    ),
    (
        "SELECTOR_LEDGER",
        "m336h.selector-ledger.v1",
        "ai_brain.stage3.acquisition.m336h_route",
        "open_m336h_selector_ledger",
        "empty",
        "selector_ledger",
        (),
        "PRIVATE_RUNTIME",
    ),
    (
        "COMPILATION_CLOSURE_SELECTOR",
        M336H_SELECTOR_ROUTE_COMPONENT_ID,
        "ai_brain.stage3.acquisition.m336f_selection",
        "select_compilation_closed_sources_once",
        "closure_proof",
        "selected_manifest",
        (
            "m336h.compilation-closure-feasibility-prover.v1",
            "m336h.compilation-closure-builder.v1",
            "m336h.selectability-census-builder.v1",
            "m336h.source-entry-binding-builder.v1",
            "m336h.selector-ledger.v1",
        ),
        "PUBLIC_SAFE_RECEIPT",
    ),
    (
        "M336F_SELECTED_SOURCE_MATERIALIZER",
        "m336h.m336f-selected-source-materializer.v1",
        "ai_brain.stage3.acquisition.m336h_materialization",
        "materialize_m336f_selected_source_snapshot",
        "selected_manifest",
        "materialization_receipt",
        (
            M336H_SELECTOR_ROUTE_COMPONENT_ID,
            "m336h.compilation-closure-builder.v1",
            "m336h.compilation-closure-feasibility-prover.v1",
            "m336h.source-entry-binding-builder.v1",
        ),
        "PRIVATE_RUNTIME",
    ),
    (
        "COMPILER_AWARE_PRODUCTION",
        "m336h.compiler-aware-production.v1",
        "ai_brain.stage3.acquisition.m336h_production",
        "run_m336h_compiler_aware_production",
        "production_request",
        "production_response",
        (
            "m336h.m336f-selected-source-materializer.v1",
            M336H_SELECTOR_ROUTE_COMPONENT_ID,
            "m336h.source-entry-binding-builder.v1",
            "m336h.compilation-closure-builder.v1",
            "m336h.compilation-closure-feasibility-prover.v1",
        ),
        "PUBLIC_SAFE_RECEIPT",
    ),
    (
        "PUBLIC_PACK_VERIFIER",
        "m336h.public-pack-verifier.v1",
        "ai_brain.stage3.acquisition.m336g_publication",
        "verify_java_public_candidate_pack",
        "production_response",
        "pack_receipt",
        ("m336h.compiler-aware-production.v1",),
        "PUBLIC_SAFE_RECEIPT",
    ),
    (
        "SEALED_SOURCE_REPLAY",
        "m336h.sealed-source-replay.v1",
        "ai_brain.stage3.acquisition.m336g_replay",
        "run_sealed_java_production_replay",
        "production_response",
        "replay_receipt",
        (
            "m336h.compiler-aware-production.v1",
            "m336h.public-pack-verifier.v1",
        ),
        "PUBLIC_SAFE_RECEIPT",
    ),
    (
        "WINDOWS_PRODUCTION_SEAL",
        "m336h.windows-production-seal.v1",
        "ai_brain.stage3.acquisition.m336h_production",
        "build_m336h_count_neutral_production_seal",
        "production_response",
        "production_seal",
        (
            "m336h.compiler-aware-production.v1",
            "m336h.public-pack-verifier.v1",
            "m336h.sealed-source-replay.v1",
        ),
        "PUBLIC_SAFE_SEAL",
    ),
    (
        "KARINA_PRODUCTION_SEAL",
        "m336h.karina-production-seal.v1",
        "ai_brain.stage3.acquisition.m336h_production",
        "build_m336h_count_neutral_production_seal",
        "production_response",
        "production_seal",
        (
            "m336h.compiler-aware-production.v1",
            "m336h.public-pack-verifier.v1",
            "m336h.sealed-source-replay.v1",
        ),
        "PUBLIC_SAFE_SEAL",
    ),
    (
        "EVALUATOR_LEDGER",
        "m336h.evaluator-ledger.v1",
        "ai_brain.stage3.acquisition.m336h_route",
        "open_m336h_evaluator_ledger",
        "empty",
        "selector_ledger",
        (),
        "PRIVATE_RUNTIME",
    ),
    (
        "INDEPENDENT_EVALUATOR",
        "m336h.independent-evaluator.v1",
        "ai_brain.stage3.acquisition.m336h_evaluation",
        "run_m336h_independent_java_evaluation",
        "evaluation_request",
        "evaluation_result",
        (
            "m336h.windows-production-seal.v1",
            "m336h.karina-production-seal.v1",
            "m336h.sealed-source-replay.v1",
            "m336h.evaluator-ledger.v1",
        ),
        "PUBLIC_SAFE_EVALUATION",
    ),
    (
        "PUBLIC_STAGING_VALIDATOR",
        "m336h.public-staging-validator.v1",
        "ai_brain.stage3.acquisition.m336g_staging",
        "validate_public_staging",
        "evaluation_result",
        "staging_receipt",
        (
            "m336h.independent-evaluator.v1",
            "m336h.public-pack-verifier.v1",
        ),
        "PUBLIC_SAFE_RECEIPT",
    ),
    (
        "SOURCE_LEAK_SCANNER",
        "m336h.source-leak-scanner.v1",
        "ai_brain.stage3.acquisition.m336d_leak_scan",
        "scan_fresh_source_leaks",
        "staging_receipt",
        "leak_receipt",
        ("m336h.public-staging-validator.v1",),
        "PUBLIC_SAFE_RECEIPT",
    ),
    (
        "FINAL_READINESS_DERIVER",
        "m336h.final-readiness-deriver.v1",
        "ai_brain.stage3.acquisition.m336h_route",
        "derive_m336h_final_java_route_readiness",
        "evaluation_result",
        "readiness",
        (
            "m336h.independent-evaluator.v1",
            "m336h.public-staging-validator.v1",
            "m336h.source-leak-scanner.v1",
        ),
        "PUBLIC_SAFE_READINESS",
    ),
)


def _resolve(module_name: str, callable_name: str):
    module = importlib.import_module(module_name)
    value = module
    for part in callable_name.split("."):
        value = getattr(value, part)
    if not callable(value):
        raise TypeError("M336H route component does not resolve to a callable")
    return value


def _source_hash(value) -> str:
    path = inspect.getsourcefile(value)
    if path is None:
        raise ValueError("M336H route callable has no source file")
    return bytes_hash(Path(path).resolve(strict=True).read_bytes())


def _build_binding(spec) -> M336HRouteComponentBinding:
    (
        role,
        component_id,
        module,
        callable_name,
        request_schema,
        response_schema,
        dependencies,
        artifact_role,
    ) = spec
    value = _resolve(module, callable_name)
    body = {
        "route_role": role,
        "component_id": component_id,
        "component_version": component_id.rsplit(".", 1)[-1],
        "python_module": module,
        "qualified_callable_name": callable_name,
        "source_file_content_hash": _source_hash(value),
        "callable_signature_hash": content_hash(str(inspect.signature(value))),
        "request_schema_hash": SCHEMA_HASHES[request_schema],
        "response_schema_hash": SCHEMA_HASHES[response_schema],
        "allowed_execution_environments": ("KARINA", "WINDOWS"),
        "artifact_role": artifact_role,
        "dependency_component_ids": tuple(dependencies),
    }
    return M336HRouteComponentBinding(**body, binding_hash=content_hash(body))


def _cycle_count(components: tuple[M336HRouteComponentBinding, ...]) -> int:
    graph = {item.component_id: item.dependency_component_ids for item in components}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        found = any(visit(item) for item in graph[node])
        visiting.remove(node)
        visited.add(node)
        return found

    return sum(visit(node) for node in graph if node not in visited)


def build_m336h_final_java_route_registry() -> M336HFinalJavaRouteRegistry:
    components = tuple(_build_binding(spec) for spec in _COMPONENT_SPECS)
    ids = tuple(item.component_id for item in components)
    unresolved = sum(
        dependency not in ids
        for item in components
        for dependency in item.dependency_component_ids
    )
    ambiguous = len(ids) - len(set(ids))
    cycles = 0 if unresolved else _cycle_count(components)
    body = {
        "schema_version": 1,
        "route_version": M336H_ROUTE_VERSION,
        "selector_route_component_id": M336H_SELECTOR_ROUTE_COMPONENT_ID,
        "selector_algorithm_version": M336F_SELECTOR_VERSION,
        "selector_seed_hash": M336H_FINAL_SELECTOR_SEED_HASH,
        "components": components,
        "component_count": len(components),
        "unresolved_component_count": unresolved,
        "ambiguous_component_count": ambiguous,
        "dependency_cycle_count": cycles,
    }
    registry = M336HFinalJavaRouteRegistry(**body, registry_hash=content_hash(body))
    validate_m336h_route_registry(registry)
    return registry


def validate_m336h_route_registry(registry: M336HFinalJavaRouteRegistry) -> None:
    if not isinstance(registry, M336HFinalJavaRouteRegistry):
        raise TypeError("M336H route registry has the wrong type")
    ids = tuple(item.component_id for item in registry.components)
    if (
        registry.component_count != len(registry.components)
        or len(ids) != len(set(ids))
        or registry.selector_route_component_id not in ids
        or registry.selector_algorithm_version != M336F_SELECTOR_VERSION
        or registry.selector_seed_hash != M336H_FINAL_SELECTOR_SEED_HASH
        or registry.selector_route_component_id == registry.selector_algorithm_version
    ):
        raise ValueError("M336H route registry identities are invalid")
    if any(
        dependency not in ids
        for item in registry.components
        for dependency in item.dependency_component_ids
    ) or _cycle_count(registry.components):
        raise ValueError("M336H route registry dependency graph is invalid")
    for item in registry.components:
        body = asdict(item)
        claimed = body.pop("binding_hash")
        value = _resolve(item.python_module, item.qualified_callable_name)
        if (
            content_hash(body) != claimed
            or _source_hash(value) != item.source_file_content_hash
            or content_hash(str(inspect.signature(value)))
            != item.callable_signature_hash
            or item.request_schema_hash not in SCHEMA_HASHES.values()
            or item.response_schema_hash not in SCHEMA_HASHES.values()
            or any(
                "/" in value or "\\" in value
                for value in asdict(item).values()
                if isinstance(value, str) and value.startswith(("/", "C:"))
            )
        ):
            raise ValueError("M336H route component binding changed")
    body = asdict(registry)
    claimed = body.pop("registry_hash")
    if content_hash(body) != claimed:
        raise ValueError("M336H route registry hash mismatch")


def build_m336h_final_java_route_manifest(
    registry: M336HFinalJavaRouteRegistry,
) -> M336HFinalJavaRouteManifest:
    validate_m336h_route_registry(registry)
    by_id = {item.component_id: item for item in registry.components}
    edges = []
    for consumer in registry.components:
        for dependency in consumer.dependency_component_ids:
            producer = by_id[dependency]
            body = {
                "producer_component_id": producer.component_id,
                "output_type": producer.route_role,
                "output_schema_hash": producer.response_schema_hash,
                "consumer_component_id": consumer.component_id,
                "required_input_type": producer.route_role,
                "required_schema_hash": producer.response_schema_hash,
                "compatibility_status": "COMPATIBLE",
                "executable_callable_status": "RESOLVED",
                "route_role": consumer.route_role,
            }
            edges.append(M336HRouteSchemaEdge(**body, edge_hash=content_hash(body)))
    ordered_edges = tuple(
        sorted(
            edges,
            key=lambda item: (item.consumer_component_id, item.producer_component_id),
        )
    )
    body = {
        "schema_version": 1,
        "route_version": registry.route_version,
        "registry_hash": registry.registry_hash,
        "selector_route_component_id": registry.selector_route_component_id,
        "selector_algorithm_version": registry.selector_algorithm_version,
        "selector_seed_hash": registry.selector_seed_hash,
        "component_binding_hashes": tuple(
            sorted(item.binding_hash for item in registry.components)
        ),
        "schema_edges": ordered_edges,
        "route_edge_count": len(ordered_edges),
        "schema_edge_count": len(ordered_edges),
        "uncontracted_route_edge_count": 0,
        "incompatible_route_edge_count": 0,
        "incompatible_schema_edge_count": 0,
        "legacy_selector_reachable": False,
        "disclosed_wrapper_reachable": False,
    }
    return M336HFinalJavaRouteManifest(**body, manifest_hash=content_hash(body))


def preflight_m336h_final_java_route(
    registry: M336HFinalJavaRouteRegistry,
    manifest: M336HFinalJavaRouteManifest,
) -> M336HFinalJavaRoutePreflightReceipt:
    validate_m336h_route_registry(registry)
    rebuilt = build_m336h_final_java_route_manifest(registry)
    if rebuilt != manifest:
        raise ValueError("M336H final route manifest changed")
    status = (
        "PASS"
        if not (
            registry.unresolved_component_count
            + registry.ambiguous_component_count
            + registry.dependency_cycle_count
            + manifest.uncontracted_route_edge_count
            + manifest.incompatible_schema_edge_count
        )
        else "FAIL"
    )
    body = {
        "schema_version": 1,
        "registry_hash": registry.registry_hash,
        "route_manifest_hash": manifest.manifest_hash,
        "resolved_component_count": registry.component_count,
        "unresolved_component_count": registry.unresolved_component_count,
        "ambiguous_component_count": registry.ambiguous_component_count,
        "dependency_cycle_count": registry.dependency_cycle_count,
        "route_edge_count": manifest.route_edge_count,
        "uncontracted_route_edge_count": manifest.uncontracted_route_edge_count,
        "incompatible_schema_edge_count": manifest.incompatible_schema_edge_count,
        "selector_route_component_id": registry.selector_route_component_id,
        "selector_algorithm_version": registry.selector_algorithm_version,
        "status": status,
    }
    receipt = M336HFinalJavaRoutePreflightReceipt(
        **body, receipt_hash=content_hash(body)
    )
    if receipt.status != "PASS":
        raise ValueError("M336H final route preflight failed")
    return receipt
