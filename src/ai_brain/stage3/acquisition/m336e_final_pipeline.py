"""One-shot fresh acquisition, qualification, census and selector orchestration."""

from __future__ import annotations

import time
import tracemalloc
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    build_disclosed_java_material_entry,
    load_disclosed_java_registry,
)
from ai_brain.stage3.acquisition.java_evidence_policy import (
    load_production_java_evidence_policy,
    verify_java_evidence_policy,
)
from ai_brain.stage3.acquisition.m336d_contracts import (
    LOCAL_SOURCE_VAULT_CONTRACT_REGISTRY,
)
from ai_brain.stage3.acquisition.m336d_final_pipeline import (
    _acquire_one,
    _candidate_overlap_counts,
    _set_read_only,
)
from ai_brain.stage3.acquisition.m336d_spdx_expression import parse_spdx_expression
from ai_brain.stage3.acquisition.m336e_authority import (
    M336E_AUTHORITY_STATEMENT_SHA256,
    M336ESourceAuthorizationBinding,
    load_m336e_authority_registry,
    m336e_receipt_public_dict,
)
from ai_brain.stage3.acquisition.m336e_disclosed_qualification import (
    M336E_DISCLOSED_CONSTRUCT_QUOTAS,
    _production_document_identity,
    _production_index_candidate,
    materialize_selected_source_snapshot,
)
from ai_brain.stage3.acquisition.m336e_identity import (
    PortableVaultManifest,
    SourceEntryBindingManifest,
    build_portable_vault_manifest,
    build_source_entry_binding,
    build_source_entry_binding_manifest,
    build_source_entry_id,
    verify_portable_vault_manifest,
)
from ai_brain.stage3.acquisition.m336e_metadata_pool import validate_metadata_pool_v4
from ai_brain.stage3.acquisition.m336e_protocol import RunProtocolLedger
from ai_brain.stage3.acquisition.m336e_selectability import (
    SelectableSourceCensus,
    SelectedSourceManifest,
    SelectorFeasibilityProof,
    SelectorReceipt,
    build_selectable_source_census,
    build_selectable_source_decision,
    prove_selector_feasibility,
    select_final_sources_once,
)
from ai_brain.stage3.acquisition.maven_provenance import (
    MavenCentralProvenanceProvider,
    canonical_source_bytes,
    inspect_source_archive,
)
from ai_brain.stage3.acquisition.scm_revision import ScmRevisionProvider
from ai_brain.stage3.acquisition.source_authority import (
    PublicationTarget,
    SourceUseScope,
)
from ai_brain.stage3.acquisition.spdx_license import LicenseDocumentRole

M336E_FINAL_ACQUISITION_RUN_ID = "m336e.fresh-java.global-acquisition.v1"
M336E_FINAL_SELECTOR_VERSION = "m336e.production-supported-selector.v1"
M336E_FINAL_SELECTOR_SEED = "m336e-fresh-java-freeze-v4-180"
M336E_FINAL_TARGET = 180
M336E_FINAL_ROOT_CAP = 63


@dataclass(frozen=True)
class FreshAcquisitionPreflight:
    schema_version: int
    f20_sha: str
    candidate_pool_hash: str
    acquisition_report: dict
    qualification_report: dict
    portable_vault_manifest: PortableVaultManifest
    source_entry_binding_manifest: SourceEntryBindingManifest
    selectability_census: SelectableSourceCensus
    feasibility_proof: SelectorFeasibilityProof
    selected_manifest: SelectedSourceManifest | None
    selector_receipt: SelectorReceipt | None
    source_overlap_report: dict
    disclosure_append: dict
    performance_report: dict
    status: str
    report_hash: str


