"""Candidate-fault-isolated Maven acquisition and terminal accounting."""

from __future__ import annotations

import io
import json
import os
import subprocess
import time
import urllib.error
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path, PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336d_contracts import LocalVaultRole
from ai_brain.stage3.acquisition.m336d_correspondence import (
    derive_scm_correspondence_decision,
)
from ai_brain.stage3.acquisition.m336d_legal_inventory import (
    LegalDocumentContainer,
    inventory_legal_documents,
)
from ai_brain.stage3.acquisition.m336d_spdx_expression import parse_spdx_expression
from ai_brain.stage3.acquisition.m336k_archive import (
    ArchiveInspectionPolicyV2,
    ArchiveInspectionResultV2,
    CandidateArchiveInspectionBinding,
    archive_decision_is_accepted,
    build_candidate_archive_inspection_binding,
    inspect_source_archive_v2,
)
from ai_brain.stage3.acquisition.maven_provenance import (
    MavenCentralProvenanceProvider,
    correspond_source_trees,
    maven_coordinate,
)
from ai_brain.stage3.acquisition.scm_revision import (
    ScmRevisionProvider,
    _inspect_github_archive,
)
from ai_brain.stage3.acquisition.source_artifact_provenance import (
    SourceCorrespondenceStatus,
)

M336K_PROTOCOL_VERSION = "m336k.candidate-isolated-acquisition.v1"
M336K_ACQUISITION_EVENTS = (
    "AUTHORIZATION_VALIDATED",
    "ACQUISITION_RESERVED",
    "ACQUISITION_STARTED",
    "ALL_CANDIDATES_TERMINAL",
    "ACQUISITION_COMPLETED",
)
_OPTIONAL_FETCH_ERRORS = (
    urllib.error.HTTPError,
    urllib.error.URLError,
    TimeoutError,
    ConnectionError,
    subprocess.CalledProcessError,
    subprocess.TimeoutExpired,
)
_COMPLETE = frozenset(
    {
        SourceCorrespondenceStatus.RAW_EXACT_MATCH,
        SourceCorrespondenceStatus.CANONICAL_TEXT_EXACT_MATCH,
        SourceCorrespondenceStatus.PATH_RELOCATED_RAW_MATCH,
        SourceCorrespondenceStatus.PATH_RELOCATED_CANONICAL_MATCH,
        SourceCorrespondenceStatus.GENERATED_WITH_VERIFIED_PROVENANCE,
    }
)


class CandidateAcquisitionStage(str, Enum):
    SOURCE_FETCH = "SOURCE_FETCH"
    SOURCE_ARCHIVE_INSPECTION = "SOURCE_ARCHIVE_INSPECTION"
    POM_FETCH = "POM_FETCH"
    POM_VERIFICATION = "POM_VERIFICATION"
    SCM_FETCH = "SCM_FETCH"
    SCM_VERIFICATION = "SCM_VERIFICATION"
    CORRESPONDENCE = "CORRESPONDENCE"
    LICENSE = "LICENSE"
    DISCLOSURE = "DISCLOSURE"
    COMPLETE = "COMPLETE"


class CandidateFailureScope(str, Enum):
    CANDIDATE = "CANDIDATE"
    NONE = "NONE"
    GLOBAL = "GLOBAL"


class CandidateTerminalStatus(str, Enum):
    ELIGIBLE_FOR_QUALIFICATION = "ELIGIBLE_FOR_QUALIFICATION"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INELIGIBLE_ARCHIVE = "INELIGIBLE_ARCHIVE"
    INELIGIBLE_PROVENANCE = "INELIGIBLE_PROVENANCE"
    INELIGIBLE_LICENSE = "INELIGIBLE_LICENSE"
    INELIGIBLE_CORRESPONDENCE = "INELIGIBLE_CORRESPONDENCE"
    FETCH_FAILED_OPTIONAL = "FETCH_FAILED_OPTIONAL"
    METADATA_DRIFT = "METADATA_DRIFT"
    DENYLISTED = "DENYLISTED"
    DISCLOSED_IDENTITY_OVERLAP = "DISCLOSED_IDENTITY_OVERLAP"


@dataclass(frozen=True)
class CandidateTerminalReceipt:
    schema_version: int
    candidate_family_id: str
    coordinate: str
    candidate_policy_hash: str
    acquisition_run_id: str
    source_receipt_hash: str | None
    pom_receipt_hash: str | None
    scm_receipt_hash: str | None
    archive_inspection_receipt_hash: str | None
    archive_inspection_binding_hash: str | None
    retained_private_artifact_hashes: tuple[tuple[str, str], ...]
    failure_stage: CandidateAcquisitionStage
    failure_scope: CandidateFailureScope
    normalized_reason_codes: tuple[str, ...]
    eligible: bool
    terminal_status: CandidateTerminalStatus
    receipt_hash: str


@dataclass(frozen=True)
class CandidateAcquisitionOutcome:
    terminal_receipt: CandidateTerminalReceipt
    pipeline_item: dict
    archive_result: ArchiveInspectionResultV2 | None
    archive_binding: CandidateArchiveInspectionBinding | None
    authoritative_archive_inspection_count: int


@dataclass(frozen=True)
class M336KAcquisitionLedgerEvent:
    schema_version: int
    protocol_version: str
    event: str
    ordinal: int
    context_hash: str
    operation_hash: str
    previous_event_hash: str | None
    event_hash: str


