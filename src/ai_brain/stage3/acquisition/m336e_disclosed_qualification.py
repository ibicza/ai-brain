"""Offline full-path qualification of the already disclosed M-33.6d vault."""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_evidence_policy import (
    enumerate_java_evidence_requirements,
    load_production_java_evidence_policy,
    verify_java_evidence_policy,
)
from ai_brain.stage3.acquisition.java_proposals import propose_java_knowledge
from ai_brain.stage3.acquisition.java_source_index import index_java_bundle
from ai_brain.stage3.acquisition.m336d_authority import (
    M336D_AUTHORITY_STATEMENT_SHA256,
    SourceAuthorizationBinding,
    load_pinned_authority_registry_for_development,
    receipt_public_dict,
)
from ai_brain.stage3.acquisition.m336d_correspondence import (
    derive_scm_correspondence_decision,
)
from ai_brain.stage3.acquisition.m336d_final_pipeline import (
    M336D_ACQUISITION_RUN_ID,
    _qualification_report,
    validate_candidate_pool,
)
from ai_brain.stage3.acquisition.m336d_legal_inventory import (
    LegalDocumentContainer,
    inventory_legal_documents,
)
from ai_brain.stage3.acquisition.m336d_spdx_expression import parse_spdx_expression
from ai_brain.stage3.acquisition.m336e_identity import (
    PortableVaultManifest,
    SourceEntryBindingManifest,
    build_portable_vault_manifest,
    build_source_entry_binding,
    build_source_entry_binding_manifest,
    build_source_entry_id,
    verify_portable_vault_manifest,
)
from ai_brain.stage3.acquisition.m336e_selectability import (
    SelectableSourceCensus,
    SelectedSourceManifest,
    SelectorFeasibilityProof,
    build_selectable_source_census,
    build_selectable_source_decision,
    prove_selector_feasibility,
)
from ai_brain.stage3.acquisition.maven_provenance import (
    canonical_source_bytes,
    correspond_source_trees,
    inspect_source_archive,
)
from ai_brain.stage3.acquisition.persistence import AcquisitionStore
from ai_brain.stage3.acquisition.scm_revision import _inspect_github_archive
from ai_brain.stage3.acquisition.segmentation import segment_bundle_with_report
from ai_brain.stage3.acquisition.source_artifact_provenance import (
    SourceCorrespondenceStatus,
)
from ai_brain.stage3.acquisition.source_authority import (
    PublicationTarget,
    SourceUseScope,
)
from ai_brain.stage3.acquisition.sources import ingest_bundle
from ai_brain.stage3.acquisition.version import CANONICAL_ACQUISITION_SCHEMA_VERSION

M336E_DISCLOSED_RUN_ID = "m336e.disclosed-full-path.rehearsal.v1"
M336E_DISCLOSED_SELECTOR_SEED = "m336e-disclosed-full-path-180-v1"
M336E_DISCLOSED_TARGET = 180
M336E_DISCLOSED_ROOT_CAP = 63
M336E_DISCLOSED_CONSTRUCT_QUOTAS = (("constructor", 30), ("method", 120))

_COMPLETE = frozenset(
    {
        SourceCorrespondenceStatus.RAW_EXACT_MATCH,
        SourceCorrespondenceStatus.CANONICAL_TEXT_EXACT_MATCH,
        SourceCorrespondenceStatus.PATH_RELOCATED_RAW_MATCH,
        SourceCorrespondenceStatus.PATH_RELOCATED_CANONICAL_MATCH,
        SourceCorrespondenceStatus.GENERATED_WITH_VERIFIED_PROVENANCE,
    }
)


@dataclass(frozen=True)
class DisclosedCandidateQualification:
    family_id: str
    source_jar_sha256: str
    source_tree_hash: str
    java_file_count: int
    legal_document_count: int
    unknown_legal_document_role_count: int
    correspondence_complete_file_count: int
    analysis_eligible: bool
    authority_receipt_valid: bool
    qualification_hash: str


@dataclass(frozen=True)
class DisclosedFullPathPreflight:
    schema_version: int
    candidate_pool_hash: str
    historical_f19_sha: str
    vault_manifest: PortableVaultManifest
    historical_qualification_report: dict
    candidates: tuple[DisclosedCandidateQualification, ...]
    source_entry_binding_manifest: SourceEntryBindingManifest
    selectability_census: SelectableSourceCensus
    feasibility_proof: SelectorFeasibilityProof
    authority_receipt_failure_count: int
    historical_qualification_equal: bool
    status: str
    report_hash: str