def run_fresh_acquisition_and_preflight(
    *,
    pool: dict,
    vault_root: Path,
    authority_statement: Path,
    f20_sha: str,
    timestamp: str,
    host: str,
    ledger: RunProtocolLedger,
    selected_source_output: Path,
    git_worktrees: tuple[Path, ...],
    maven_provider=None,
    scm_provider=None,
    acquire_one=_acquire_one,
) -> FreshAcquisitionPreflight:
    """Execute the sole source-body acquisition and one guarded selector."""

    candidates = validate_metadata_pool_v4(pool)
    if len(f20_sha) != 40 or any(
        character not in "0123456789abcdef" for character in f20_sha
    ):
        raise ValueError("fresh pipeline requires an exact F20 SHA")
    resolved_worktrees = tuple(path.resolve(strict=True) for path in git_worktrees)
    for external_path in (vault_root, selected_source_output, ledger.path):
        resolved = external_path.resolve(strict=False)
        if any(_is_relative_to(resolved, worktree) for worktree in resolved_worktrees):
            raise ValueError(
                "fresh raw-source and protocol paths must remain outside Git"
            )
    if vault_root.exists() or selected_source_output.exists() or ledger.events():
        raise FileExistsError("fresh acquisition, selection, and ledger must be new")
    vault_root.mkdir(parents=True)
    LOCAL_SOURCE_VAULT_CONTRACT_REGISTRY.validate_root(
        vault_root, git_worktrees=git_worktrees
    )
    context = {
        "f20_sha": f20_sha,
        "acquisition_run_id": M336E_FINAL_ACQUISITION_RUN_ID,
        "candidate_pool_hash": pool["pool_hash"],
    }
    ledger.append("FREEZE_VERIFIED", **context)
    ledger.append("ACQUISITION_RESERVED", **context)

    tracemalloc.start()
    started = time.perf_counter()
    maven = maven_provider or MavenCentralProvenanceProvider(timeout_seconds=180)
    scm = scm_provider or ScmRevisionProvider(timeout_seconds=240)
    acquired = []
    timings: dict[str, list[float]] = {}
    for policy in candidates:
        item = acquire_one(policy, vault_root=vault_root, maven=maven, scm=scm)
        _apply_fresh_scoped_qualification(policy, item)
        for name, seconds in item.pop("_performance_seconds").items():
            timings.setdefault(name, []).append(seconds)
        item.pop("_vault_files")
        acquired.append(item)
    ledger.append("ACQUISITION_COMPLETED", **context)

    vault_started = time.perf_counter()
    portable = build_portable_vault_manifest(vault_root)
    _set_read_only(vault_root)
    verify_portable_vault_manifest(vault_root, portable)
    timings["portable_vault_seal"] = [time.perf_counter() - vault_started]
    sealed_context = {**context, "vault_tree_hash": portable.portable_tree_hash}
    ledger.append("VAULT_SEALED", **sealed_context)

    authority = load_m336e_authority_registry(
        authority_statement,
        expected_statement_sha256=M336E_AUTHORITY_STATEMENT_SHA256,
    )
    disclosed = load_disclosed_java_registry()
    authority_started = time.perf_counter()
    for item in acquired:
        binding = M336ESourceAuthorizationBinding(
            f20_sha=f20_sha,
            acquisition_run_id=M336E_FINAL_ACQUISITION_RUN_ID,
            candidate_family_id=item["family_id"],
            maven_coordinate=item["coordinate"],
            source_repository_url=item["source_url"],
            source_jar_sha256=item["source_jar_sha256"],
            pom_sha256=item["pom_sha256"],
            immutable_scm_commit=item["immutable_scm_commit"],
            scm_archive_sha256=item["scm_archive_sha256"],
            source_tree_hash=item["source_tree_hash"],
            local_vault_manifest_hash=portable.manifest_hash,
        )
        receipt = authority.issue(
            binding,
            source_use_scopes=(
                SourceUseScope.PRIVATE_LOCAL_ANALYSIS,
                SourceUseScope.LOCAL_RESEARCH_EVALUATION,
                SourceUseScope.DERIVED_KNOWLEDGE_ONLY,
                SourceUseScope.RAW_SOURCE_RETENTION,
                SourceUseScope.PUBLIC_REPRODUCIBLE_EVALUATION,
            ),
            publication_targets=(
                PublicationTarget.DERIVED_PACK_PUBLICATION,
                PublicationTarget.METRICS_ONLY_PUBLICATION,
            ),
        )
        authority.verify(receipt, expected_binding=binding)
        item["authority"] = m336e_receipt_public_dict(receipt)
        item["authority_receipt_hash"] = receipt.receipt_hash
        overlaps = _candidate_overlap_counts(item, disclosed)
        item["preselection_overlap_counts"] = overlaps
        if sum(overlaps.values()):
            item["analysis_eligible"] = False
            item["qualification_errors"] = (
                *item["qualification_errors"],
                "FRESHNESS:DISCLOSED_IDENTITY_OVERLAP",
            )
    timings["authority_and_freshness"] = [time.perf_counter() - authority_started]
    qualification = _fresh_qualification_report(acquired)
    qualified_context = {
        **sealed_context,
        "qualification_manifest_hash": qualification["report_hash"],
    }
    ledger.append("QUALIFICATION_COMPLETED", **qualified_context)

    evidence_policy = load_production_java_evidence_policy()
    verify_java_evidence_policy(evidence_policy)
    census_started = time.perf_counter()
    decisions = []
    path_bindings = []
    for item in acquired:
        source_path = vault_root / "candidates" / item["family_id"] / "source.jar"
        if not source_path.is_file() or item["source_jar_sha256"] == "0" * 64:
            continue
        inspection = inspect_source_archive(source_path.read_bytes())
        declarations, evidence_nodes, parser_status_by_path = (
            _production_index_candidate(vault_root, item, inspection, evidence_policy)
        )
        correspondence = {
            row["artifact_path"]: row
            for row in (
                item["correspondence"]["entries"] if item["correspondence"] else ()
            )
        }
        publication_targets = set(item["authority"]["permitted_publication_targets"])
        authority_valid = True
        for archive_path, raw in inspection.java_entries:
            identity = build_source_entry_id(
                candidate_family_id=item["family_id"],
                source_jar_sha256=item["source_jar_sha256"],
                archive_relative_path=archive_path,
                raw_source_sha256=bytes_hash(raw),
                canonical_source_sha256=bytes_hash(canonical_source_bytes(raw)),
            )
            correspondence_row = correspondence.get(archive_path)
            correspondence_complete = bool(
                correspondence_row
                and correspondence_row["complete"]
                and correspondence_row["scm_path"]
            )
            declaration_rows = declarations.get(archive_path, ())
            callable_rows = tuple(
                row
                for row in declaration_rows
                if row.member_kind in {"method", "constructor"}
            )
            supported_rows = tuple(row for row in callable_rows if row.supported)
            production_identity = _production_document_identity(
                item["family_id"], archive_path, bytes_hash(raw)
            )
            if correspondence_complete:
                path_bindings.append(
                    build_source_entry_binding(
                        source_entry_id=identity,
                        archive_path=archive_path,
                        scm_path=correspondence_row["scm_path"],
                        vault_path=f"candidates/{item['family_id']}/sources/{archive_path}",
                        selected_path=f"{item['family_id']}/{archive_path}",
                        production_document_identity=production_identity,
                    )
                )
            eligible = bool(item["analysis_eligible"])
            decisions.append(
                build_selectable_source_decision(
                    source_entry_id=identity,
                    candidate_root=item["family_id"],
                    canonical_path=archive_path,
                    analysis_eligible=eligible,
                    publication_allowed=eligible
                    and {
                        PublicationTarget.DERIVED_PACK_PUBLICATION.value,
                        PublicationTarget.METRICS_ONLY_PUBLICATION.value,
                    }.issubset(publication_targets),
                    source_use_receipt_valid=authority_valid,
                    scoped_license_resolved=bool(
                        eligible
                        and item["_scoped_license_by_archive_path"]
                        .get(archive_path, {})
                        .get("status")
                        == "RESOLVED"
                    ),
                    scm_correspondence_complete=correspondence_complete,
                    parser_status=parser_status_by_path.get(
                        archive_path, "PRODUCTION_INDEX_FAILED"
                    ),
                    declaration_count=len(declaration_rows),
                    callable_declaration_count=len(callable_rows),
                    supported_callable_declaration_count=len(supported_rows),
                    construct_classes=tuple(
                        sorted({row.member_kind for row in callable_rows})
                    ),
                    evidence_policy_path_declared=bool(
                        supported_rows
                        and all(row.node_id in evidence_nodes for row in supported_rows)
                    ),
                )
            )
    binding_manifest = build_source_entry_binding_manifest(path_bindings)
    census = build_selectable_source_census(decisions)
    proof = prove_selector_feasibility(
        census,
        target_file_count=M336E_FINAL_TARGET,
        maximum_files_per_root=M336E_FINAL_ROOT_CAP,
        minimum_root_count=3,
        construct_quotas=M336E_DISCLOSED_CONSTRUCT_QUOTAS,
    )
    timings["selectability_census_and_proof"] = [time.perf_counter() - census_started]
    census_context = {
        **qualified_context,
        "selectability_census_hash": census.census_hash,
    }
    ledger.append("SELECTABILITY_CENSUS_COMPLETED", **census_context)

    selected = None
    selector = None
    if proof.hard_requirements_satisfied:
        selector_started = time.perf_counter()
        selected, selector = select_final_sources_once(
            census,
            proof,
            binding_manifest,
            ledger,
            selector_seed=M336E_FINAL_SELECTOR_SEED,
            selector_version=M336E_FINAL_SELECTOR_VERSION,
            **census_context,
        )
        materialize_selected_source_snapshot(
            vault_root=vault_root,
            binding_manifest=binding_manifest,
            selected_manifest=selected,
            destination=selected_source_output,
        )
        timings["selector_and_materialization"] = [
            time.perf_counter() - selector_started
        ]

    compatible_selected = {
        "files": tuple(
            {
                "family_id": row.candidate_root,
                "source_relative_path": row.canonical_path,
            }
            for row in (selected.files if selected else ())
        )
    }
    overlap = _fresh_overlap_report(acquired, compatible_selected, disclosed)
    disclosure_append = _fresh_disclosure_append(acquired, compatible_selected)
    acquisition = _fresh_acquisition_report(acquired, f20_sha=f20_sha, host=host)
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    performance_body = {
        "schema_version": 2,
        "platform": "windows",
        "candidate_count": len(candidates),
        "total_acquisition_preflight_seconds": f"{elapsed:.6f}",
        "throughput_candidates_per_second": f"{len(candidates) / elapsed:.6f}",
        "peak_python_bytes": peak,
        "operations": tuple(
            (name, _performance_summary(values))
            for name, values in sorted(timings.items())
        ),
    }
    performance = {
        **performance_body,
        "report_hash": content_hash(performance_body),
    }
    status = (
        "PASS"
        if proof.hard_requirements_satisfied
        and selected is not None
        and selected.file_count == M336E_FINAL_TARGET
        and overlap["status"] == "PASS"
        else "BLOCKED"
    )
    body = {
        "schema_version": 2,
        "f20_sha": f20_sha,
        "candidate_pool_hash": pool["pool_hash"],
        "acquisition_report": acquisition,
        "qualification_report": qualification,
        "portable_vault_manifest": portable,
        "source_entry_binding_manifest": binding_manifest,
        "selectability_census": census,
        "feasibility_proof": proof,
        "selected_manifest": selected,
        "selector_receipt": selector,
        "source_overlap_report": overlap,
        "disclosure_append": disclosure_append,
        "performance_report": performance,
        "status": status,
    }
    return FreshAcquisitionPreflight(**body, report_hash=content_hash(body))


