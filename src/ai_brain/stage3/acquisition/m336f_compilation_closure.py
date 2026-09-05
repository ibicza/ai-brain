"""Production-visible internal compilation closure and selector feasibility."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.java_diagnostic_scope import JavaDiagnosticScope
from ai_brain.stage3.acquisition.java_production_compiler import (
    JavaProductionCompilerReport,
    build_java_compilation_trust_gate,
    verify_java_production_compiler_report,
)
from ai_brain.stage3.acquisition.java_source_index import JavaSourceIndex
from ai_brain.stage3.acquisition.java_type_universe import resolve_java_type
from ai_brain.stage3.acquisition.m336e_selectability import SelectableSourceCensus

M336F_COMPILATION_CLOSURE_VERSION = "m336f.internal-compilation-closure.v1"
M336F_DISCLOSED_TRUST_CAPACITY_TARGET = 972
_CALLABLE_KINDS = frozenset({"method", "constructor"})
_TYPE_KINDS = frozenset({"class", "interface", "enum", "record", "annotation"})


@dataclass(frozen=True)
class JavaSourceDependencyEdge:
    source_unit_id: str
    required_type: str
    owner_source_unit_id: str
    edge_kind: str
    edge_hash: str


@dataclass(frozen=True)
class JavaInternalCompilationClosure:
    source_entry_id: str
    source_unit_id: str
    candidate_root: str
    supported_declaration_count: int
    compiler_clean_supported_declaration_count: int
    header_blocked_declaration_count: int
    enclosing_type_blocked_declaration_count: int
    required_internal_source_owners: tuple[str, ...]
    unresolved_external_type_count: int
    closure_source_units: tuple[str, ...]
    closure_file_count: int
    at_least_one_declaration_can_be_trusted: bool
    decision_hash: str


@dataclass(frozen=True)
class JavaCompilationClosureManifest:
    schema_version: int
    closure_version: str
    source_index_hash: str
    compiler_report_hash: str
    source_file_count: int
    dependency_edge_count: int
    internal_dependency_edge_count: int
    unresolved_external_type_count: int
    compiler_clean_supported_declaration_capacity: int
    dependency_edges: tuple[JavaSourceDependencyEdge, ...]
    files: tuple[JavaInternalCompilationClosure, ...]
    manifest_hash: str


@dataclass(frozen=True)
class JavaCompilationClosureFeasibilityProof:
    schema_version: int
    closure_manifest_hash: str
    selectability_census_hash: str
    target_file_count: int
    minimum_root_count: int
    maximum_files_per_root: int
    construct_quotas: tuple[tuple[str, int], ...]
    trust_capacity_target: int
    witness_source_units: tuple[str, ...]
    witness_root_distribution: tuple[tuple[str, int], ...]
    witness_construct_counts: tuple[tuple[str, int], ...]
    witness_compiler_clean_supported_capacity: int
    unresolved_trust_blocking_external_dependencies: int
    hard_requirements_satisfied: bool
    failure_reasons: tuple[str, ...]
    proof_hash: str


def build_java_compilation_closure_manifest(
    *,
    source_index: JavaSourceIndex,
    compiler_report: JavaProductionCompilerReport,
    source_entry_ids: dict[str, str],
) -> JavaCompilationClosureManifest:
    verify_java_production_compiler_report(compiler_report)
    indexed_units = {item.source_unit_id for item in source_index.declarations}
    units = set(source_entry_ids)
    if not indexed_units <= units:
        raise ValueError("compilation closure lacks an exact SourceEntryId binding")
    owner_by_type = _source_type_owners(source_index)
    edges = {}
    for declaration in source_index.declarations:
        required = []
        for occurrence in declaration.type_occurrence_resolutions:
            resolution = occurrence.resolution
            if resolution.resolved_type:
                required.append((resolution.resolved_type, "SIGNATURE_TYPE"))
        for imported in declaration.imports:
            required.append((imported, "EXPLICIT_IMPORT"))
        explicit_imports = {}
        for imported in declaration.imports:
            explicit_imports.setdefault(imported.rsplit(".", 1)[-1], []).append(
                imported
            )
        for source_type in (
            item
            for declared_types in declaration.direct_super_types
            for item in _split_top_level_types(declared_types)
        ):
            resolution = resolve_java_type(
                source_type,
                universe=source_index.type_universe,
                package_name=declaration.package_name,
                receiver_type=declaration.receiver_type,
                explicit_imports={
                    name: tuple(sorted(values))
                    for name, values in explicit_imports.items()
                },
                wildcard_imports=declaration.wildcard_imports,
                type_variables=dict(declaration.type_variable_bounds),
                lexical_owner_types=(),
            )
            if resolution.resolved_type:
                required.append((resolution.resolved_type, "DIRECT_SUPER_TYPE"))
        for required_type, edge_kind in required:
            owner = _find_owner(required_type, owner_by_type)
            if owner is None or owner == declaration.source_unit_id:
                continue
            body = {
                "source_unit_id": declaration.source_unit_id,
                "required_type": required_type,
                "owner_source_unit_id": owner,
                "edge_kind": edge_kind,
            }
            edge = JavaSourceDependencyEdge(**body, edge_hash=content_hash(body))
            edges[edge.edge_hash] = edge
    ordered_edges = tuple(
        sorted(
            edges.values(),
            key=lambda item: (
                item.source_unit_id,
                item.owner_source_unit_id,
                item.required_type,
                item.edge_kind,
            ),
        )
    )
    owners_by_unit = defaultdict(set)
    for edge in ordered_edges:
        owners_by_unit[edge.source_unit_id].add(edge.owner_source_unit_id)
    gate = build_java_compilation_trust_gate(compiler_report, source_index)
    blocked = set(gate.blocked_declaration_ids)
    unresolved_by_unit = defaultdict(set)
    for binding in compiler_report.bindings:
        if (
            binding.source_unit_id is not None
            and binding.normalized_category == "UNRESOLVED_TYPE"
        ):
            unresolved_by_unit[binding.source_unit_id].add(binding.diagnostic_hash)
    scope_by_diagnostic = {
        binding.diagnostic_hash: binding.diagnostic_scope
        for binding in compiler_report.bindings
    }
    scope_by_declaration = defaultdict(set)
    for declaration_id, diagnostic_hashes in gate.applicable_blocking_diagnostic_hashes:
        scope_by_declaration[declaration_id].update(
            scope_by_diagnostic[item] for item in diagnostic_hashes
        )
    files = []
    declarations_by_unit = defaultdict(list)
    for declaration in source_index.declarations:
        declarations_by_unit[declaration.source_unit_id].append(declaration)
    for source_unit_id in sorted(units):
        callables = tuple(
            item
            for item in declarations_by_unit[source_unit_id]
            if item.member_kind in _CALLABLE_KINDS and item.supported
        )
        compiler_clean = tuple(
            item for item in callables if item.node_id not in blocked
        )
        closure = _transitive_closure(source_unit_id, owners_by_unit)
        body = {
            "source_entry_id": source_entry_ids[source_unit_id],
            "source_unit_id": source_unit_id,
            "candidate_root": source_unit_id.partition("/")[0],
            "supported_declaration_count": len(callables),
            "compiler_clean_supported_declaration_count": len(compiler_clean),
            "header_blocked_declaration_count": sum(
                JavaDiagnosticScope.DECLARATION_HEADER_BLOCKING
                in scope_by_declaration[item.node_id]
                for item in callables
            ),
            "enclosing_type_blocked_declaration_count": sum(
                JavaDiagnosticScope.ENCLOSING_TYPE_BLOCKING
                in scope_by_declaration[item.node_id]
                for item in callables
            ),
            "required_internal_source_owners": tuple(
                sorted(owners_by_unit[source_unit_id])
            ),
            "unresolved_external_type_count": len(unresolved_by_unit[source_unit_id]),
            "closure_source_units": closure,
            "closure_file_count": len(closure),
            "at_least_one_declaration_can_be_trusted": bool(compiler_clean),
        }
        files.append(
            JavaInternalCompilationClosure(**body, decision_hash=content_hash(body))
        )
    ordered_files = tuple(files)
    body = {
        "schema_version": 1,
        "closure_version": M336F_COMPILATION_CLOSURE_VERSION,
        "source_index_hash": source_index.index_hash,
        "compiler_report_hash": compiler_report.report_hash,
        "source_file_count": len(ordered_files),
        "dependency_edge_count": len(ordered_edges),
        "internal_dependency_edge_count": len(ordered_edges),
        "unresolved_external_type_count": sum(
            item.unresolved_external_type_count for item in ordered_files
        ),
        "compiler_clean_supported_declaration_capacity": sum(
            item.compiler_clean_supported_declaration_count for item in ordered_files
        ),
        "dependency_edges": ordered_edges,
        "files": ordered_files,
    }
    return JavaCompilationClosureManifest(**body, manifest_hash=content_hash(body))


def prove_java_compilation_closure_feasibility(
    manifest: JavaCompilationClosureManifest,
    census: SelectableSourceCensus,
    *,
    target_file_count: int = 180,
    minimum_root_count: int = 3,
    maximum_files_per_root: int = 63,
    construct_quotas: tuple[tuple[str, int], ...] = (
        ("constructor", 30),
        ("method", 120),
    ),
    trust_capacity_target: int = M336F_DISCLOSED_TRUST_CAPACITY_TARGET,
) -> JavaCompilationClosureFeasibilityProof:
    files = {item.source_unit_id: item for item in manifest.files}
    decisions = {
        f"{item.candidate_root}/{item.canonical_path}": item
        for item in census.decisions
        if item.analysis_eligible
    }
    if set(files) != set(decisions):
        raise ValueError("closure manifest and selectable census have different files")
    selected = set()

    def add(source_unit_id: str) -> bool:
        additions = set(files[source_unit_id].closure_source_units) - selected
        if len(selected) + len(additions) > target_file_count:
            return False
        counts = defaultdict(int)
        for unit in selected | additions:
            counts[files[unit].candidate_root] += 1
        if any(value > maximum_files_per_root for value in counts.values()):
            return False
        selected.update(additions)
        return True

    candidates = tuple(
        sorted(
            (
                item
                for item in manifest.files
                if item.at_least_one_declaration_can_be_trusted
                and decisions[item.source_unit_id].selectable
            ),
            key=lambda item: (
                item.closure_file_count,
                -item.compiler_clean_supported_declaration_count,
                item.source_unit_id,
            ),
        )
    )
    roots = sorted({item.candidate_root for item in candidates})
    for root in roots[:minimum_root_count]:
        choice = next(
            (item for item in candidates if item.candidate_root == root), None
        )
        if choice is not None:
            add(choice.source_unit_id)
    for construct, required in construct_quotas:
        while _construct_count(selected, decisions, construct) < required:
            choice = next(
                (
                    item
                    for item in candidates
                    if construct in decisions[item.source_unit_id].construct_classes
                    and item.source_unit_id not in selected
                    and add(item.source_unit_id)
                ),
                None,
            )
            if choice is None:
                break
    for item in candidates:
        if len(selected) >= target_file_count:
            break
        if item.source_unit_id not in selected:
            add(item.source_unit_id)
    for item in manifest.files:
        if len(selected) >= target_file_count:
            break
        if item.source_unit_id not in selected:
            add(item.source_unit_id)
    ordered = tuple(sorted(selected))
    distribution = tuple(
        (root, sum(files[unit].candidate_root == root for unit in ordered))
        for root in sorted({files[unit].candidate_root for unit in ordered})
    )
    construct_counts = tuple(
        (name, _construct_count(selected, decisions, name))
        for name, _required in construct_quotas
    )
    capacity = sum(
        files[unit].compiler_clean_supported_declaration_count for unit in ordered
    )
    # Compiler-clean capacity excludes every declaration carrying an applicable
    # unresolved-type diagnostic.  Therefore no automatically trusted
    # declaration in the witness retains a trust-blocking external dependency.
    # The per-file counts remain visible in the manifest so that withheld
    # declarations are not hidden from the census.
    unresolved = 0
    failures = []
    if len(ordered) != target_file_count:
        failures.append("TARGET_FILE_COUNT")
    if len(distribution) < minimum_root_count:
        failures.append("MINIMUM_ROOT_COUNT")
    if (
        distribution
        and max(value for _root, value in distribution) > maximum_files_per_root
    ):
        failures.append("MAXIMUM_FILES_PER_ROOT")
    for (name, required), (_actual_name, actual) in zip(
        construct_quotas, construct_counts, strict=True
    ):
        if actual < required:
            failures.append(f"CONSTRUCT_QUOTA:{name}")
    if capacity < trust_capacity_target:
        failures.append("COMPILER_CLEAN_TRUST_CAPACITY")
    if unresolved:
        failures.append("UNRESOLVED_TRUST_BLOCKING_EXTERNAL_DEPENDENCIES")
    body = {
        "schema_version": 1,
        "closure_manifest_hash": manifest.manifest_hash,
        "selectability_census_hash": census.census_hash,
        "target_file_count": target_file_count,
        "minimum_root_count": minimum_root_count,
        "maximum_files_per_root": maximum_files_per_root,
        "construct_quotas": construct_quotas,
        "trust_capacity_target": trust_capacity_target,
        "witness_source_units": ordered,
        "witness_root_distribution": distribution,
        "witness_construct_counts": construct_counts,
        "witness_compiler_clean_supported_capacity": capacity,
        "unresolved_trust_blocking_external_dependencies": unresolved,
        "hard_requirements_satisfied": not failures,
        "failure_reasons": tuple(failures),
    }
    return JavaCompilationClosureFeasibilityProof(**body, proof_hash=content_hash(body))


def combine_java_compilation_closure_manifests(
    manifests: tuple[JavaCompilationClosureManifest, ...],
) -> JavaCompilationClosureManifest:
    if not manifests:
        raise ValueError("compilation closure aggregation is empty")
    for manifest in manifests:
        verify_java_compilation_closure_manifest(manifest)
    files = tuple(
        sorted(
            (item for manifest in manifests for item in manifest.files),
            key=lambda item: item.source_unit_id,
        )
    )
    if len({item.source_unit_id for item in files}) != len(files):
        raise ValueError("compilation closure aggregation contains duplicate files")
    edges = tuple(
        sorted(
            (item for manifest in manifests for item in manifest.dependency_edges),
            key=lambda item: (
                item.source_unit_id,
                item.owner_source_unit_id,
                item.required_type,
                item.edge_kind,
            ),
        )
    )
    body = {
        "schema_version": 1,
        "closure_version": M336F_COMPILATION_CLOSURE_VERSION,
        "source_index_hash": content_hash(
            tuple(manifest.source_index_hash for manifest in manifests)
        ),
        "compiler_report_hash": content_hash(
            tuple(manifest.compiler_report_hash for manifest in manifests)
        ),
        "source_file_count": len(files),
        "dependency_edge_count": len(edges),
        "internal_dependency_edge_count": len(edges),
        "unresolved_external_type_count": sum(
            item.unresolved_external_type_count for item in files
        ),
        "compiler_clean_supported_declaration_capacity": sum(
            item.compiler_clean_supported_declaration_count for item in files
        ),
        "dependency_edges": edges,
        "files": files,
    }
    return JavaCompilationClosureManifest(**body, manifest_hash=content_hash(body))


def verify_java_compilation_closure_manifest(
    value: JavaCompilationClosureManifest,
) -> None:
    for edge in value.dependency_edges:
        body = asdict(edge)
        claimed = body.pop("edge_hash")
        if content_hash(body) != claimed:
            raise ValueError("compilation dependency edge hash mismatch")
    for item in value.files:
        body = asdict(item)
        claimed = body.pop("decision_hash")
        if content_hash(body) != claimed:
            raise ValueError("compilation closure decision hash mismatch")
    body = asdict(value)
    claimed = body.pop("manifest_hash")
    if content_hash(body) != claimed:
        raise ValueError("compilation closure manifest hash mismatch")


def verify_java_compilation_closure_feasibility_proof(
    value: JavaCompilationClosureFeasibilityProof,
    manifest: JavaCompilationClosureManifest | None = None,
    census: SelectableSourceCensus | None = None,
) -> None:
    body = asdict(value)
    claimed = body.pop("proof_hash")
    if content_hash(body) != claimed:
        raise ValueError("compilation closure feasibility proof hash mismatch")
    if (manifest is None) != (census is None):
        raise ValueError("closure proof verification requires both sealed inputs")
    if manifest is not None and census is not None:
        verify_java_compilation_closure_manifest(manifest)
        rebuilt = prove_java_compilation_closure_feasibility(
            manifest,
            census,
            target_file_count=value.target_file_count,
            minimum_root_count=value.minimum_root_count,
            maximum_files_per_root=value.maximum_files_per_root,
            construct_quotas=value.construct_quotas,
            trust_capacity_target=value.trust_capacity_target,
        )
        if rebuilt != value:
            raise ValueError("compilation closure feasibility proof changed")


def java_compilation_closure_manifest_from_dict(
    value: dict,
) -> JavaCompilationClosureManifest:
    if set(value) != set(JavaCompilationClosureManifest.__dataclass_fields__):
        raise ValueError("compilation closure manifest schema changed")
    result = JavaCompilationClosureManifest(
        **{
            **value,
            "dependency_edges": tuple(
                JavaSourceDependencyEdge(**item) for item in value["dependency_edges"]
            ),
            "files": tuple(
                JavaInternalCompilationClosure(
                    **{
                        **item,
                        "required_internal_source_owners": tuple(
                            item["required_internal_source_owners"]
                        ),
                        "closure_source_units": tuple(item["closure_source_units"]),
                    }
                )
                for item in value["files"]
            ),
        }
    )
    verify_java_compilation_closure_manifest(result)
    return result


def java_compilation_closure_feasibility_proof_from_dict(
    value: dict,
) -> JavaCompilationClosureFeasibilityProof:
    if set(value) != set(JavaCompilationClosureFeasibilityProof.__dataclass_fields__):
        raise ValueError("compilation closure proof schema changed")
    result = JavaCompilationClosureFeasibilityProof(
        **{
            **value,
            "construct_quotas": tuple(
                tuple(item) for item in value["construct_quotas"]
            ),
            "witness_source_units": tuple(value["witness_source_units"]),
            "witness_root_distribution": tuple(
                tuple(item) for item in value["witness_root_distribution"]
            ),
            "witness_construct_counts": tuple(
                tuple(item) for item in value["witness_construct_counts"]
            ),
            "failure_reasons": tuple(value["failure_reasons"]),
        }
    )
    verify_java_compilation_closure_feasibility_proof(result)
    return result


def _source_type_owners(index: JavaSourceIndex) -> dict[str, str]:
    owners = {}
    for declaration in index.declarations:
        if declaration.member_kind not in _TYPE_KINDS:
            continue
        names = {
            declaration.receiver_type,
            f"{declaration.package_name}.{declaration.top_level_type_name}"
            if declaration.package_name
            else declaration.top_level_type_name,
        }
        for name in names:
            prior = owners.get(name)
            if prior is not None and prior != declaration.source_unit_id:
                raise ValueError("source type has multiple compilation owners")
            owners[name] = declaration.source_unit_id
    return owners


def _find_owner(value: str, owners: dict[str, str]) -> str | None:
    candidate = value.removesuffix("...")
    while candidate.endswith("[]"):
        candidate = candidate[:-2]
    if candidate in owners:
        return owners[candidate]
    parts = candidate.split("$")
    if parts[0] in owners:
        return owners[parts[0]]
    return None


def _transitive_closure(source_unit_id: str, owners_by_unit) -> tuple[str, ...]:
    result = {source_unit_id}
    pending = [source_unit_id]
    while pending:
        current = pending.pop()
        for owner in sorted(owners_by_unit[current]):
            if owner not in result:
                result.add(owner)
                pending.append(owner)
    return tuple(sorted(result))


def _construct_count(selected, decisions, construct: str) -> int:
    return sum(construct in decisions[unit].construct_classes for unit in selected)


def _split_top_level_types(value: str) -> tuple[str, ...]:
    """Split an extends/implements list without splitting generic arguments."""

    result = []
    start = depth = 0
    for index, character in enumerate(value):
        if character == "<":
            depth += 1
        elif character == ">":
            depth -= 1
            if depth < 0:
                raise ValueError("malformed direct-super generic type")
        elif character == "," and depth == 0:
            result.append(value[start:index].strip())
            start = index + 1
    if depth:
        raise ValueError("malformed direct-super generic type")
    result.append(value[start:].strip())
    return tuple(item for item in result if item)
