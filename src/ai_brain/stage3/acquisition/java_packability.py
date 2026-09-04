"""Pre-trust Java identity and pack namespace closure."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.java_identity import (
    JavaCanonicalCallableIdentity,
    canonical_java_callable_identity,
    verify_java_callable_identity,
)

JAVA_PACKABILITY_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class JavaPackabilityBinding:
    proposal_id: str
    parser_node_id: str
    record_id: str
    identity: JavaCanonicalCallableIdentity
    semantic_content_hash: str
    source_location: str
    source_snapshot_hash: str
    dependency_references: tuple[str, ...]
    source_binding_id: str
    binding_hash: str


@dataclass(frozen=True)
class JavaPackabilityGroup:
    group_kind: str
    runtime_key: tuple[str, ...]
    proposal_ids: tuple[str, ...]
    identity_hashes: tuple[str, ...]
    semantic_content_hashes: tuple[str, ...]
    group_hash: str


@dataclass(frozen=True)
class JavaPackabilityReport:
    schema_version: int
    domain_id: str
    eligible_proposal_ids: tuple[str, ...]
    packable_proposal_ids: tuple[str, ...]
    bindings: tuple[JavaPackabilityBinding, ...]
    exact_references: tuple[tuple[str, str], ...]
    search_aliases: tuple[tuple[str, tuple[str, ...]], ...]
    legal_overload_groups: tuple[JavaPackabilityGroup, ...]
    duplicate_groups: tuple[JavaPackabilityGroup, ...]
    true_conflict_groups: tuple[JavaPackabilityGroup, ...]
    cross_root_binary_collisions: tuple[JavaPackabilityGroup, ...]
    unresolved_references: tuple[tuple[str, str], ...]
    ambiguous_exact_references: tuple[str, ...]
    withholding_reasons: tuple[tuple[str, str], ...]
    candidate_record_ids: tuple[str, ...]
    expected_source_bindings: tuple[tuple[str, str], ...]
    status: str
    report_hash: str


def build_java_packability_report(
    proposal_batch,
    source_index,
    release_identity,
    eligible_proposal_ids,
    *,
    domain_id: str,
) -> JavaPackabilityReport:
    nodes = {item.node_id: item for item in source_index.declarations}
    proposals = {item.proposal_id: item for item in proposal_batch.proposals}
    proposal_bindings = {item.proposal_id: item for item in proposal_batch.bindings}
    eligible = tuple(sorted(set(eligible_proposal_ids)))
    bindings = []
    by_runtime = defaultdict(list)
    by_physical = defaultdict(list)
    overloads = defaultdict(list)
    for proposal_id in eligible:
        proposal = proposals[proposal_id]
        declaration = nodes[proposal_bindings[proposal_id].parser_node_id]
        identity = canonical_java_callable_identity(declaration, release_identity)
        record_id = f"{domain_id}.knowledge.{identity.identity_hash[:32]}"
        semantic_hash = content_hash(asdict(proposal.proposed_content))
        location = (
            f"{declaration.source_unit_id}:"
            f"{declaration.declaration_span.byte_start}-"
            f"{declaration.declaration_span.byte_end}"
        )
        body = {
            "proposal_id": proposal_id,
            "parser_node_id": declaration.node_id,
            "record_id": record_id,
            "identity": identity,
            "semantic_content_hash": semantic_hash,
            "source_location": location,
            "source_snapshot_hash": declaration.source_snapshot_hash,
            "dependency_references": tuple(proposal.proposed_dependencies),
            "source_binding_id": f"source.{proposal.proposal_hash[:32]}",
        }
        binding = JavaPackabilityBinding(**body, binding_hash=content_hash(body))
        bindings.append(binding)
        by_runtime[identity.runtime_key].append(binding)
        physical = (location, declaration.source_snapshot_hash)
        by_physical[physical].append(binding)
        overloads[
            (
                identity.source_scope,
                identity.module_identity,
                identity.binary_receiver_identity,
                identity.callable_kind,
                identity.member_name,
            )
        ].append(binding)

    duplicates = []
    conflicts = []
    cross_roots = []
    blocked: dict[str, str] = {}
    for physical, values in sorted(by_physical.items()):
        if len(values) > 1:
            group = _group("DUPLICATE_PHYSICAL_PROPOSAL", physical, values)
            duplicates.append(group)
            blocked.update((item.proposal_id, group.group_kind) for item in values)
    for runtime_key, values in sorted(by_runtime.items()):
        if len(values) < 2:
            continue
        scopes = {item.identity.source_scope for item in values}
        contents = {item.semantic_content_hash for item in values}
        if len(scopes) > 1:
            group = _group("CROSS_SOURCE_BINARY_COLLISION", runtime_key, values)
            cross_roots.append(group)
        elif len(contents) == 1:
            group = _group("SAME_CANONICAL_IDENTITY_SAME_CONTENT", runtime_key, values)
            duplicates.append(group)
            blocked.update((item.proposal_id, group.group_kind) for item in values)
        else:
            group = _group(
                "SAME_CANONICAL_IDENTITY_DIFFERENT_CONTENT", runtime_key, values
            )
            conflicts.append(group)
            blocked.update((item.proposal_id, group.group_kind) for item in values)
    legal = []
    for key, values in sorted(overloads.items()):
        distinct = {item.identity.erased_parameter_descriptor for item in values}
        if len(distinct) > 1:
            legal.append(_group("LEGAL_OVERLOAD", key, values))

    packable = tuple(item for item in eligible if item not in blocked)
    by_id = {item.proposal_id: item for item in bindings}
    record_ids = tuple(sorted(by_id[item].record_id for item in packable))
    exact_map: dict[str, str] = {}
    ambiguous = set()
    search: dict[str, set[str]] = defaultdict(set)
    for proposal_id in packable:
        binding = by_id[proposal_id]
        identity = binding.identity
        proposal = proposals[proposal_id]
        exact_values = (proposal_id, identity.exact_reference, identity.identity_hash)
        for reference in exact_values:
            previous = exact_map.get(reference)
            if previous is not None and previous != binding.record_id:
                ambiguous.add(reference)
            exact_map[reference] = binding.record_id
        short = f"{identity.binary_receiver_identity}.{identity.member_name}".casefold()
        search[short].add(binding.record_id)
        source_parameters = ",".join(
            value for _name, value in proposal.proposed_content.parameters
        )
        search[f"{short}({source_parameters})".casefold()].add(binding.record_id)
        resolved_parameters = ",".join(
            proposal.proposed_content.resolved_parameter_types
        )
        exact_name = (
            f"{identity.binary_receiver_identity}.{identity.member_name}"
            f"({resolved_parameters})"
        )
        previous = exact_map.get(exact_name)
        if previous is not None and previous != binding.record_id:
            ambiguous.add(exact_name)
        exact_map[exact_name] = binding.record_id
    for reference in ambiguous:
        exact_map.pop(reference, None)
    unresolved = []
    for proposal_id in packable:
        for reference in by_id[proposal_id].dependency_references:
            if reference not in exact_map and reference not in proposals:
                unresolved.append((proposal_id, reference))
    # Duplicate and conflicting identities are closed by withholding every implicated
    # proposal.  The report is successful when the remaining namespace is non-empty
    # and exact-reference complete.
    status = "PASS" if packable and not (unresolved or ambiguous) else "FAIL"
    body = {
        "schema_version": JAVA_PACKABILITY_SCHEMA_VERSION,
        "domain_id": domain_id,
        "eligible_proposal_ids": eligible,
        "packable_proposal_ids": packable,
        "bindings": tuple(sorted(bindings, key=lambda item: item.proposal_id)),
        "exact_references": tuple(sorted(exact_map.items())),
        "search_aliases": tuple(
            (alias, tuple(sorted(values))) for alias, values in sorted(search.items())
        ),
        "legal_overload_groups": tuple(legal),
        "duplicate_groups": tuple(duplicates),
        "true_conflict_groups": tuple(conflicts),
        "cross_root_binary_collisions": tuple(cross_roots),
        "unresolved_references": tuple(sorted(unresolved)),
        "ambiguous_exact_references": tuple(sorted(ambiguous)),
        "withholding_reasons": tuple(sorted(blocked.items())),
        "candidate_record_ids": record_ids,
        "expected_source_bindings": tuple(
            (item, by_id[item].source_binding_id) for item in packable
        ),
        "status": status,
    }
    return JavaPackabilityReport(**body, report_hash=content_hash(body))


def verify_java_packability_report(
    report: JavaPackabilityReport,
    *,
    trusted_proposal_ids: tuple[str, ...] | None = None,
) -> None:
    """Rebuild the complete packability partition and namespace from the report."""

    body = asdict(report)
    claimed = body.pop("report_hash")
    eligible = report.eligible_proposal_ids
    packable = report.packable_proposal_ids
    bindings = report.bindings
    if (
        report.schema_version != JAVA_PACKABILITY_SCHEMA_VERSION
        or content_hash(body) != claimed
    ):
        raise ValueError("invalid Java packability report")
    if not report.domain_id or eligible != tuple(sorted(set(eligible))):
        raise ValueError("invalid Java packability eligible denominator")
    if packable != tuple(sorted(set(packable))) or not set(packable) <= set(eligible):
        raise ValueError("invalid Java packability candidate denominator")
    by_id = {item.proposal_id: item for item in bindings}
    if len(by_id) != len(bindings) or set(by_id) != set(eligible):
        raise ValueError("Java packability requires one binding per eligible proposal")
    for binding in bindings:
        binding_body = asdict(binding)
        binding_hash = binding_body.pop("binding_hash")
        verify_java_callable_identity(binding.identity)
        expected_record = (
            f"{report.domain_id}.knowledge.{binding.identity.identity_hash[:32]}"
        )
        if (
            content_hash(binding_body) != binding_hash
            or binding.record_id != expected_record
        ):
            raise ValueError("invalid Java packability binding identity")
    expected_groups, expected_blocked = _rebuild_groups(bindings)
    actual_groups = (
        report.legal_overload_groups,
        report.duplicate_groups,
        report.true_conflict_groups,
        report.cross_root_binary_collisions,
    )
    if actual_groups != expected_groups:
        raise ValueError("Java packability identity grouping mismatch")
    reasons = dict(report.withholding_reasons)
    if (
        len(reasons) != len(report.withholding_reasons)
        or reasons != expected_blocked
        or set(packable) != set(eligible) - set(reasons)
        or set(packable) & set(reasons)
    ):
        raise ValueError("Java packability partition or withholding reason mismatch")
    candidate_records = tuple(sorted(by_id[item].record_id for item in packable))
    if (
        report.candidate_record_ids != candidate_records
        or len(candidate_records) != len(set(candidate_records))
        or report.expected_source_bindings
        != tuple((item, by_id[item].source_binding_id) for item in packable)
    ):
        raise ValueError(
            "Java packability candidate/source binding denominator mismatch"
        )
    record_set = set(candidate_records)
    exact = dict(report.exact_references)
    if len(exact) != len(report.exact_references) or any(
        target not in record_set for target in exact.values()
    ):
        raise ValueError("Java packability exact reference target mismatch")
    for proposal_id in packable:
        binding = by_id[proposal_id]
        required = (
            proposal_id,
            binding.identity.identity_hash,
            binding.identity.exact_reference,
        )
        if any(exact.get(reference) != binding.record_id for reference in required):
            raise ValueError("Java packability exact reference closure mismatch")
    if any(
        target not in record_set
        for _alias, targets in report.search_aliases
        for target in targets
    ):
        raise ValueError("Java packability search alias target mismatch")
    if (
        report.ambiguous_exact_references
        != tuple(sorted(set(report.ambiguous_exact_references)))
        or set(report.ambiguous_exact_references) & set(exact)
        or report.unresolved_references
        != tuple(sorted(set(report.unresolved_references)))
    ):
        raise ValueError("Java packability unresolved/ambiguous reference mismatch")
    expected_status = (
        "PASS"
        if packable
        and not report.unresolved_references
        and not report.ambiguous_exact_references
        else "FAIL"
    )
    if report.status != expected_status:
        raise ValueError("Java packability status derivation mismatch")
    if (
        trusted_proposal_ids is not None
        and tuple(sorted(trusted_proposal_ids)) != packable
    ):
        raise ValueError("final Java trust is not exactly the packable set")


def _rebuild_groups(bindings):
    by_runtime = defaultdict(list)
    by_physical = defaultdict(list)
    overloads = defaultdict(list)
    for binding in bindings:
        identity = binding.identity
        by_runtime[identity.runtime_key].append(binding)
        by_physical[
            (
                binding.source_location,
                binding.source_snapshot_hash,
            )
        ].append(binding)
        overloads[
            (
                identity.source_scope,
                identity.module_identity,
                identity.binary_receiver_identity,
                identity.callable_kind,
                identity.member_name,
            )
        ].append(binding)
    duplicate = []
    conflict = []
    cross_root = []
    blocked = {}
    for physical, values in sorted(by_physical.items()):
        if len(values) > 1:
            group = _group("DUPLICATE_PHYSICAL_PROPOSAL", physical, values)
            duplicate.append(group)
            blocked.update((item.proposal_id, group.group_kind) for item in values)
    for runtime_key, values in sorted(by_runtime.items()):
        if len(values) < 2:
            continue
        scopes = {item.identity.source_scope for item in values}
        contents = {item.semantic_content_hash for item in values}
        if len(scopes) > 1:
            cross_root.append(
                _group("CROSS_SOURCE_BINARY_COLLISION", runtime_key, values)
            )
        elif len(contents) == 1:
            group = _group("SAME_CANONICAL_IDENTITY_SAME_CONTENT", runtime_key, values)
            duplicate.append(group)
            blocked.update((item.proposal_id, group.group_kind) for item in values)
        else:
            group = _group(
                "SAME_CANONICAL_IDENTITY_DIFFERENT_CONTENT", runtime_key, values
            )
            conflict.append(group)
            blocked.update((item.proposal_id, group.group_kind) for item in values)
    legal = []
    for key, values in sorted(overloads.items()):
        if len({item.identity.erased_parameter_descriptor for item in values}) > 1:
            legal.append(_group("LEGAL_OVERLOAD", key, values))
    groups = (tuple(legal), tuple(duplicate), tuple(conflict), tuple(cross_root))
    for values in groups:
        for group in values:
            group_body = asdict(group)
            group_hash = group_body.pop("group_hash")
            if content_hash(group_body) != group_hash:
                raise ValueError("invalid Java packability group hash")
    return groups, blocked


def _group(kind, key, values):
    body = {
        "group_kind": kind,
        "runtime_key": tuple(key),
        "proposal_ids": tuple(sorted(item.proposal_id for item in values)),
        "identity_hashes": tuple(
            sorted({item.identity.identity_hash for item in values})
        ),
        "semantic_content_hashes": tuple(
            sorted({item.semantic_content_hash for item in values})
        ),
    }
    return JavaPackabilityGroup(**body, group_hash=content_hash(body))