def _apply_fresh_scoped_qualification(policy: dict, item: dict) -> None:
    """Separate candidate authenticity from exact per-source license scope."""

    correspondence = {
        row["artifact_path"]: row
        for row in (item["correspondence"]["entries"] if item["correspondence"] else ())
    }
    pom_ids = tuple(
        row[0]
        for row in policy.get("pom_license_declarations", ())
        if row and row[0] != "NOASSERTION"
    )
    automatic_statuses = {
        "EXACT_BYTES_MATCH",
        "EXACT_NORMALIZED_MATCH",
        "SPDX_TEMPLATE_MATCH",
    }
    decisions = {}
    for archive_path in item.get("_archive_java_paths", ()):
        scm_path = (correspondence.get(archive_path) or {}).get("scm_path")
        expressions = set()
        evidence_hashes = set()
        if len(pom_ids) == 1:
            try:
                expression = parse_spdx_expression(pom_ids[0]).canonical()
            except ValueError:
                expression = None
            if expression is not None:
                expressions.add(expression)
                evidence_hashes.update(policy.get("metadata_receipt_hashes", ()))
        unknown_applicable = []
        for row in item.get("_legal_inventory_rows", ()):
            applies = _legal_row_applies_to_source(row, archive_path, scm_path)
            if not applies:
                continue
            if (
                LicenseDocumentRole(row.candidate_role)
                is LicenseDocumentRole.UNKNOWN_LICENSE_DOCUMENT
            ):
                unknown_applicable.append(row.receipt_hash)
                continue
            if (
                row.selected_as_project_license
                and row.spdx_license_id
                and row.spdx_match_status in automatic_statuses
            ):
                expressions.add(parse_spdx_expression(row.spdx_license_id).canonical())
                evidence_hashes.add(row.receipt_hash)
        if unknown_applicable:
            status = "REVIEW_REQUIRED_AMBIGUOUS_SCOPE"
            expression = None
        elif len(expressions) == 1:
            status = "RESOLVED"
            expression = next(iter(expressions))
        elif len(expressions) > 1:
            status = "REVIEW_REQUIRED_UNSPECIFIED_MULTI_LICENSE"
            expression = None
        else:
            status = "REVIEW_REQUIRED_AMBIGUOUS_SCOPE"
            expression = None
        body = {
            "source_path": archive_path,
            "scm_path": scm_path,
            "expression": expression,
            "status": status,
            "evidence_hashes": tuple(sorted(evidence_hashes)),
            "applicable_unknown_document_hashes": tuple(sorted(unknown_applicable)),
        }
        decisions[archive_path] = {**body, "decision_hash": content_hash(body)}

    non_license_errors = tuple(
        error
        for error in item["qualification_errors"]
        if not error.startswith("LICENSE:UNKNOWN_LICENSE_DOCUMENT:")
    )
    authentic = all(
        item[name] != zero
        for name, zero in (
            ("source_jar_sha256", "0" * 64),
            ("pom_sha256", "0" * 64),
            ("scm_archive_sha256", "0" * 64),
            ("immutable_scm_commit", "0" * 40),
        )
    )
    eligible_paths = tuple(
        path
        for path, decision in decisions.items()
        if decision["status"] == "RESOLVED"
        and (correspondence.get(path) or {}).get("complete")
    )
    item["_scoped_license_by_archive_path"] = decisions
    item["scoped_license_expressions"] = tuple(
        sorted(
            {
                decision["expression"]
                for decision in decisions.values()
                if decision["expression"] is not None
            }
        )
    )
    item["complete_correspondence_paths"] = tuple(
        sorted(path for path, row in correspondence.items() if row.get("complete"))
    )
    item["candidate_eligible_source_entry_count"] = len(eligible_paths)
    item["analysis_eligible"] = bool(
        authentic and eligible_paths and not non_license_errors
    )
    item["qualification_errors"] = non_license_errors
    item["qualification_review_findings"] = tuple(
        sorted(
            {
                "LICENSE:UNKNOWN_APPLICABILITY_REVIEW_REQUIRED"
                for decision in decisions.values()
                if decision["applicable_unknown_document_hashes"]
            }
        )
    )