@dataclass(frozen=True)
class M336KAcquisitionLedgerReceipt:
    schema_version: int
    protocol_version: str
    context_hash: str | None
    event_count: int
    final_event: str | None
    authorization_validation_count: int
    acquisition_reservation_count: int
    acquisition_start_count: int
    all_candidates_terminal_count: int
    acquisition_completion_count: int
    acquisition_failure_count: int
    acquisition_rerun_count: int
    ledger_bytes_hash: str
    receipt_hash: str


@dataclass(frozen=True)
class M336KGlobalAcquisitionReceipt:
    schema_version: int
    acquisition_run_id: str
    candidate_count: int
    attempted_count: int
    terminal_count: int
    eligible_count: int
    review_count: int
    rejected_count_by_reason: tuple[tuple[str, int], ...]
    fetch_failed_count: int
    missing_terminal_count: int
    duplicate_terminal_count: int
    unexpected_global_failure_count: int
    candidate_retry_count: int
    candidate_replacement_count: int
    authoritative_archive_inspection_count: int
    candidate_terminal_manifest_hash: str
    vault_manifest_hash: str
    status: str
    receipt_hash: str


@dataclass(frozen=True)
class M336KCandidateIsolatedAcquisition:
    candidate_outcomes: tuple[CandidateAcquisitionOutcome, ...]
    global_receipt: M336KGlobalAcquisitionReceipt
    ledger_receipt: M336KAcquisitionLedgerReceipt


class CandidateLocalFailure(RuntimeError):
    """Closed, explicitly typed candidate-local failure from a provider adapter."""

    def __init__(
        self,
        *,
        status: CandidateTerminalStatus,
        stage: CandidateAcquisitionStage,
        reason_code: str,
    ) -> None:
        super().__init__(reason_code)
        self.status = status
        self.stage = stage
        self.reason_code = reason_code


class M336KAcquisitionLedger:
    """Fsync-backed one-shot ledger with explicit all-candidates terminal state."""

    def __init__(self, path: Path, *, git_worktrees: Iterable[Path] = ()):
        self.path = path.resolve(strict=False)
        roots = tuple(Path(item).resolve(strict=True) for item in git_worktrees)
        if any(_is_relative_to(self.path, root) for root in roots):
            raise ValueError("M336K acquisition ledger must remain outside Git")

    def events(self) -> tuple[M336KAcquisitionLedgerEvent, ...]:
        if not self.path.exists():
            return ()
        raw = self.path.read_bytes()
        if raw and (b"\r" in raw or not raw.endswith(b"\n")):
            raise ValueError("M336K acquisition ledger is not canonical LF JSONL")
        rows = []
        previous = None
        context = None
        for ordinal, line in enumerate(raw.splitlines()):
            value = _strict_json(line)
            if set(value) != set(M336KAcquisitionLedgerEvent.__dataclass_fields__):
                raise ValueError("M336K acquisition event fields changed")
            event = M336KAcquisitionLedgerEvent(**value)
            body = asdict(event)
            claimed = body.pop("event_hash")
            if (
                event.schema_version != 1
                or event.protocol_version != M336K_PROTOCOL_VERSION
                or event.ordinal != ordinal
                or event.previous_event_hash != previous
                or content_hash(body) != claimed
            ):
                raise ValueError("M336K acquisition ledger hash chain is invalid")
            if context is None:
                context = event.context_hash
            elif context != event.context_hash:
                raise ValueError("M336K acquisition context changed")
            rows.append(event)
            previous = event.event_hash
        _verify_event_order(tuple(rows))
        return tuple(rows)

    def append(self, event: str, *, context_hash: str, operation_hash: str) -> None:
        lock = self.path.with_name(self.path.name + ".lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = None
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, b"M336K_ACQUISITION_LOCK\n")
            os.fsync(descriptor)
            prior = self.events()
            if prior and prior[-1].event in {
                "ACQUISITION_COMPLETED",
                "ACQUISITION_FAILED",
            }:
                raise ValueError("M336K acquisition ledger is terminal")
            if event == "ACQUISITION_FAILED":
                if not prior or prior[-1].event not in {
                    "ACQUISITION_RESERVED",
                    "ACQUISITION_STARTED",
                    "ALL_CANDIDATES_TERMINAL",
                }:
                    raise ValueError("M336K acquisition failure boundary is invalid")
            elif event != M336K_ACQUISITION_EVENTS[len(prior)]:
                raise ValueError("M336K acquisition event is out of order or repeated")
            if prior and prior[0].context_hash != context_hash:
                raise ValueError("M336K acquisition context changed")
            body = {
                "schema_version": 1,
                "protocol_version": M336K_PROTOCOL_VERSION,
                "event": event,
                "ordinal": len(prior),
                "context_hash": context_hash,
                "operation_hash": operation_hash,
                "previous_event_hash": prior[-1].event_hash if prior else None,
            }
            encoded = (
                canonical_json({**body, "event_hash": content_hash(body)}) + "\n"
            ).encode()
            with self.path.open("ab") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            self.events()
        finally:
            if descriptor is not None:
                os.close(descriptor)
                lock.unlink(missing_ok=True)

    def receipt(self) -> M336KAcquisitionLedgerReceipt:
        events = self.events()
        counts = Counter(item.event for item in events)
        body = {
            "schema_version": 1,
            "protocol_version": M336K_PROTOCOL_VERSION,
            "context_hash": events[0].context_hash if events else None,
            "event_count": len(events),
            "final_event": events[-1].event if events else None,
            "authorization_validation_count": counts["AUTHORIZATION_VALIDATED"],
            "acquisition_reservation_count": counts["ACQUISITION_RESERVED"],
            "acquisition_start_count": counts["ACQUISITION_STARTED"],
            "all_candidates_terminal_count": counts["ALL_CANDIDATES_TERMINAL"],
            "acquisition_completion_count": counts["ACQUISITION_COMPLETED"],
            "acquisition_failure_count": counts["ACQUISITION_FAILED"],
            "acquisition_rerun_count": max(0, counts["ACQUISITION_STARTED"] - 1),
            "ledger_bytes_hash": bytes_hash(self.path.read_bytes())
            if self.path.exists()
            else bytes_hash(b""),
        }
        return M336KAcquisitionLedgerReceipt(**body, receipt_hash=content_hash(body))