def run_disclosed_full_path_preflight(
    *,
    pool: dict,
    vault_root: Path,
    authority_statement: Path,
    historical_f19_sha: str,
    historical_public_vault_manifest: dict,
    expected_historical_qualification: dict | None = None,
) -> DisclosedFullPathPreflight:
    """Re-qualify disclosed bytes and prove selector capacity without an oracle."""

    policies = validate_candidate_pool(pool)
    portable = build_portable_vault_manifest(vault_root)
    verify_portable_vault_manifest(vault_root, portable)
    _verify_historical_vault_rows(vault_root, historical_public_vault_manifest)
    content_manifest_hash = historical_public_vault_manifest["content_manifest_hash"]
    registry = load_pinned_authority_registry_for_development(
        authority_statement,
        expected_statement_sha256=M336D_AUTHORITY_STATEMENT_SHA256,
    )
    evidence_policy = load_production_java_evidence_policy()
    verify_java_evidence_policy(evidence_policy)

    acquired = []
    candidate_receipts = []
    source_rows = []
    bindings = []
    authority_failures = 0
    for policy in policies:
        item, inspection, correspondence, inventory = _reconstruct_candidate(
            policy, vault_root
        )
        binding = SourceAuthorizationBinding(
            f19_sha=historical_f19_sha,
            acquisition_run_id=M336D_ACQUISITION_RUN_ID,
            candidate_family_id=item["family_id"],
            maven_coordinate=item["coordinate"],
            source_repository_url=item["source_url"],
            source_jar_sha256=item["source_jar_sha256"],
            pom_sha256=item["pom_sha256"],
            immutable_scm_commit=item["immutable_scm_commit"],
            scm_archive_sha256=item["scm_archive_sha256"],
            source_tree_hash=item["source_tree_hash"],
            local_vault_manifest_hash=content_manifest_hash,
        )
        authority = registry.issue(
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
        try:
            registry.verify(authority, expected_binding=binding)
            authority_valid = True
        except (TypeError, ValueError):
            authority_valid = False
            authority_failures += 1
        item["authority"] = receipt_public_dict(authority)
        item["authority_receipt_hash"] = authority.receipt_hash
        acquired.append(item)

        declarations_by_path, evidence_nodes, parser_status_by_path = (
            _production_index_candidate(vault_root, item, inspection, evidence_policy)
        )
        correspondence_by_path = {
            row.artifact_path: row
            for row in (correspondence.entries if correspondence else ())
        }
        for archive_path, raw in inspection.java_entries:
            source_identity = build_source_entry_id(
                candidate_family_id=item["family_id"],
                source_jar_sha256=item["source_jar_sha256"],
                archive_relative_path=archive_path,
                raw_source_sha256=bytes_hash(raw),
                canonical_source_sha256=bytes_hash(canonical_source_bytes(raw)),
            )
            correspondence_row = correspondence_by_path.get(archive_path)
            correspondence_complete = bool(
                correspondence_row
                and correspondence_row.status in _COMPLETE
                and correspondence_row.repository_path
            )
            candidate_eligible = bool(item["analysis_eligible"])
            declaration_rows = declarations_by_path.get(archive_path, ())
            callable_rows = tuple(
                row
                for row in declaration_rows
                if row.member_kind in {"method", "constructor"}
            )
            supported_rows = tuple(row for row in callable_rows if row.supported)
            construct_classes = tuple(
                sorted({row.member_kind for row in callable_rows})
            )
            parser_status = parser_status_by_path.get(
                archive_path, "PRODUCTION_INDEX_FAILED"
            )
            production_document_identity = _production_document_identity(
                item["family_id"], archive_path, bytes_hash(raw)
            )
            if correspondence_complete:
                bindings.append(
                    build_source_entry_binding(
                        source_entry_id=source_identity,
                        archive_path=archive_path,
                        scm_path=correspondence_row.repository_path,
                        vault_path=(
                            f"candidates/{item['family_id']}/sources/{archive_path}"
                        ),
                        selected_path=f"{item['family_id']}/{archive_path}",
                        production_document_identity=production_document_identity,
                    )
                )
            source_rows.append(
                build_selectable_source_decision(
                    source_entry_id=source_identity,
                    candidate_root=item["family_id"],
                    canonical_path=archive_path,
                    analysis_eligible=candidate_eligible,
                    publication_allowed=candidate_eligible,
                    source_use_receipt_valid=authority_valid,
                    scoped_license_resolved=bool(
                        candidate_eligible and item["scoped_license_expressions"]
                    ),
                    scm_correspondence_complete=correspondence_complete,
                    parser_status=parser_status,
                    declaration_count=len(declaration_rows),
                    callable_declaration_count=len(callable_rows),
                    supported_callable_declaration_count=len(supported_rows),
                    construct_classes=construct_classes,
                    evidence_policy_path_declared=bool(
                        supported_rows
                        and all(row.node_id in evidence_nodes for row in supported_rows)
                    ),
                )
            )
        candidate_body = {
            "family_id": item["family_id"],
            "source_jar_sha256": item["source_jar_sha256"],
            "source_tree_hash": item["source_tree_hash"],
            "java_file_count": len(inspection.java_entries),
            "legal_document_count": (
                inventory.discovered_document_count if inventory else 0
            ),
            "unknown_legal_document_role_count": (
                inventory.unknown_role_count if inventory else 0
            ),
            "correspondence_complete_file_count": sum(
                row.status in _COMPLETE for row in correspondence_by_path.values()
            ),
            "analysis_eligible": bool(item["analysis_eligible"]),
            "authority_receipt_valid": authority_valid,
        }
        candidate_receipts.append(
            DisclosedCandidateQualification(
                **candidate_body, qualification_hash=content_hash(candidate_body)
            )
        )

    historical_qualification = _qualification_report(acquired)
    equal = expected_historical_qualification is None or canonical_json(
        historical_qualification
    ) == canonical_json(expected_historical_qualification)
    binding_manifest = build_source_entry_binding_manifest(bindings)
    census = build_selectable_source_census(source_rows)
    proof = prove_selector_feasibility(
        census,
        target_file_count=M336E_DISCLOSED_TARGET,
        maximum_files_per_root=M336E_DISCLOSED_ROOT_CAP,
        minimum_root_count=3,
        construct_quotas=M336E_DISCLOSED_CONSTRUCT_QUOTAS,
    )
    status = (
        "PASS"
        if not authority_failures and equal and proof.hard_requirements_satisfied
        else "FAIL"
    )
    body = {
        "schema_version": 1,
        "candidate_pool_hash": pool["pool_hash"],
        "historical_f19_sha": historical_f19_sha,
        "vault_manifest": portable,
        "historical_qualification_report": historical_qualification,
        "candidates": tuple(candidate_receipts),
        "source_entry_binding_manifest": binding_manifest,
        "selectability_census": census,
        "feasibility_proof": proof,
        "authority_receipt_failure_count": authority_failures,
        "historical_qualification_equal": equal,
        "status": status,
    }
    return DisclosedFullPathPreflight(**body, report_hash=content_hash(body))


def _reconstruct_candidate(policy: dict, vault_root: Path):
    family = policy["family_id"]
    root = vault_root / "candidates" / family
    source_raw = (root / "source.jar").read_bytes()
    pom_raw = (root / "pom.xml").read_bytes()
    scm_raw = (root / "scm.zip").read_bytes()
    inspection = inspect_source_archive(source_raw)
    scm_java, _scm_licenses, tree_hash = _inspect_github_archive(scm_raw)
    errors = []
    correspondence = None
    inventory = None
    try:
        correspondence = correspond_source_trees(
            inspection.java_entries,
            scm_java,
            repository_path_prefixes=tuple(policy["repository_source_prefixes"]),
        )
    except Exception as exc:  # noqa: BLE001 - candidate-local disclosed evidence
        errors.append(f"CORRESPONDENCE:{type(exc).__name__}:{str(exc)[:160]}")
    if correspondence is not None:
        try:
            inventory = inventory_legal_documents(
                (
                    LegalDocumentContainer("source-jar", source_raw),
                    LegalDocumentContainer("scm-archive", scm_raw),
                )
            )
        except Exception as exc:  # noqa: BLE001 - candidate-local disclosed evidence
            errors.append(f"LEGAL_INVENTORY:{type(exc).__name__}:{str(exc)[:160]}")
    automatic_licenses = tuple(
        sorted(
            {
                row.spdx_license_id
                for row in (inventory.rows if inventory else ())
                if row.spdx_license_id
            }
        )
    )
    for expression in automatic_licenses:
        if parse_spdx_expression(expression).canonical() != expression:
            errors.append("LICENSE:NONCANONICAL_SPDX_EXPRESSION")
    if inventory is not None and (
        inventory.unclassified_document_count or inventory.unknown_role_count
    ):
        errors.append(
            "LICENSE:UNKNOWN_LICENSE_DOCUMENT:"
            f"unclassified={inventory.unclassified_document_count},"
            f"unknown_role={inventory.unknown_role_count}"
        )
    complete_entries = tuple(
        row.artifact_path
        for row in (correspondence.entries if correspondence else ())
        if row.status in _COMPLETE
    )
    all_correspond = bool(
        correspondence
        and not correspondence.unmatched_count
        and not correspondence.ambiguous_count
    )
    eligible = bool(
        complete_entries
        and automatic_licenses
        and inventory is not None
        and inventory.unclassified_document_count == 0
        and inventory.unknown_role_count == 0
        and not errors
    )
    public_correspondence = (
        asdict(derive_scm_correspondence_decision(correspondence, selected_paths=()))
        if correspondence
        else None
    )
    item = {
        "family_id": family,
        "organization_id": policy["organization_id"],
        "coordinate": policy["coordinate"],
        "source_url": policy["source_url"],
        "source_jar_sha256": bytes_hash(source_raw),
        "source_jar_size": len(source_raw),
        "pom_sha256": bytes_hash(pom_raw),
        "immutable_scm_commit": policy["scm_commit"],
        "scm_archive_sha256": bytes_hash(scm_raw),
        "scm_archive_size": len(scm_raw),
        "source_tree_hash": tree_hash,
        "artifact_authenticity_mode": "MAVEN_CENTRAL_PLUS_IMMUTABLE_SCM",
        "scoped_license_expressions": automatic_licenses,
        "legal_document_count": inventory.discovered_document_count if inventory else 0,
        "unclassified_legal_document_count": (
            inventory.unclassified_document_count if inventory else 0
        ),
        "unknown_legal_document_role_count": (
            inventory.unknown_role_count if inventory else 0
        ),
        "correspondence": public_correspondence,
        "correspondence_complete_for_all_entries": all_correspond,
        "complete_correspondence_paths": complete_entries,
        "analysis_eligible": eligible,
        "candidate_eligible_source_entry_count": len(complete_entries)
        if eligible
        else 0,
        "qualification_errors": tuple(errors),
        "_raw_source_hashes": tuple(
            sorted(bytes_hash(raw) for _path, raw in inspection.java_entries)
        ),
        "_canonical_source_hashes": tuple(
            sorted(
                bytes_hash(canonical_source_bytes(raw))
                for _path, raw in inspection.java_entries
            )
        ),
    }
    return item, inspection, correspondence, inventory


def _production_index_candidate(vault_root, item, inspection, evidence_policy):
    if not item["analysis_eligible"]:
        return (
            {},
            frozenset(),
            {
                path: "NOT_RUN_CANDIDATE_INELIGIBLE"
                for path, _raw in inspection.java_entries
            },
        )
    family = item["family_id"]
    source_root = vault_root / "candidates" / family / "sources"
    remaining = tuple(
        source_root.joinpath(*path.split("/")) for path, _raw in inspection.java_entries
    )
    parser_status = {
        path.relative_to(source_root).as_posix(): "PASS" for path in remaining
    }
    attempt = 0
    while remaining:
        try:
            with tempfile.TemporaryDirectory(
                prefix=f"m336e-census-{family}-{attempt}-"
            ) as temporary:
                store = AcquisitionStore.open_or_initialize(Path(temporary) / "store")
                bundle = ingest_bundle(
                    remaining,
                    bundle_id=f"m336e-disclosed-{family}-{attempt}",
                    domain_tags=("java-api",),
                    imported_at="1970-01-01T00:00:00Z",
                    source_root=source_root,
                    store=store,
                )
                index = index_java_bundle(bundle, store)
                segmentation = segment_bundle_with_report(
                    bundle, store, java_source_index=index
                )
                proposals = propose_java_knowledge(bundle, segmentation, index)
                requirements = enumerate_java_evidence_requirements(
                    proposals, index, evidence_policy
                )
            break
        except ValueError as exc:
            prefix = "Java grammar parse failure: "
            if not str(exc).startswith(prefix):
                return (
                    {},
                    frozenset(),
                    {path: "PRODUCTION_INDEX_FAILED" for path in parser_status},
                )
            failed = str(exc).removeprefix(prefix)
            matching = tuple(
                path
                for path in remaining
                if path.relative_to(source_root).as_posix() == failed
            )
            if len(matching) != 1:
                return (
                    {},
                    frozenset(),
                    {path: "PRODUCTION_INDEX_FAILED" for path in parser_status},
                )
            parser_status[failed] = "PARSER_FAILED"
            remaining = tuple(path for path in remaining if path != matching[0])
            attempt += 1
    else:
        return {}, frozenset(), parser_status
    document_paths = {row.document_id: row.relative_path for row in bundle.documents}
    by_path = {path: [] for path in document_paths.values()}
    for declaration in index.declarations:
        by_path[document_paths[declaration.document_id]].append(declaration)
    proposal_ids_with_policy = {row.proposal_id for row in requirements}
    evidence_nodes = frozenset(
        row.parser_node_id
        for row in proposals.bindings
        if row.proposal_id in proposal_ids_with_policy
    )
    return (
        {path: tuple(rows) for path, rows in by_path.items()},
        evidence_nodes,
        parser_status,
    )


def _production_document_identity(family: str, archive_path: str, raw_hash: str) -> str:
    relative_path = f"{family}/{archive_path}"
    identity = {
        "schema_version": CANONICAL_ACQUISITION_SCHEMA_VERSION,
        "bundle_id": "m336-final-java",
        "relative_path": relative_path,
        "bytes_hash": raw_hash,
    }
    return f"m336-final-java.document.{content_hash(identity)[:32]}"


def _verify_historical_vault_rows(vault_root: Path, public_manifest: dict) -> None:
    rows = tuple(public_manifest["rows"])
    if public_manifest["file_count"] != len(rows):
        raise ValueError("historical public vault row denominator differs")
    for row in rows:
        path = vault_root.joinpath(*row["relative_path"].split("/"))
        raw = path.read_bytes()
        if len(raw) != row["byte_size"] or bytes_hash(raw) != row["sha256"]:
            raise ValueError("historical public vault row differs from disclosed bytes")
    physical = {
        path.relative_to(vault_root).as_posix()
        for path in vault_root.rglob("*")
        if path.is_file()
    }
    if physical != {row["relative_path"] for row in rows}:
        raise ValueError("historical public vault physical path set differs")


def materialize_selected_source_snapshot(
    *,
    vault_root: Path,
    binding_manifest: SourceEntryBindingManifest,
    selected_manifest: SelectedSourceManifest,
    destination: Path,
) -> None:
    """Copy exactly the sealed selection into an external production snapshot."""

    if destination.exists():
        raise FileExistsError("selected source snapshot already exists")
    by_identity = {
        row.source_entry_id.identity_hash: row for row in binding_manifest.bindings
    }
    destination.mkdir(parents=True)
    for selected in selected_manifest.files:
        binding = by_identity[selected.source_entry_identity_hash]
        if (
            selected.selected_path != binding.selected_path
            or selected.production_document_identity
            != binding.production_document_identity
        ):
            raise ValueError("selected source row differs from its path-domain binding")
        source = vault_root.joinpath(*binding.vault_path.split("/"))
        raw = source.read_bytes()
        identity = binding.source_entry_id
        if (
            bytes_hash(raw) != identity.raw_source_sha256
            or bytes_hash(canonical_source_bytes(raw))
            != identity.canonical_source_sha256
        ):
            raise ValueError("selected source bytes differ from SourceEntryId")
        target = destination.joinpath(*binding.selected_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    actual = tuple(
        sorted(
            path.relative_to(destination).as_posix()
            for path in destination.rglob("*")
            if path.is_file()
        )
    )
    expected = tuple(sorted(row.selected_path for row in selected_manifest.files))
    if actual != expected or len(actual) != selected_manifest.file_count:
        raise ValueError("materialized source snapshot differs from selected manifest")


def load_strict_json(path: Path):
    """Load a canonical JSON evidence file and reject duplicate object keys."""

    def unique(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=unique)
    if raw != (canonical_json(value) + "\n").encode("utf-8"):
        raise ValueError("disclosed evidence JSON is not canonical UTF-8/LF")
    return value


def legal_archive_document_count(path: Path) -> int:
    """Diagnostic helper that reads only already disclosed archive bytes."""

    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
        return len(archive.namelist())