def _legal_row_applies_to_source(row, archive_path: str, scm_path: str | None) -> bool:
    """Resolve a legal row against the path domain of its own container."""

    if row.container_id == "source-jar":
        source = archive_path
        legal = row.path
    elif row.container_id == "scm-archive" and scm_path:
        source = scm_path
        parts = PurePosixPath(row.path).parts
        legal = PurePosixPath(*parts[1:]).as_posix() if len(parts) > 1 else row.path
    else:
        return False
    if LicenseDocumentRole(row.candidate_role) is LicenseDocumentRole.PROJECT_LICENSE:
        return True
    parent = PurePosixPath(legal).parent.as_posix()
    if parent in {".", "META-INF", "meta-inf"}:
        return True
    return source == parent or source.startswith(parent + "/")


def _fresh_qualification_report(acquired) -> dict:
    decisions = []
    for item in sorted(acquired, key=lambda value: value["family_id"]):
        authority = item["authority"]
        publication_targets = set(authority["permitted_publication_targets"])
        denied_targets = set(authority["denied_publication_targets"])
        scoped = tuple(item["_scoped_license_by_archive_path"].values())
        resolved_count = sum(row["status"] == "RESOLVED" for row in scoped)
        authentic = all(
            item[name] != zero
            for name, zero in (
                ("source_jar_sha256", "0" * 64),
                ("pom_sha256", "0" * 64),
                ("scm_archive_sha256", "0" * 64),
                ("immutable_scm_commit", "0" * 40),
            )
        )
        eligible = bool(item["analysis_eligible"])
        body = {
            "family_id": item["family_id"],
            "organization_id": item["organization_id"],
            "coordinate": item["coordinate"],
            "source_authenticity_decision": (
                "AUTHENTIC" if authentic else "REVIEW_REQUIRED"
            ),
            "knowledge_acquisition_eligibility_decision": (
                "ELIGIBLE_FOR_ANALYSIS" if eligible else "INELIGIBLE"
            ),
            "source_retention_decision": "ALLOWED_SEALED_VAULT_ONLY",
            "raw_source_publication_decision": (
                "DENIED"
                if PublicationTarget.RAW_SOURCE_PUBLICATION.value in denied_targets
                else "NOT_AUTHORIZED"
            ),
            "source_excerpt_publication_decision": (
                "DENIED"
                if PublicationTarget.SOURCE_EXCERPT_PUBLICATION.value in denied_targets
                else "NOT_AUTHORIZED"
            ),
            "derived_pack_publication_decision": (
                "ALLOWED"
                if eligible
                and PublicationTarget.DERIVED_PACK_PUBLICATION.value
                in publication_targets
                else "NOT_APPLICABLE"
            ),
            "metrics_publication_decision": (
                "ALLOWED"
                if eligible
                and PublicationTarget.METRICS_ONLY_PUBLICATION.value
                in publication_targets
                else "NOT_APPLICABLE"
            ),
            "scm_correspondence_decision": (
                "COMPLETE"
                if item["correspondence_complete_for_all_entries"]
                else "PARTIAL_OR_INCOMPLETE"
            ),
            "scoped_license_decision": (
                "RESOLVED"
                if scoped and resolved_count == len(scoped)
                else "PARTIALLY_RESOLVED"
                if resolved_count
                else "REVIEW_REQUIRED"
            ),
            "candidate_eligible_source_set_count": item[
                "candidate_eligible_source_entry_count"
            ],
            "scoped_license_file_decision_count": len(scoped),
            "scoped_license_resolved_file_count": resolved_count,
            "scoped_license_review_required_file_count": len(scoped) - resolved_count,
            "scoped_license_decisions": scoped,
            "scoped_license_expressions": item["scoped_license_expressions"],
            "legal_document_count": item["legal_document_count"],
            "unclassified_legal_document_count": item[
                "unclassified_legal_document_count"
            ],
            "unknown_legal_document_role_count": item[
                "unknown_legal_document_role_count"
            ],
            "authority_receipt_hash": item["authority_receipt_hash"],
            "authority": authority,
            "qualification_errors": item["qualification_errors"],
            "qualification_review_findings": item["qualification_review_findings"],
        }
        decisions.append({**body, "decision_hash": content_hash(body)})
    eligible = tuple(
        item
        for item in decisions
        if item["knowledge_acquisition_eligibility_decision"] == "ELIGIBLE_FOR_ANALYSIS"
    )
    body = {
        "schema_version": 2,
        "candidate_count": len(decisions),
        "analysis_eligible_root_count": len(eligible),
        "analysis_eligible_java_entry_count": sum(
            item["candidate_eligible_source_set_count"] for item in eligible
        ),
        "raw_source_publication_root_count": sum(
            item["raw_source_publication_decision"] == "ALLOWED" for item in decisions
        ),
        "source_excerpt_publication_root_count": sum(
            item["source_excerpt_publication_decision"] == "ALLOWED"
            for item in decisions
        ),
        "derived_pack_publication_root_count": sum(
            item["derived_pack_publication_decision"] == "ALLOWED" for item in decisions
        ),
        "metrics_publication_root_count": sum(
            item["metrics_publication_decision"] == "ALLOWED" for item in decisions
        ),
        "typed_decisions_per_candidate": 10,
        "legal_document_count": sum(item["legal_document_count"] for item in decisions),
        "unknown_legal_document_role_count": sum(
            item["unknown_legal_document_role_count"] for item in decisions
        ),
        "scoped_license_file_decision_count": sum(
            item["scoped_license_file_decision_count"] for item in decisions
        ),
        "scoped_license_review_required_file_count": sum(
            item["scoped_license_review_required_file_count"] for item in decisions
        ),
        "decisions": tuple(decisions),
    }
    return {**body, "report_hash": content_hash(body)}


