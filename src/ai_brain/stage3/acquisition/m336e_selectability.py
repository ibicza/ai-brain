"""Production-anchored selectability census and exact feasibility proof."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336e_identity import (
    CanonicalVaultPath,
    SourceEntryBindingManifest,
    SourceEntryId,
    source_entry_id_from_dict,
    verify_source_entry_binding_manifest,
    verify_source_entry_id,
)
from ai_brain.stage3.acquisition.m336e_protocol import RunProtocolLedger

M336E_SELECTABILITY_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SelectableSourceDecision:
    schema_version: int
    source_entry_id: SourceEntryId
    candidate_root: str
    canonical_path: str
    analysis_eligible: bool
    publication_allowed: bool
    source_use_receipt_valid: bool
    scoped_license_resolved: bool
    scm_correspondence_complete: bool
    parser_status: str
    declaration_count: int
    callable_declaration_count: int
    supported_callable_declaration_count: int
    construct_classes: tuple[str, ...]
    evidence_policy_path_declared: bool
    blocker_reasons: tuple[str, ...]
    selectable: bool
    decision_hash: str


def build_selectable_source_decision(
    *,
    source_entry_id: SourceEntryId,
    candidate_root: str,
    canonical_path: str,
    analysis_eligible: bool,
    publication_allowed: bool,
    source_use_receipt_valid: bool,
    scoped_license_resolved: bool,
    scm_correspondence_complete: bool,
    parser_status: str,
    declaration_count: int,
    callable_declaration_count: int,
    supported_callable_declaration_count: int,
    construct_classes,
    evidence_policy_path_declared: bool,
) -> SelectableSourceDecision:
    verify_source_entry_id(source_entry_id)
    canonical = CanonicalVaultPath.parse(canonical_path).canonical_posix_path
    if candidate_root != source_entry_id.candidate_family_id:
        raise ValueError("selectability root differs from SourceEntryId family")
    counts = (
        declaration_count,
        callable_declaration_count,
        supported_callable_declaration_count,
    )
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in counts
    ):
        raise ValueError(
            "selectability declaration counts must be non-negative integers"
        )
    if not (
        supported_callable_declaration_count
        <= callable_declaration_count
        <= declaration_count
    ):
        raise ValueError("selectability declaration denominators are inconsistent")
    classes = tuple(
        sorted(set(construct_classes), key=lambda value: value.encode("utf-8"))
    )
    if any(not value for value in classes):
        raise ValueError("selectability construct class is empty")
    reasons = []
    checks = (
        (analysis_eligible, "CANDIDATE_NOT_ANALYSIS_ELIGIBLE"),
        (publication_allowed, "DERIVED_OR_METRICS_PUBLICATION_NOT_ALLOWED"),
        (source_use_receipt_valid, "SOURCE_USE_RECEIPT_INVALID"),
        (scoped_license_resolved, "SCOPED_LICENSE_UNRESOLVED"),
        (scm_correspondence_complete, "SCM_CORRESPONDENCE_INCOMPLETE"),
        (parser_status == "PASS", "EXACT_PARSER_FAILED"),
        (declaration_count > 0, "NO_PRODUCTION_DECLARATION"),
        (callable_declaration_count > 0, "NO_CALLABLE_DECLARATION"),
        (
            supported_callable_declaration_count > 0,
            "NO_PRODUCTION_SUPPORTED_CALLABLE_DECLARATION",
        ),
        (evidence_policy_path_declared, "NO_PRODUCTION_EVIDENCE_POLICY_PATH"),
    )
    reasons.extend(reason for passed, reason in checks if not passed)
    body = {
        "schema_version": M336E_SELECTABILITY_SCHEMA_VERSION,
        "source_entry_id": source_entry_id,
        "candidate_root": candidate_root,
        "canonical_path": canonical,
        "analysis_eligible": analysis_eligible,
        "publication_allowed": publication_allowed,
        "source_use_receipt_valid": source_use_receipt_valid,
        "scoped_license_resolved": scoped_license_resolved,
        "scm_correspondence_complete": scm_correspondence_complete,
        "parser_status": parser_status,
        "declaration_count": declaration_count,
        "callable_declaration_count": callable_declaration_count,
        "supported_callable_declaration_count": supported_callable_declaration_count,
        "construct_classes": classes,
        "evidence_policy_path_declared": evidence_policy_path_declared,
        "blocker_reasons": tuple(reasons),
        "selectable": not reasons,
    }
    return SelectableSourceDecision(**body, decision_hash=content_hash(body))


def verify_selectable_source_decision(value: SelectableSourceDecision) -> None:
    rebuilt = build_selectable_source_decision(
        source_entry_id=value.source_entry_id,
        candidate_root=value.candidate_root,
        canonical_path=value.canonical_path,
        analysis_eligible=value.analysis_eligible,
        publication_allowed=value.publication_allowed,
        source_use_receipt_valid=value.source_use_receipt_valid,
        scoped_license_resolved=value.scoped_license_resolved,
        scm_correspondence_complete=value.scm_correspondence_complete,
        parser_status=value.parser_status,
        declaration_count=value.declaration_count,
        callable_declaration_count=value.callable_declaration_count,
        supported_callable_declaration_count=value.supported_callable_declaration_count,
        construct_classes=value.construct_classes,
        evidence_policy_path_declared=value.evidence_policy_path_declared,
    )
    if rebuilt != value:
        raise ValueError("selectability decision does not match its evidence")


def selectable_source_decision_from_dict(value: dict) -> SelectableSourceDecision:
    """Deserialize a census decision without accepting recursive schema drift."""

    expected = {
        "schema_version",
        "source_entry_id",
        "candidate_root",
        "canonical_path",
        "analysis_eligible",
        "publication_allowed",
        "source_use_receipt_valid",
        "scoped_license_resolved",
        "scm_correspondence_complete",
        "parser_status",
        "declaration_count",
        "callable_declaration_count",
        "supported_callable_declaration_count",
        "construct_classes",
        "evidence_policy_path_declared",
        "blocker_reasons",
        "selectable",
        "decision_hash",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("selectability decision fields differ from the frozen schema")
    result = SelectableSourceDecision(
        **{
            **value,
            "source_entry_id": source_entry_id_from_dict(value["source_entry_id"]),
            "construct_classes": tuple(value["construct_classes"]),
            "blocker_reasons": tuple(value["blocker_reasons"]),
        }
    )
    verify_selectable_source_decision(result)
    return result


@dataclass(frozen=True)
class SelectableRootCensus:
    candidate_root: str
    analysis_eligible_file_count: int
    parser_valid_file_count: int
    callable_file_count: int
    production_supported_file_count: int
    selectable_file_count: int
    construct_file_counts: tuple[tuple[str, int], ...]
    census_hash: str


@dataclass(frozen=True)
class SelectableSourceCensus:
    schema_version: int
    decisions: tuple[SelectableSourceDecision, ...]
    roots: tuple[SelectableRootCensus, ...]
    file_count: int
    analysis_eligible_file_count: int
    parser_valid_file_count: int
    callable_file_count: int
    production_supported_file_count: int
    selectable_file_count: int
    selectable_root_count: int
    rejected_by_reason: tuple[tuple[str, int], ...]
    decision_manifest_hash: str
    census_hash: str


def build_selectable_source_census(decisions) -> SelectableSourceCensus:
    values = tuple(decisions)
    for decision in values:
        verify_selectable_source_decision(decision)
    if len({item.source_entry_id.identity_hash for item in values}) != len(values):
        raise ValueError("selectability census contains a duplicate SourceEntryId")
    if len(
        {(item.candidate_root, item.canonical_path.casefold()) for item in values}
    ) != len(values):
        raise ValueError("selectability census contains a logical path collision")
    ordered = tuple(
        sorted(
            values, key=lambda item: bytes.fromhex(item.source_entry_id.identity_hash)
        )
    )
    roots = []
    for name in sorted(
        {item.candidate_root for item in ordered},
        key=lambda value: value.encode("utf-8"),
    ):
        rows = tuple(item for item in ordered if item.candidate_root == name)
        constructs = tuple(
            (construct, sum(construct in item.construct_classes for item in rows))
            for construct in sorted(
                {value for item in rows for value in item.construct_classes},
                key=lambda value: value.encode("utf-8"),
            )
        )
        root_body = {
            "candidate_root": name,
            "analysis_eligible_file_count": sum(
                item.analysis_eligible for item in rows
            ),
            "parser_valid_file_count": sum(
                item.parser_status == "PASS" for item in rows
            ),
            "callable_file_count": sum(
                item.callable_declaration_count > 0 for item in rows
            ),
            "production_supported_file_count": sum(
                item.supported_callable_declaration_count > 0 for item in rows
            ),
            "selectable_file_count": sum(item.selectable for item in rows),
            "construct_file_counts": constructs,
        }
        roots.append(
            SelectableRootCensus(**root_body, census_hash=content_hash(root_body))
        )
    reasons = tuple(
        (reason, sum(reason in item.blocker_reasons for item in ordered))
        for reason in sorted(
            {value for item in ordered for value in item.blocker_reasons},
            key=lambda value: value.encode("utf-8"),
        )
    )
    decision_manifest = tuple(
        (item.source_entry_id.identity_hash, item.decision_hash) for item in ordered
    )
    body = {
        "schema_version": M336E_SELECTABILITY_SCHEMA_VERSION,
        "decisions": ordered,
        "roots": tuple(roots),
        "file_count": len(ordered),
        "analysis_eligible_file_count": sum(item.analysis_eligible for item in ordered),
        "parser_valid_file_count": sum(
            item.parser_status == "PASS" for item in ordered
        ),
        "callable_file_count": sum(
            item.callable_declaration_count > 0 for item in ordered
        ),
        "production_supported_file_count": sum(
            item.supported_callable_declaration_count > 0 for item in ordered
        ),
        "selectable_file_count": sum(item.selectable for item in ordered),
        "selectable_root_count": sum(root.selectable_file_count > 0 for root in roots),
        "rejected_by_reason": reasons,
        "decision_manifest_hash": content_hash(decision_manifest),
    }
    return SelectableSourceCensus(**body, census_hash=content_hash(body))


def verify_selectable_source_census(value: SelectableSourceCensus) -> None:
    if build_selectable_source_census(value.decisions) != value:
        raise ValueError("selectability census does not match its decisions")


def selectable_source_census_from_dict(value: dict) -> SelectableSourceCensus:
    """Deserialize and rebuild a sealed selectability census."""

    expected = {
        "schema_version",
        "decisions",
        "roots",
        "file_count",
        "analysis_eligible_file_count",
        "parser_valid_file_count",
        "callable_file_count",
        "production_supported_file_count",
        "selectable_file_count",
        "selectable_root_count",
        "rejected_by_reason",
        "decision_manifest_hash",
        "census_hash",
    }
    root_fields = {
        "candidate_root",
        "analysis_eligible_file_count",
        "parser_valid_file_count",
        "callable_file_count",
        "production_supported_file_count",
        "selectable_file_count",
        "construct_file_counts",
        "census_hash",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("selectability census fields differ from the frozen schema")
    if not isinstance(value["decisions"], list | tuple) or not isinstance(
        value["roots"], list | tuple
    ):
        raise TypeError("selectability census rows must be arrays")
    roots = []
    for item in value["roots"]:
        if not isinstance(item, dict) or set(item) != root_fields:
            raise ValueError("selectable root census fields differ from the schema")
        roots.append(
            SelectableRootCensus(
                **{
                    **item,
                    "construct_file_counts": tuple(
                        tuple(row) for row in item["construct_file_counts"]
                    ),
                }
            )
        )
    result = SelectableSourceCensus(
        **{
            **value,
            "decisions": tuple(
                selectable_source_decision_from_dict(item)
                for item in value["decisions"]
            ),
            "roots": tuple(roots),
            "rejected_by_reason": tuple(
                tuple(row) for row in value["rejected_by_reason"]
            ),
        }
    )
    verify_selectable_source_census(result)
    return result


@dataclass(frozen=True)
class SelectorFeasibilityProof:
    schema_version: int
    census_hash: str
    target_file_count: int
    maximum_files_per_root: int
    minimum_root_count: int
    selectable_file_count: int
    selectable_root_count: int
    balanced_capacity: int
    construct_quotas: tuple[tuple[str, int], ...]
    hard_requirements_satisfied: bool
    infeasibility_reasons: tuple[str, ...]
    witness_root_allocation: tuple[tuple[str, int], ...]
    witness_construct_counts: tuple[tuple[str, int], ...]
    proof_hash: str


def prove_selector_feasibility(
    census: SelectableSourceCensus,
    *,
    target_file_count: int = 180,
    maximum_files_per_root: int = 63,
    minimum_root_count: int = 3,
    construct_quotas=(),
) -> SelectorFeasibilityProof:
    if target_file_count <= 0 or maximum_files_per_root <= 0 or minimum_root_count <= 0:
        raise ValueError("selector feasibility policy must be positive")
    quotas = tuple(sorted(construct_quotas, key=lambda item: item[0].encode("utf-8")))
    if len({name for name, _count in quotas}) != len(quotas) or any(
        not name or not isinstance(count, int) or isinstance(count, bool) or count < 0
        for name, count in quotas
    ):
        raise ValueError("construct quotas are invalid")
    selectable = tuple(item for item in census.decisions if item.selectable)
    by_root = {
        root.candidate_root: tuple(
            item for item in selectable if item.candidate_root == root.candidate_root
        )
        for root in census.roots
        if root.selectable_file_count
    }
    balanced = sum(min(len(rows), maximum_files_per_root) for rows in by_root.values())
    reasons = []
    if len(by_root) < minimum_root_count:
        reasons.append("SELECTABLE_ROOT_COUNT_BELOW_MINIMUM")
    if len(selectable) < target_file_count:
        reasons.append("SELECTABLE_FILE_COUNT_BELOW_TARGET")
    if balanced < target_file_count:
        reasons.append("BALANCED_CAPACITY_BELOW_TARGET")
    available_constructs = {
        name: sum(name in item.construct_classes for item in selectable)
        for name, _count in quotas
    }
    reasons.extend(
        f"CONSTRUCT_QUOTA_UNAVAILABLE:{name}"
        for name, count in quotas
        if available_constructs[name] < count
    )
    allocation: tuple[tuple[str, int], ...] = ()
    witness_counts: tuple[tuple[str, int], ...] = ()
    if not reasons:
        witness = _exact_aggregate_witness(
            by_root,
            target=target_file_count,
            cap=maximum_files_per_root,
            minimum_roots=minimum_root_count,
            quotas=quotas,
        )
        if witness is None:
            reasons.append("SIMULTANEOUS_ROOT_AND_CONSTRUCT_CONSTRAINTS_INFEASIBLE")
        else:
            allocation, quota_values = witness
            witness_counts = tuple(
                (name, quota_values[index])
                for index, (name, _count) in enumerate(quotas)
            )
    body = {
        "schema_version": M336E_SELECTABILITY_SCHEMA_VERSION,
        "census_hash": census.census_hash,
        "target_file_count": target_file_count,
        "maximum_files_per_root": maximum_files_per_root,
        "minimum_root_count": minimum_root_count,
        "selectable_file_count": len(selectable),
        "selectable_root_count": len(by_root),
        "balanced_capacity": balanced,
        "construct_quotas": quotas,
        "hard_requirements_satisfied": not reasons,
        "infeasibility_reasons": tuple(reasons),
        "witness_root_allocation": allocation,
        "witness_construct_counts": witness_counts,
    }
    return SelectorFeasibilityProof(**body, proof_hash=content_hash(body))


def verify_selector_feasibility_proof(
    census: SelectableSourceCensus, proof: SelectorFeasibilityProof
) -> None:
    rebuilt = prove_selector_feasibility(
        census,
        target_file_count=proof.target_file_count,
        maximum_files_per_root=proof.maximum_files_per_root,
        minimum_root_count=proof.minimum_root_count,
        construct_quotas=proof.construct_quotas,
    )
    if rebuilt != proof:
        raise ValueError("selector feasibility proof does not match the census")


def selector_feasibility_proof_from_dict(
    value: dict, census: SelectableSourceCensus
) -> SelectorFeasibilityProof:
    """Deserialize and exactly recompute an aggregate feasibility proof."""

    expected = {
        "schema_version",
        "census_hash",
        "target_file_count",
        "maximum_files_per_root",
        "minimum_root_count",
        "selectable_file_count",
        "selectable_root_count",
        "balanced_capacity",
        "construct_quotas",
        "hard_requirements_satisfied",
        "infeasibility_reasons",
        "witness_root_allocation",
        "witness_construct_counts",
        "proof_hash",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("selector feasibility fields differ from the frozen schema")
    result = SelectorFeasibilityProof(
        **{
            **value,
            "construct_quotas": tuple(tuple(row) for row in value["construct_quotas"]),
            "infeasibility_reasons": tuple(value["infeasibility_reasons"]),
            "witness_root_allocation": tuple(
                tuple(row) for row in value["witness_root_allocation"]
            ),
            "witness_construct_counts": tuple(
                tuple(row) for row in value["witness_construct_counts"]
            ),
        }
    )
    verify_selector_feasibility_proof(census, result)
    return result


def _exact_aggregate_witness(by_root, *, target, cap, minimum_roots, quotas):
    quota_names = tuple(name for name, _count in quotas)
    quota_limits = tuple(count for _name, count in quotas)
    global_states: dict[
        tuple[int, int, tuple[int, ...]], tuple[tuple[str, int], ...]
    ] = {(0, 0, (0,) * len(quotas)): ()}
    for root in sorted(by_root, key=lambda value: value.encode("utf-8")):
        root_states = _root_aggregate_states(
            by_root[root],
            cap=min(cap, target),
            quota_names=quota_names,
            quota_limits=quota_limits,
        )
        updated = dict(global_states)
        for (total, used_roots, counts), allocation in global_states.items():
            for selected, contributions in root_states:
                if selected == 0 or total + selected > target:
                    continue
                merged = tuple(
                    min(limit, left + right)
                    for left, right, limit in zip(
                        counts, contributions, quota_limits, strict=True
                    )
                )
                key = (total + selected, used_roots + 1, merged)
                candidate = (*allocation, (root, selected))
                current = updated.get(key)
                if current is None or candidate < current:
                    updated[key] = candidate
        global_states = updated
    candidates = [
        (key, allocation)
        for key, allocation in global_states.items()
        if key[0] == target
        and key[1] >= minimum_roots
        and all(
            value >= limit for value, limit in zip(key[2], quota_limits, strict=True)
        )
    ]
    if not candidates:
        return None
    key, allocation = min(candidates, key=lambda item: (item[1], item[0]))
    return allocation, key[2]


def _root_aggregate_states(rows, *, cap, quota_names, quota_limits):
    states = {(0, (0,) * len(quota_names))}
    for row in rows:
        contribution = tuple(name in row.construct_classes for name in quota_names)
        additions = set()
        for selected, counts in states:
            if selected >= cap:
                continue
            additions.add(
                (
                    selected + 1,
                    tuple(
                        min(limit, value + int(add))
                        for value, add, limit in zip(
                            counts, contribution, quota_limits, strict=True
                        )
                    ),
                )
            )
        states.update(additions)
        states = _pareto_states(states)
    return tuple(sorted(states))


def _pareto_states(states):
    by_selected = {}
    for selected, counts in states:
        candidates = by_selected.setdefault(selected, [])
        if any(
            all(a >= b for a, b in zip(prior, counts, strict=True))
            for prior in candidates
        ):
            continue
        candidates[:] = [
            prior
            for prior in candidates
            if not all(a >= b for a, b in zip(counts, prior, strict=True))
        ]
        candidates.append(counts)
    return {
        (selected, counts)
        for selected, candidates in by_selected.items()
        for counts in candidates
    }


@dataclass(frozen=True)
class SelectedSourceRow:
    source_entry_identity_hash: str
    candidate_root: str
    canonical_path: str
    selected_path: str
    production_document_identity: str
    selection_rank: str
    row_hash: str


@dataclass(frozen=True)
class SelectedSourceManifest:
    schema_version: int
    census_hash: str
    feasibility_proof_hash: str
    binding_manifest_hash: str
    file_count: int
    root_count: int
    root_distribution: tuple[tuple[str, int], ...]
    files: tuple[SelectedSourceRow, ...]
    manifest_hash: str


@dataclass(frozen=True)
class SelectorReceipt:
    schema_version: int
    selector_version: str
    selector_seed: str
    f20_sha: str
    census_hash: str
    feasibility_proof_hash: str
    binding_manifest_hash: str
    selector_invocation_count: int
    selector_rerun_count: int
    selected_file_count: int
    selected_root_count: int
    maximum_one_root_count: int
    evaluator_read_count: int
    golden_read_count: int
    trust_metric_read_count: int
    selected_manifest_hash: str
    root_distribution: tuple[tuple[str, int], ...]
    receipt_hash: str


def selected_source_manifest_from_dict(value: dict) -> SelectedSourceManifest:
    """Deserialize a selector result without invoking the selector."""

    expected = {
        "schema_version",
        "census_hash",
        "feasibility_proof_hash",
        "binding_manifest_hash",
        "file_count",
        "root_count",
        "root_distribution",
        "files",
        "manifest_hash",
    }
    row_fields = {
        "source_entry_identity_hash",
        "candidate_root",
        "canonical_path",
        "selected_path",
        "production_document_identity",
        "selection_rank",
        "row_hash",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("selected manifest fields differ from the frozen schema")
    rows = []
    for item in value["files"]:
        if not isinstance(item, dict) or set(item) != row_fields:
            raise ValueError("selected source row fields differ from the frozen schema")
        rows.append(SelectedSourceRow(**item))
    return SelectedSourceManifest(
        **{
            **value,
            "root_distribution": tuple(
                tuple(row) for row in value["root_distribution"]
            ),
            "files": tuple(rows),
        }
    )


def selector_receipt_from_dict(value: dict) -> SelectorReceipt:
    """Deserialize a selector receipt with exact top-level fields."""

    expected = {item.name for item in SelectorReceipt.__dataclass_fields__.values()}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("selector receipt fields differ from the frozen schema")
    return SelectorReceipt(
        **{
            **value,
            "root_distribution": tuple(
                tuple(row) for row in value["root_distribution"]
            ),
        }
    )


def verify_selector_result_without_invocation(
    census: SelectableSourceCensus,
    proof: SelectorFeasibilityProof,
    bindings: SourceEntryBindingManifest,
    manifest: SelectedSourceManifest,
    receipt: SelectorReceipt,
) -> None:
    """Verify a remote selector result without reserving or selecting again.

    This intentionally does not call ``_rank_and_select``.  It proves that every
    transferred row is selectable, hash-bound, path-bound, quota-compliant and
    covered by the signed-style receipt.  The originating host remains the only
    host that consumes the one-shot selector reservation.
    """

    verify_selectable_source_census(census)
    verify_selector_feasibility_proof(census, proof)
    verify_source_entry_binding_manifest(bindings)
    if not proof.hard_requirements_satisfied:
        raise ValueError("selector result cannot follow an infeasible proof")
    decisions = {
        item.source_entry_id.identity_hash: item
        for item in census.decisions
        if item.selectable
    }
    binding_by_identity = {
        item.source_entry_id.identity_hash: item for item in bindings.bindings
    }
    identities = []
    selected_paths = []
    documents = []
    ranks = []
    for row in manifest.files:
        body = asdict(row)
        claimed = body.pop("row_hash")
        decision = decisions.get(row.source_entry_identity_hash)
        binding = binding_by_identity.get(row.source_entry_identity_hash)
        if decision is None or binding is None:
            raise ValueError("selected source is not census-selectable and path-bound")
        if (
            content_hash(body) != claimed
            or CanonicalVaultPath.parse(row.canonical_path).canonical_posix_path
            != row.canonical_path
            or CanonicalVaultPath.parse(row.selected_path).canonical_posix_path
            != row.selected_path
            or row.candidate_root != decision.candidate_root
            or row.canonical_path != decision.canonical_path
            or row.selected_path != binding.selected_path
            or row.production_document_identity != binding.production_document_identity
            or row.selection_rank
            != content_hash(
                (
                    receipt.f20_sha,
                    receipt.selector_seed,
                    row.candidate_root,
                    row.canonical_path,
                    row.source_entry_identity_hash,
                )
            )
        ):
            raise ValueError("selected source row is not bound to its sealed inputs")
        identities.append(row.source_entry_identity_hash)
        selected_paths.append(row.selected_path)
        documents.append(row.production_document_identity)
        ranks.append(row.selection_rank)
    if any(
        len(set(values)) != len(values)
        for values in (identities, selected_paths, documents, ranks)
    ):
        raise ValueError("selector result contains a duplicate identity or path")
    if (
        tuple(sorted(manifest.files, key=lambda row: row.selected_path.encode("utf-8")))
        != manifest.files
    ):
        raise ValueError("selected source rows use non-canonical ordering")
    distribution = tuple(
        (root, sum(row.candidate_root == root for row in manifest.files))
        for root in sorted(
            {row.candidate_root for row in manifest.files},
            key=lambda value: value.encode("utf-8"),
        )
    )
    manifest_body = asdict(manifest)
    manifest_claim = manifest_body.pop("manifest_hash")
    selected_decisions = tuple(decisions[identity] for identity in identities)
    if (
        manifest.schema_version != M336E_SELECTABILITY_SCHEMA_VERSION
        or manifest.census_hash != census.census_hash
        or manifest.feasibility_proof_hash != proof.proof_hash
        or manifest.binding_manifest_hash != bindings.manifest_hash
        or manifest.file_count != len(manifest.files)
        or manifest.file_count != proof.target_file_count
        or manifest.root_count != len(distribution)
        or manifest.root_count < proof.minimum_root_count
        or manifest.root_distribution != distribution
        or max(count for _root, count in distribution) > proof.maximum_files_per_root
        or any(
            sum(name in item.construct_classes for item in selected_decisions)
            < required
            for name, required in proof.construct_quotas
        )
        or content_hash(manifest_body) != manifest_claim
    ):
        raise ValueError("selected source manifest invariants failed")
    receipt_body = asdict(receipt)
    receipt_claim = receipt_body.pop("receipt_hash")
    if (
        receipt.schema_version != M336E_SELECTABILITY_SCHEMA_VERSION
        or not receipt.selector_version
        or not receipt.selector_seed
        or len(receipt.f20_sha) != 40
        or any(character not in "0123456789abcdef" for character in receipt.f20_sha)
        or receipt.census_hash != census.census_hash
        or receipt.feasibility_proof_hash != proof.proof_hash
        or receipt.binding_manifest_hash != bindings.manifest_hash
        or receipt.selector_invocation_count != 1
        or receipt.selector_rerun_count != 0
        or receipt.selected_file_count != manifest.file_count
        or receipt.selected_root_count != manifest.root_count
        or receipt.maximum_one_root_count != max(count for _root, count in distribution)
        or receipt.evaluator_read_count != 0
        or receipt.golden_read_count != 0
        or receipt.trust_metric_read_count != 0
        or receipt.selected_manifest_hash != manifest.manifest_hash
        or receipt.root_distribution != distribution
        or content_hash(receipt_body) != receipt_claim
    ):
        raise ValueError("selector receipt invariants failed")


def select_final_sources_once(
    census: SelectableSourceCensus,
    proof: SelectorFeasibilityProof,
    bindings: SourceEntryBindingManifest,
    ledger: RunProtocolLedger,
    *,
    f20_sha: str,
    acquisition_run_id: str,
    candidate_pool_hash: str,
    vault_tree_hash: str,
    qualification_manifest_hash: str,
    selector_seed: str,
    selectability_census_hash: str | None = None,
    selector_version: str = "m336e.production-supported-selector.v1",
) -> tuple[SelectedSourceManifest, SelectorReceipt]:
    """Reserve only after a sealed feasible proof, then invoke exactly once."""

    verify_selector_feasibility_proof(census, proof)
    verify_source_entry_binding_manifest(bindings)
    if not proof.hard_requirements_satisfied:
        raise ValueError("selector cannot be reserved for an infeasible census")
    if (
        selectability_census_hash is not None
        and selectability_census_hash != census.census_hash
    ):
        raise ValueError("selector request contains a wrong census hash")
    binding_by_id = {
        item.source_entry_id.identity_hash: item for item in bindings.bindings
    }
    candidates = tuple(item for item in census.decisions if item.selectable)
    if {item.source_entry_id.identity_hash for item in candidates} - set(binding_by_id):
        raise ValueError("selectable source lacks an explicit path-domain binding")
    context = {
        "f20_sha": f20_sha,
        "acquisition_run_id": acquisition_run_id,
        "candidate_pool_hash": candidate_pool_hash,
        "vault_tree_hash": vault_tree_hash,
        "qualification_manifest_hash": qualification_manifest_hash,
        "selectability_census_hash": census.census_hash,
    }
    ledger.append("SELECTOR_INVOCATION_RESERVED", **context)
    selected = _rank_and_select(candidates, proof, selector_seed, f20_sha)
    rows = []
    for decision, rank in selected:
        binding = binding_by_id[decision.source_entry_id.identity_hash]
        row_body = {
            "source_entry_identity_hash": decision.source_entry_id.identity_hash,
            "candidate_root": decision.candidate_root,
            "canonical_path": decision.canonical_path,
            "selected_path": binding.selected_path,
            "production_document_identity": binding.production_document_identity,
            "selection_rank": rank,
        }
        rows.append(SelectedSourceRow(**row_body, row_hash=content_hash(row_body)))
    ordered_rows = tuple(
        sorted(rows, key=lambda item: item.selected_path.encode("utf-8"))
    )
    distribution = tuple(
        (root, sum(item.candidate_root == root for item in ordered_rows))
        for root in sorted(
            {item.candidate_root for item in ordered_rows},
            key=lambda value: value.encode("utf-8"),
        )
    )
    manifest_body = {
        "schema_version": M336E_SELECTABILITY_SCHEMA_VERSION,
        "census_hash": census.census_hash,
        "feasibility_proof_hash": proof.proof_hash,
        "binding_manifest_hash": bindings.manifest_hash,
        "file_count": len(ordered_rows),
        "root_count": len(distribution),
        "root_distribution": distribution,
        "files": ordered_rows,
    }
    manifest = SelectedSourceManifest(
        **manifest_body, manifest_hash=content_hash(manifest_body)
    )
    receipt_body = {
        "schema_version": M336E_SELECTABILITY_SCHEMA_VERSION,
        "selector_version": selector_version,
        "selector_seed": selector_seed,
        "f20_sha": f20_sha,
        "census_hash": census.census_hash,
        "feasibility_proof_hash": proof.proof_hash,
        "binding_manifest_hash": bindings.manifest_hash,
        "selector_invocation_count": 1,
        "selector_rerun_count": 0,
        "selected_file_count": len(ordered_rows),
        "selected_root_count": len(distribution),
        "maximum_one_root_count": max(count for _root, count in distribution),
        "evaluator_read_count": 0,
        "golden_read_count": 0,
        "trust_metric_read_count": 0,
        "selected_manifest_hash": manifest.manifest_hash,
        "root_distribution": distribution,
    }
    receipt = SelectorReceipt(**receipt_body, receipt_hash=content_hash(receipt_body))
    ledger.append("SELECTOR_COMPLETED", **context)
    return manifest, receipt


def _rank_and_select(candidates, proof, seed, f20_sha):
    ranked = tuple(
        sorted(
            (
                (
                    content_hash(
                        (
                            f20_sha,
                            seed,
                            item.candidate_root,
                            item.canonical_path,
                            item.source_entry_id.identity_hash,
                        )
                    ),
                    item,
                )
                for item in candidates
            ),
            key=lambda pair: (pair[0], pair[1].source_entry_id.identity_hash),
        )
    )
    selected: list[tuple[SelectableSourceDecision, str]] = []
    selected_ids = set()
    counts = {item.candidate_root: 0 for item in candidates}

    def add(rank, item):
        identity = item.source_entry_id.identity_hash
        if (
            identity in selected_ids
            or counts[item.candidate_root] >= proof.maximum_files_per_root
        ):
            return False
        selected.append((item, rank))
        selected_ids.add(identity)
        counts[item.candidate_root] += 1
        return True

    root_order = sorted(
        counts,
        key=lambda root: next(
            rank for rank, item in ranked if item.candidate_root == root
        ),
    )
    for root in root_order[: proof.minimum_root_count]:
        rank, item = next(
            (rank, item) for rank, item in ranked if item.candidate_root == root
        )
        add(rank, item)
    for construct, required in proof.construct_quotas:
        while (
            sum(construct in item.construct_classes for item, _rank in selected)
            < required
        ):
            choice = next(
                (
                    (rank, item)
                    for rank, item in ranked
                    if construct in item.construct_classes
                    and item.source_entry_id.identity_hash not in selected_ids
                    and counts[item.candidate_root] < proof.maximum_files_per_root
                ),
                None,
            )
            if choice is None:
                raise ValueError(
                    "selector ranking cannot realize a proven construct quota"
                )
            add(*choice)
    queues = {
        root: [(rank, item) for rank, item in ranked if item.candidate_root == root]
        for root in root_order
    }
    while len(selected) < proof.target_file_count:
        progressed = False
        for root in root_order:
            while (
                queues[root]
                and queues[root][0][1].source_entry_id.identity_hash in selected_ids
            ):
                queues[root].pop(0)
            if not queues[root] or counts[root] >= proof.maximum_files_per_root:
                continue
            rank, item = queues[root].pop(0)
            progressed = add(rank, item) or progressed
            if len(selected) == proof.target_file_count:
                break
        if not progressed:
            raise ValueError("selector ranking exhausted before the proven target")
    if (
        len({item.candidate_root for item, _rank in selected})
        < proof.minimum_root_count
        or max(counts.values()) > proof.maximum_files_per_root
        or any(
            sum(name in item.construct_classes for item, _rank in selected) < required
            for name, required in proof.construct_quotas
        )
    ):
        raise ValueError("selector result violates the sealed feasibility policy")
    return tuple(selected)