def acquire_candidate_v2(
    policy: dict,
    *,
    vault_root: Path,
    acquisition_run_id: str,
    maven: MavenCentralProvenanceProvider,
    scm: ScmRevisionProvider,
    archive_policy: ArchiveInspectionPolicyV2 | None = None,
) -> CandidateAcquisitionOutcome:
    """Acquire all candidate roles and return exactly one typed terminal result."""

    family = policy["family_id"]
    if not family or any(character in family for character in "/\\"):
        raise ValueError("candidate family ID is not a safe vault segment")
    root = vault_root / "candidates" / family
    root.mkdir(parents=True, exist_ok=False)
    coordinate = maven_coordinate(
        group_id=policy["group_id"],
        artifact_id=policy["artifact_id"],
        version=policy["version"],
    )
    active_archive_policy = archive_policy or ArchiveInspectionPolicyV2.frozen_default()
    started = time.perf_counter()
    reasons: list[str] = []
    status: CandidateTerminalStatus | None = None
    failure_stage = CandidateAcquisitionStage.COMPLETE
    retained: list[tuple[str, str]] = []
    source = pom = revision = None
    inspection = None
    binding = None
    correspondence = None
    inventory = None
    vault_files = []

    try:
        source = maven.fetch_sources(coordinate)
    except _OPTIONAL_FETCH_ERRORS:
        status = CandidateTerminalStatus.FETCH_FAILED_OPTIONAL
        failure_stage = CandidateAcquisitionStage.SOURCE_FETCH
        reasons.append("OPTIONAL_SOURCE_FETCH_FAILED")
    if source is not None:
        source_hash = source.digest.downloaded_bytes_sha256
        source_path = root / "source.jar"
        source_path.write_bytes(source.payload)
        retained.append(("SOURCE_JAR", source_hash))
        vault_files.append(
            (
                _relative(vault_root, source_path),
                family,
                LocalVaultRole.SOURCE_JAR,
                content_hash(policy["coordinate"]),
            )
        )
        metadata_drift = (
            len(source.payload) != policy["source_content_length"]
            or source.digest.sidecar_verified
            is not policy["source_sha256_sidecar_available"]
            or (
                policy["source_sha256_sidecar_value"] is not None
                and source_hash != policy["source_sha256_sidecar_value"]
            )
            or (source.digest.detached_signature_url is not None)
            is not policy["source_signature_available"]
        )
        if metadata_drift:
            status = CandidateTerminalStatus.METADATA_DRIFT
            failure_stage = CandidateAcquisitionStage.SOURCE_FETCH
            reasons.append("SOURCE_METADATA_DRIFT")
        inspection = inspect_source_archive_v2(
            source.payload, policy=active_archive_policy
        )
        binding = build_candidate_archive_inspection_binding(
            candidate_identity=(family, policy["coordinate"]), result=inspection
        )
        if not archive_decision_is_accepted(inspection.receipt.decision):
            status = CandidateTerminalStatus.INELIGIBLE_ARCHIVE
            failure_stage = CandidateAcquisitionStage.SOURCE_ARCHIVE_INSPECTION
            reasons.extend(item.reason_code for item in inspection.receipt.anomalies)
        else:
            sources = root / "sources"
            sources.mkdir()
            for relative, raw in inspection.java_entries:
                destination = sources.joinpath(*PurePosixPath(relative).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
                vault_files.append(
                    (
                        _relative(vault_root, destination),
                        family,
                        LocalVaultRole.JAVA_SOURCE,
                        source_hash,
                    )
                )

    try:
        pom = maven.fetch_pom(coordinate)
    except _OPTIONAL_FETCH_ERRORS:
        if status is None:
            status = CandidateTerminalStatus.FETCH_FAILED_OPTIONAL
            failure_stage = CandidateAcquisitionStage.POM_FETCH
        reasons.append("OPTIONAL_POM_FETCH_FAILED")
    if pom is not None:
        pom_hash = bytes_hash(pom.payload)
        pom_path = root / "pom.xml"
        pom_path.write_bytes(pom.payload)
        retained.append(("POM", pom_hash))
        vault_files.append(
            (
                _relative(vault_root, pom_path),
                family,
                LocalVaultRole.POM,
                content_hash(policy["coordinate"]),
            )
        )
        if pom_hash != policy["metadata_pom_sha256"]:
            if status is None:
                status = CandidateTerminalStatus.METADATA_DRIFT
                failure_stage = CandidateAcquisitionStage.POM_VERIFICATION
            reasons.append("POM_METADATA_DRIFT")

    try:
        revision = scm.verify(
            repository_url=policy["scm_repository"], requested_ref=policy["scm_ref"]
        )
    except _OPTIONAL_FETCH_ERRORS:
        if status is None:
            status = CandidateTerminalStatus.FETCH_FAILED_OPTIONAL
            failure_stage = CandidateAcquisitionStage.SCM_FETCH
        reasons.append("OPTIONAL_SCM_FETCH_FAILED")
    except ValueError as exc:
        reason = _closed_scm_value_error(exc)
        if status is None:
            status = CandidateTerminalStatus.METADATA_DRIFT
            failure_stage = CandidateAcquisitionStage.SCM_VERIFICATION
        reasons.append(reason)
    if revision is not None:
        scm_hash = bytes_hash(revision.archive_payload)
        scm_path = root / "scm.zip"
        scm_path.write_bytes(revision.archive_payload)
        retained.append(("SCM_ARCHIVE", scm_hash))
        vault_files.append(
            (
                _relative(vault_root, scm_path),
                family,
                LocalVaultRole.SCM_ARCHIVE,
                content_hash(policy["scm_commit"]),
            )
        )
        if revision.receipt.immutable_commit != policy["scm_commit"]:
            if status is None:
                status = CandidateTerminalStatus.METADATA_DRIFT
                failure_stage = CandidateAcquisitionStage.SCM_VERIFICATION
            reasons.append("SCM_IMMUTABLE_COMMIT_DRIFT")

    if (
        inspection is not None
        and archive_decision_is_accepted(inspection.receipt.decision)
        and revision is not None
    ):
        try:
            correspondence = correspond_source_trees(
                inspection.java_entries,
                revision.java_entries,
                repository_path_prefixes=tuple(policy["repository_source_prefixes"]),
            )
        except ValueError:
            if status is None:
                status = CandidateTerminalStatus.INELIGIBLE_CORRESPONDENCE
                failure_stage = CandidateAcquisitionStage.CORRESPONDENCE
            reasons.append("SOURCE_TREE_CORRESPONDENCE_INVALID")
        if correspondence is not None:
            try:
                inventory = inventory_legal_documents(
                    (
                        LegalDocumentContainer(
                            "source-jar", _accepted_entry_archive(inspection)
                        ),
                        LegalDocumentContainer("scm-archive", revision.archive_payload),
                    )
                )
            except (ValueError, zipfile.BadZipFile, UnicodeError):
                if status is None:
                    status = CandidateTerminalStatus.INELIGIBLE_LICENSE
                    failure_stage = CandidateAcquisitionStage.LICENSE
                reasons.append("LICENSE_EVIDENCE_INVALID")

    automatic_licenses = _automatic_license_expressions(policy, inventory)
    if inventory is not None and (
        inventory.unclassified_document_count or inventory.unknown_role_count
    ):
        if status is None:
            status = CandidateTerminalStatus.REVIEW_REQUIRED
            failure_stage = CandidateAcquisitionStage.LICENSE
        reasons.append("UNKNOWN_LICENSE_DOCUMENT")

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
    if status is None and not complete_entries:
        status = CandidateTerminalStatus.INELIGIBLE_CORRESPONDENCE
        failure_stage = CandidateAcquisitionStage.CORRESPONDENCE
        reasons.append("NO_COMPLETE_SOURCE_CORRESPONDENCE")
    if status is None and not automatic_licenses:
        status = CandidateTerminalStatus.INELIGIBLE_LICENSE
        failure_stage = CandidateAcquisitionStage.LICENSE
        reasons.append("NO_AUTOMATIC_LICENSE_EVIDENCE")
    if status is None:
        status = CandidateTerminalStatus.ELIGIBLE_FOR_QUALIFICATION
        failure_stage = CandidateAcquisitionStage.COMPLETE
        reasons.append("CANDIDATE_ACQUISITION_COMPLETE")

    eligible = status is CandidateTerminalStatus.ELIGIBLE_FOR_QUALIFICATION
    source_hash = source.digest.downloaded_bytes_sha256 if source else "0" * 64
    pom_hash = bytes_hash(pom.payload) if pom else "0" * 64
    scm_hash = bytes_hash(revision.archive_payload) if revision else "0" * 64
    commit = revision.receipt.immutable_commit if revision else "0" * 40
    tree_hash = revision.receipt.source_tree_hash if revision else "0" * 64
    public_correspondence = (
        asdict(derive_scm_correspondence_decision(correspondence, selected_paths=()))
        if correspondence
        else None
    )
    terminal = build_candidate_terminal_receipt(
        policy=policy,
        acquisition_run_id=acquisition_run_id,
        status=status,
        failure_stage=failure_stage,
        reason_codes=tuple(reasons),
        source_receipt_hash=(
            source.repository.network_receipt_hash if source else None
        ),
        pom_receipt_hash=(pom.repository.network_receipt_hash if pom else None),
        scm_receipt_hash=(revision.receipt.receipt_hash if revision else None),
        archive_result=inspection,
        archive_binding=binding,
        retained_private_artifact_hashes=tuple(retained),
    )
    item = {
        "family_id": family,
        "organization_id": policy["organization_id"],
        "coordinate": policy["coordinate"],
        "source_url": policy["source_url"],
        "source_jar_sha256": source_hash,
        "source_jar_size": len(source.payload) if source else 0,
        "pom_sha256": pom_hash,
        "immutable_scm_commit": commit,
        "scm_archive_sha256": scm_hash,
        "scm_archive_size": len(revision.archive_payload) if revision else 0,
        "source_tree_hash": tree_hash,
        "artifact_authenticity_mode": "MAVEN_CENTRAL_PLUS_IMMUTABLE_SCM"
        if source and revision
        else "INCOMPLETE",
        "scoped_license_expressions": automatic_licenses,
        "legal_document_count": inventory.discovered_document_count if inventory else 0,
        "unclassified_legal_document_count": inventory.unclassified_document_count
        if inventory
        else 0,
        "unknown_legal_document_role_count": inventory.unknown_role_count
        if inventory
        else 0,
        "correspondence": public_correspondence,
        "correspondence_complete_for_all_entries": all_correspond,
        "complete_correspondence_paths": complete_entries,
        "analysis_eligible": eligible,
        "candidate_eligible_source_entry_count": len(complete_entries)
        if eligible
        else 0,
        "qualification_errors": tuple(reasons) if not eligible else (),
        "candidate_terminal_receipt": terminal,
        "archive_inspection_binding": binding,
        "_archive_inspection_result": inspection,
        "_raw_source_hashes": tuple(
            sorted(
                item.payload_hash
                for item in (inspection.receipt.entries if inspection else ())
                if item.payload_hash is not None
                and item.canonical_posix_path.endswith(".java")
            )
        ),
        "_canonical_source_hashes": tuple(
            sorted(
                item.canonical_source_hash
                for item in (inspection.receipt.entries if inspection else ())
                if item.canonical_source_hash is not None
            )
        ),
        "_archive_java_paths": tuple(
            path for path, _raw in (inspection.java_entries if inspection else ())
        ),
        "_legal_inventory_rows": tuple(inventory.rows) if inventory else (),
        "_vault_files": tuple(vault_files),
        "_performance_seconds": {
            "candidate_acquisition_v2": time.perf_counter() - started
        },
    }
    return CandidateAcquisitionOutcome(
        terminal, item, inspection, binding, 1 if inspection else 0
    )


def recover_disclosed_candidate_v2(
    policy: dict,
    *,
    preserved_vault_root: Path,
    destination_vault_root: Path,
    acquisition_run_id: str,
    archive_policy: ArchiveInspectionPolicyV2 | None = None,
) -> CandidateAcquisitionOutcome:
    """Replay one F26 candidate offline into a separate rehearsal vault."""

    family = policy["family_id"]
    source_root = preserved_vault_root / "candidates" / family
    destination_root = destination_vault_root / "candidates" / family
    destination_root.mkdir(parents=True, exist_ok=False)
    source_path = source_root / "source.jar"
    pom_path = source_root / "pom.xml"
    scm_path = source_root / "scm.zip"
    if not source_path.is_file() or not pom_path.is_file() or not scm_path.is_file():
        raise RuntimeError("preserved F26 candidate artifact is missing")
    source_raw = source_path.read_bytes()
    pom_raw = pom_path.read_bytes()
    scm_raw = scm_path.read_bytes()
    inspection = inspect_source_archive_v2(source_raw, policy=archive_policy)
    binding = build_candidate_archive_inspection_binding(
        candidate_identity=(family, policy["coordinate"]), result=inspection
    )
    for name, raw in (
        ("source.jar", source_raw),
        ("pom.xml", pom_raw),
        ("scm.zip", scm_raw),
    ):
        (destination_root / name).write_bytes(raw)
    retained = (
        ("POM", bytes_hash(pom_raw)),
        ("SCM_ARCHIVE", bytes_hash(scm_raw)),
        ("SOURCE_JAR", bytes_hash(source_raw)),
    )
    vault_files = (
        (
            _relative(destination_vault_root, destination_root / "source.jar"),
            family,
            LocalVaultRole.SOURCE_JAR,
            content_hash(policy["coordinate"]),
        ),
        (
            _relative(destination_vault_root, destination_root / "pom.xml"),
            family,
            LocalVaultRole.POM,
            content_hash(policy["coordinate"]),
        ),
        (
            _relative(destination_vault_root, destination_root / "scm.zip"),
            family,
            LocalVaultRole.SCM_ARCHIVE,
            content_hash(policy["scm_commit"]),
        ),
    )
    reasons = []
    status = None
    stage = CandidateAcquisitionStage.COMPLETE
    correspondence = None
    inventory = None
    scm_java = ()
    tree_hash = "0" * 64
    if bytes_hash(pom_raw) != policy["metadata_pom_sha256"]:
        status = CandidateTerminalStatus.METADATA_DRIFT
        stage = CandidateAcquisitionStage.POM_VERIFICATION
        reasons.append("POM_METADATA_DRIFT")
    if not archive_decision_is_accepted(inspection.receipt.decision):
        status = CandidateTerminalStatus.INELIGIBLE_ARCHIVE
        stage = CandidateAcquisitionStage.SOURCE_ARCHIVE_INSPECTION
        reasons.extend(item.reason_code for item in inspection.receipt.anomalies)
    else:
        sources = destination_root / "sources"
        sources.mkdir()
        for relative, raw in inspection.java_entries:
            target = sources.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    try:
        scm_java, _scm_licenses, tree_hash = _inspect_github_archive(scm_raw)
    except ValueError as exc:
        reason = _closed_scm_value_error(exc)
        if status is None:
            status = CandidateTerminalStatus.INELIGIBLE_PROVENANCE
            stage = CandidateAcquisitionStage.SCM_VERIFICATION
        reasons.append(reason)
    if archive_decision_is_accepted(inspection.receipt.decision) and scm_java:
        try:
            correspondence = correspond_source_trees(
                inspection.java_entries,
                scm_java,
                repository_path_prefixes=tuple(policy["repository_source_prefixes"]),
            )
        except ValueError:
            if status is None:
                status = CandidateTerminalStatus.INELIGIBLE_CORRESPONDENCE
                stage = CandidateAcquisitionStage.CORRESPONDENCE
            reasons.append("SOURCE_TREE_CORRESPONDENCE_INVALID")
        if correspondence is not None:
            try:
                inventory = inventory_legal_documents(
                    (
                        LegalDocumentContainer(
                            "source-jar", _accepted_entry_archive(inspection)
                        ),
                        LegalDocumentContainer("scm-archive", scm_raw),
                    )
                )
            except (ValueError, zipfile.BadZipFile, UnicodeError):
                if status is None:
                    status = CandidateTerminalStatus.INELIGIBLE_LICENSE
                    stage = CandidateAcquisitionStage.LICENSE
                reasons.append("LICENSE_EVIDENCE_INVALID")
    automatic_licenses = _automatic_license_expressions(policy, inventory)
    complete_entries = tuple(
        row.artifact_path
        for row in (correspondence.entries if correspondence else ())
        if row.status in _COMPLETE
    )
    if status is None and not complete_entries:
        status = CandidateTerminalStatus.INELIGIBLE_CORRESPONDENCE
        stage = CandidateAcquisitionStage.CORRESPONDENCE
        reasons.append("NO_COMPLETE_SOURCE_CORRESPONDENCE")
    if status is None and not automatic_licenses:
        status = CandidateTerminalStatus.INELIGIBLE_LICENSE
        stage = CandidateAcquisitionStage.LICENSE
        reasons.append("NO_AUTOMATIC_LICENSE_EVIDENCE")
    if status is None:
        status = CandidateTerminalStatus.ELIGIBLE_FOR_QUALIFICATION
        reasons.append("CANDIDATE_ACQUISITION_COMPLETE")
    eligible = status is CandidateTerminalStatus.ELIGIBLE_FOR_QUALIFICATION
    terminal = build_candidate_terminal_receipt(
        policy=policy,
        acquisition_run_id=acquisition_run_id,
        status=status,
        failure_stage=stage,
        reason_codes=tuple(reasons),
        source_receipt_hash=content_hash(("F26_SEALED_SOURCE", bytes_hash(source_raw))),
        pom_receipt_hash=content_hash(("F26_SEALED_POM", bytes_hash(pom_raw))),
        scm_receipt_hash=content_hash(("F26_SEALED_SCM", bytes_hash(scm_raw))),
        archive_result=inspection,
        archive_binding=binding,
        retained_private_artifact_hashes=retained,
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
        "unclassified_legal_document_count": inventory.unclassified_document_count
        if inventory
        else 0,
        "unknown_legal_document_role_count": inventory.unknown_role_count
        if inventory
        else 0,
        "correspondence": public_correspondence,
        "correspondence_complete_for_all_entries": bool(
            correspondence
            and not correspondence.unmatched_count
            and not correspondence.ambiguous_count
        ),
        "complete_correspondence_paths": complete_entries,
        "analysis_eligible": eligible,
        "candidate_eligible_source_entry_count": len(complete_entries)
        if eligible
        else 0,
        "qualification_errors": tuple(reasons) if not eligible else (),
        "candidate_terminal_receipt": terminal,
        "archive_inspection_binding": binding,
        "_archive_inspection_result": inspection,
        "_raw_source_hashes": tuple(
            sorted(
                entry.payload_hash
                for entry in inspection.receipt.entries
                if entry.payload_hash is not None
                and entry.canonical_posix_path.endswith(".java")
            )
        ),
        "_canonical_source_hashes": tuple(
            sorted(
                entry.canonical_source_hash
                for entry in inspection.receipt.entries
                if entry.canonical_source_hash is not None
            )
        ),
        "_archive_java_paths": tuple(path for path, _raw in inspection.java_entries),
        "_legal_inventory_rows": tuple(inventory.rows) if inventory else (),
        "_vault_files": vault_files,
        "_performance_seconds": {"offline_f26_recovery_v2": 0},
    }
    return CandidateAcquisitionOutcome(terminal, item, inspection, binding, 1)


def run_candidate_isolated_acquisition(
    *,
    candidates: tuple[dict, ...],
    vault_root: Path,
    ledger: M336KAcquisitionLedger,
    acquisition_run_id: str,
    authorization_hash: str,
    pool_hash: str,
    attempt: Callable[[dict], CandidateAcquisitionOutcome],
) -> M336KCandidateIsolatedAcquisition:
    """Attempt every optional candidate once; only typed local failures continue."""

    if ledger.events() or vault_root.exists():
        raise FileExistsError("M336K acquisition destinations must be fresh")
    families = tuple(item["family_id"] for item in candidates)
    if len(families) != len(set(families)) or any(
        item.get("requirement") != "OPTIONAL" for item in candidates
    ):
        raise ValueError("M336K candidate pool must be unique and all optional")
    context_hash = content_hash((acquisition_run_id, authorization_hash, pool_hash))
    ledger.append(
        "AUTHORIZATION_VALIDATED",
        context_hash=context_hash,
        operation_hash=authorization_hash,
    )
    ledger.append(
        "ACQUISITION_RESERVED", context_hash=context_hash, operation_hash=pool_hash
    )
    ledger.append(
        "ACQUISITION_STARTED",
        context_hash=context_hash,
        operation_hash=content_hash(families),
    )
    vault_root.mkdir(parents=True)
    outcomes = []
    attempted = []
    try:
        for policy in candidates:
            family = policy["family_id"]
            attempted.append(family)
            try:
                outcome = attempt(policy)
            except CandidateLocalFailure as failure:
                terminal = build_candidate_terminal_receipt(
                    policy=policy,
                    acquisition_run_id=acquisition_run_id,
                    status=failure.status,
                    failure_stage=failure.stage,
                    reason_codes=(failure.reason_code,),
                )
                outcome = CandidateAcquisitionOutcome(
                    terminal,
                    _minimal_pipeline_item(policy, terminal),
                    None,
                    None,
                    0,
                )
            if outcome.terminal_receipt.candidate_family_id != family:
                raise RuntimeError("candidate terminal receipt identity mismatch")
            outcomes.append(outcome)
        terminal_families = tuple(
            item.terminal_receipt.candidate_family_id for item in outcomes
        )
        if terminal_families != tuple(attempted) or len(set(terminal_families)) != len(
            terminal_families
        ):
            raise RuntimeError(
                "candidate terminal accounting is incomplete or duplicated"
            )
        terminal_hash = content_hash(
            tuple(item.terminal_receipt.receipt_hash for item in outcomes)
        )
        ledger.append(
            "ALL_CANDIDATES_TERMINAL",
            context_hash=context_hash,
            operation_hash=terminal_hash,
        )
        vault_hash = _vault_manifest_hash(vault_root)
        receipt = build_global_acquisition_receipt(
            acquisition_run_id=acquisition_run_id,
            candidate_count=len(candidates),
            attempted_count=len(attempted),
            outcomes=tuple(outcomes),
            vault_manifest_hash=vault_hash,
        )
        ledger.append(
            "ACQUISITION_COMPLETED",
            context_hash=context_hash,
            operation_hash=receipt.receipt_hash,
        )
        return M336KCandidateIsolatedAcquisition(
            tuple(outcomes), receipt, ledger.receipt()
        )
    except (KeyboardInterrupt, SystemExit):
        raise
    except CandidateLocalFailure:
        raise RuntimeError(
            "typed candidate-local failure escaped its candidate boundary"
        )
    except Exception as error:
        ledger.append(
            "ACQUISITION_FAILED",
            context_hash=context_hash,
            operation_hash=content_hash(type(error).__name__),
        )
        raise


def build_candidate_terminal_receipt(
    *,
    policy: dict,
    acquisition_run_id: str,
    status: CandidateTerminalStatus,
    failure_stage: CandidateAcquisitionStage,
    reason_codes: tuple[str, ...],
    source_receipt_hash: str | None = None,
    pom_receipt_hash: str | None = None,
    scm_receipt_hash: str | None = None,
    archive_result: ArchiveInspectionResultV2 | None = None,
    archive_binding: CandidateArchiveInspectionBinding | None = None,
    retained_private_artifact_hashes: tuple[tuple[str, str], ...] = (),
) -> CandidateTerminalReceipt:
    eligible = status is CandidateTerminalStatus.ELIGIBLE_FOR_QUALIFICATION
    body = {
        "schema_version": 1,
        "candidate_family_id": policy["family_id"],
        "coordinate": policy["coordinate"],
        "candidate_policy_hash": policy["policy_hash"],
        "acquisition_run_id": acquisition_run_id,
        "source_receipt_hash": source_receipt_hash,
        "pom_receipt_hash": pom_receipt_hash,
        "scm_receipt_hash": scm_receipt_hash,
        "archive_inspection_receipt_hash": archive_result.receipt.receipt_hash
        if archive_result
        else None,
        "archive_inspection_binding_hash": archive_binding.binding_hash
        if archive_binding
        else None,
        "retained_private_artifact_hashes": tuple(
            sorted(retained_private_artifact_hashes)
        ),
        "failure_stage": failure_stage,
        "failure_scope": CandidateFailureScope.NONE
        if eligible
        else CandidateFailureScope.CANDIDATE,
        "normalized_reason_codes": tuple(sorted(set(reason_codes))),
        "eligible": eligible,
        "terminal_status": status,
    }
    return CandidateTerminalReceipt(**body, receipt_hash=content_hash(body))


def build_global_acquisition_receipt(
    *,
    acquisition_run_id: str,
    candidate_count: int,
    attempted_count: int,
    outcomes: tuple[CandidateAcquisitionOutcome, ...],
    vault_manifest_hash: str,
) -> M336KGlobalAcquisitionReceipt:
    terminals = tuple(item.terminal_receipt for item in outcomes)
    families = tuple(item.candidate_family_id for item in terminals)
    duplicate_count = len(families) - len(set(families))
    missing_count = candidate_count - len(terminals)
    statuses = Counter(item.terminal_status.value for item in terminals)
    reasons = Counter(
        reason
        for item in terminals
        for reason in item.normalized_reason_codes
        if not item.eligible
    )
    body = {
        "schema_version": 1,
        "acquisition_run_id": acquisition_run_id,
        "candidate_count": candidate_count,
        "attempted_count": attempted_count,
        "terminal_count": len(terminals),
        "eligible_count": statuses[
            CandidateTerminalStatus.ELIGIBLE_FOR_QUALIFICATION.value
        ],
        "review_count": statuses[CandidateTerminalStatus.REVIEW_REQUIRED.value],
        "rejected_count_by_reason": tuple(sorted(reasons.items())),
        "fetch_failed_count": statuses[
            CandidateTerminalStatus.FETCH_FAILED_OPTIONAL.value
        ],
        "missing_terminal_count": missing_count,
        "duplicate_terminal_count": duplicate_count,
        "unexpected_global_failure_count": 0,
        "candidate_retry_count": 0,
        "candidate_replacement_count": 0,
        "authoritative_archive_inspection_count": sum(
            item.authoritative_archive_inspection_count for item in outcomes
        ),
        "candidate_terminal_manifest_hash": content_hash(
            tuple(item.receipt_hash for item in terminals)
        ),
        "vault_manifest_hash": vault_manifest_hash,
        "status": "ACQUISITION_COMPLETED"
        if attempted_count == candidate_count
        and not missing_count
        and not duplicate_count
        else "BLOCKED",
    }
    return M336KGlobalAcquisitionReceipt(**body, receipt_hash=content_hash(body))


def _minimal_pipeline_item(policy: dict, terminal: CandidateTerminalReceipt) -> dict:
    return {
        "family_id": policy["family_id"],
        "organization_id": policy["organization_id"],
        "coordinate": policy["coordinate"],
        "source_url": policy["source_url"],
        "source_jar_sha256": "0" * 64,
        "source_jar_size": 0,
        "pom_sha256": "0" * 64,
        "immutable_scm_commit": "0" * 40,
        "scm_archive_sha256": "0" * 64,
        "scm_archive_size": 0,
        "source_tree_hash": "0" * 64,
        "artifact_authenticity_mode": "INCOMPLETE",
        "scoped_license_expressions": (),
        "legal_document_count": 0,
        "unclassified_legal_document_count": 0,
        "unknown_legal_document_role_count": 0,
        "correspondence": None,
        "correspondence_complete_for_all_entries": False,
        "complete_correspondence_paths": (),
        "analysis_eligible": False,
        "candidate_eligible_source_entry_count": 0,
        "qualification_errors": terminal.normalized_reason_codes,
        "candidate_terminal_receipt": terminal,
        "archive_inspection_binding": None,
        "_archive_inspection_result": None,
        "_raw_source_hashes": (),
        "_canonical_source_hashes": (),
        "_archive_java_paths": (),
        "_legal_inventory_rows": (),
        "_vault_files": (),
        "_performance_seconds": {},
    }


def _accepted_entry_archive(result: ArchiveInspectionResultV2) -> bytes:
    """Repackage already-inspected payloads; never reopen the candidate source JAR."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for path, payload in sorted((*result.java_entries, *result.legal_entries)):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, payload)
    return buffer.getvalue()


def _automatic_license_expressions(policy: dict, inventory) -> tuple[str, ...]:
    """Combine canonical POM declarations with inspected legal-document evidence."""

    candidates = {
        row.spdx_license_id
        for row in (inventory.rows if inventory else ())
        if row.spdx_license_id
    }
    candidates.update(
        row[0]
        for row in policy.get("pom_license_declarations", ())
        if row and row[0] not in {"NOASSERTION", "UNKNOWN"}
    )
    expressions = set()
    for candidate in candidates:
        try:
            expressions.add(parse_spdx_expression(candidate).canonical())
        except ValueError:
            continue
    return tuple(sorted(expressions))


def _closed_scm_value_error(error: ValueError) -> str:
    known = {
        "SCM verification requires an exact frozen tag ref": "SCM_REF_NOT_IMMUTABLE_TAG",
        "frozen SCM ref was not resolved": "SCM_REF_UNRESOLVED",
        "commit-addressed SCM archive left the frozen identity": "SCM_ARCHIVE_IDENTITY_DRIFT",
        "malformed commit-addressed SCM archive": "SCM_ARCHIVE_MALFORMED",
        "SCM archive entry denominator is invalid": "SCM_ARCHIVE_ENTRY_DENOMINATOR_INVALID",
        "SCM archive contains an unsafe path": "SCM_ARCHIVE_UNSAFE_PATH",
        "SCM archive contains a duplicate path": "SCM_ARCHIVE_DUPLICATE_PATH",
        "SCM archive uncompressed size limit exceeded": "SCM_ARCHIVE_SIZE_LIMIT",
    }
    message = str(error)
    for prefix, code in known.items():
        if message.startswith(prefix):
            return code
    raise error


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _vault_manifest_hash(root: Path) -> str:
    rows = tuple(
        (path.relative_to(root).as_posix(), bytes_hash(path.read_bytes()))
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    )
    return content_hash(rows)


def _verify_event_order(events: tuple[M336KAcquisitionLedgerEvent, ...]) -> None:
    names = tuple(item.event for item in events)
    if names and names[-1] == "ACQUISITION_FAILED":
        if names[:-1] not in (
            M336K_ACQUISITION_EVENTS[:2],
            M336K_ACQUISITION_EVENTS[:3],
            M336K_ACQUISITION_EVENTS[:4],
        ):
            raise ValueError("M336K acquisition failure event is out of order")
    elif names != M336K_ACQUISITION_EVENTS[: len(names)]:
        raise ValueError("M336K acquisition event order is invalid")


def _strict_json(raw: bytes) -> dict:
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("M336K ledger JSON contains a duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("M336K ledger JSON is malformed") from exc
    if not isinstance(value, dict):
        raise TypeError("M336K ledger event is not an object")
    return value


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