def _fresh_acquisition_report(acquired, *, f20_sha: str, host: str) -> dict:
    receipts = tuple(
        {
            "family_id": item["family_id"],
            "coordinate": item["coordinate"],
            "source_url": item["source_url"],
            "source_jar_sha256": item["source_jar_sha256"],
            "source_jar_size": item["source_jar_size"],
            "pom_sha256": item["pom_sha256"],
            "immutable_scm_commit": item["immutable_scm_commit"],
            "scm_archive_sha256": item["scm_archive_sha256"],
            "scm_archive_size": item["scm_archive_size"],
            "source_tree_hash": item["source_tree_hash"],
            "authority_receipt_hash": item["authority_receipt_hash"],
        }
        for item in sorted(acquired, key=lambda value: value["family_id"])
    )
    body = {
        "schema_version": 2,
        "f20_sha": f20_sha,
        "acquisition_run_id": M336E_FINAL_ACQUISITION_RUN_ID,
        "global_acquisition_count": 1,
        "candidate_count": len(receipts),
        "host_audit_hash": content_hash(host),
        "receipts": receipts,
    }
    return {**body, "report_hash": content_hash(body)}


def _fresh_overlap_report(acquired, selected_manifest, disclosed) -> dict:
    selected_by_family = {}
    for row in selected_manifest["files"]:
        selected_by_family.setdefault(row["family_id"], []).append(
            row["source_relative_path"]
        )
    rows = []
    totals = Counter()
    for item in sorted(acquired, key=lambda value: value["family_id"]):
        counts = _candidate_overlap_counts(
            item,
            disclosed,
            selected_paths=tuple(selected_by_family.get(item["family_id"], ())),
        )
        totals.update(counts)
        row_body = {
            "family_id": item["family_id"],
            "identity_class_overlap_counts": tuple(sorted(counts.items())),
            "overlap_count": sum(counts.values()),
            "candidate_denied": bool(sum(counts.values())),
        }
        rows.append({**row_body, "row_hash": content_hash(row_body)})
    body = {
        "schema_version": 2,
        "identity_class_count": len(totals),
        "class_overlap_counts": tuple(sorted(totals.items())),
        "selected_root_overlap_count": sum(totals.values()),
        "denied_candidate_ids": tuple(
            item["family_id"] for item in rows if item["candidate_denied"]
        ),
        "candidate_rows": tuple(rows),
        "downloaded_candidate_count": sum(
            item["source_jar_sha256"] != "0" * 64 for item in acquired
        ),
        "all_downloaded_candidates_appended": True,
        "status": "PASS" if not sum(totals.values()) else "FAIL",
    }
    return {**body, "report_hash": content_hash(body)}


def _fresh_disclosure_append(acquired, selected_manifest) -> dict:
    selected_by_family = {}
    for row in selected_manifest["files"]:
        selected_by_family.setdefault(row["family_id"], []).append(
            row["source_relative_path"]
        )
    entries = []
    for item in sorted(acquired, key=lambda value: value["family_id"]):
        if item["source_jar_sha256"] == "0" * 64:
            continue
        correspondence_hash = (
            item["correspondence"]["correspondence_hash"]
            if item["correspondence"]
            else "0" * 64
        )
        entry = build_disclosed_java_material_entry(
            coordinate=item["coordinate"],
            version=item["coordinate"].rsplit(":", 1)[-1],
            source_url=item["source_url"],
            archive_hash=item["source_jar_sha256"],
            pom_hash=item["pom_sha256"],
            raw_source_hashes=item["_raw_source_hashes"],
            canonical_source_hashes=item["_canonical_source_hashes"],
            source_tree_hash=item["source_tree_hash"],
            selected_relative_paths=tuple(
                selected_by_family.get(item["family_id"], ())
            ),
            declaration_fingerprints=tuple(
                sorted(
                    content_hash((item["family_id"], value))
                    for value in item["_canonical_source_hashes"]
                )
            ),
            scm_revision=item["immutable_scm_commit"],
            correspondence_hash=correspondence_hash,
            disclosure_reason="DOWNLOADED_DURING_M336E_H20",
            originating_chain="E19-R20-Q20-F20-H20-E20",
        )
        entries.append(asdict(entry))
    body = {
        "schema_version": 2,
        "downloaded_candidate_count": len(entries),
        "attempted_candidate_count": len(acquired),
        "all_downloaded_candidates_included": len(entries)
        == sum(item["source_jar_sha256"] != "0" * 64 for item in acquired),
        "entries": tuple(entries),
    }
    return {**body, "append_hash": content_hash(body)}


def _performance_summary(samples) -> dict:
    ordered = sorted(samples)

    def percentile(fraction):
        index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction + 0.5)))
        return f"{ordered[index]:.9f}"

    return {
        "sample_count": len(ordered),
        "p50_seconds": percentile(0.50),
        "p95_seconds": percentile(0.95),
        "p99_seconds": percentile(0.99),
        "total_seconds": f"{sum(ordered):.9f}",
    }


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
