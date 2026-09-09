"""Deterministic, candidate-local source archive inspection for M-33.6k."""

from __future__ import annotations

import io
import re
import stat
import unicodedata
import zipfile
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.maven_provenance import (
    MAX_ARCHIVE_ENTRIES,
    MAX_ARCHIVE_ENTRY_BYTES,
    MAX_ARCHIVE_UNCOMPRESSED_BYTES,
    MAX_COMPRESSION_RATIO,
    LicenseTextEvidence,
    canonical_source_bytes,
    license_text_evidence,
)


class ArchiveEntryKindV2(str, Enum):
    DIRECTORY = "DIRECTORY"
    REGULAR_FILE = "REGULAR_FILE"
    SYMLINK = "SYMLINK"
    OTHER = "OTHER"


class ArchiveDuplicateClassV2(str, Enum):
    REDUNDANT_IDENTICAL_DIRECTORY_ENTRY = "REDUNDANT_IDENTICAL_DIRECTORY_ENTRY"
    DUPLICATE_DIRECTORY_METADATA_CONFLICT = "DUPLICATE_DIRECTORY_METADATA_CONFLICT"
    DUPLICATE_IDENTICAL_REGULAR_FILE = "DUPLICATE_IDENTICAL_REGULAR_FILE"
    DUPLICATE_CONFLICTING_REGULAR_FILE = "DUPLICATE_CONFLICTING_REGULAR_FILE"
    FILE_DIRECTORY_PATH_CONFLICT = "FILE_DIRECTORY_PATH_CONFLICT"
    NFC_PATH_COLLISION = "NFC_PATH_COLLISION"
    CASEFOLD_PATH_COLLISION = "CASEFOLD_PATH_COLLISION"
    MALFORMED_DUPLICATE_ENTRY = "MALFORMED_DUPLICATE_ENTRY"
    UNRESOLVED_DUPLICATE_KIND = "UNRESOLVED_DUPLICATE_KIND"


class ArchiveInspectionDecisionV2(str, Enum):
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_REDUNDANT_DIRECTORY_ENTRIES = (
        "ACCEPTED_WITH_REDUNDANT_DIRECTORY_ENTRIES"
    )
    REJECTED_AMBIGUOUS_DUPLICATE_FILE = "REJECTED_AMBIGUOUS_DUPLICATE_FILE"
    REJECTED_CONFLICTING_DUPLICATE_FILE = "REJECTED_CONFLICTING_DUPLICATE_FILE"
    REJECTED_FILE_DIRECTORY_CONFLICT = "REJECTED_FILE_DIRECTORY_CONFLICT"
    REJECTED_NORMALIZATION_COLLISION = "REJECTED_NORMALIZATION_COLLISION"
    REJECTED_PATH_TRAVERSAL = "REJECTED_PATH_TRAVERSAL"
    REJECTED_SYMLINK = "REJECTED_SYMLINK"
    REJECTED_ENCRYPTED = "REJECTED_ENCRYPTED"
    REJECTED_SIZE_LIMIT = "REJECTED_SIZE_LIMIT"
    REJECTED_COMPRESSION_LIMIT = "REJECTED_COMPRESSION_LIMIT"
    REJECTED_MALFORMED = "REJECTED_MALFORMED"
    REJECTED_LICENSE_CONFLICT = "REJECTED_LICENSE_CONFLICT"
    REVIEW_REQUIRED_UNKNOWN_ARCHIVE_CONSTRUCT = (
        "REVIEW_REQUIRED_UNKNOWN_ARCHIVE_CONSTRUCT"
    )


class ArchiveBindingVerificationStatusV2(str, Enum):
    VERIFIED = "VERIFIED"
    SOURCE_HASH_MISMATCH = "SOURCE_HASH_MISMATCH"
    POLICY_HASH_MISMATCH = "POLICY_HASH_MISMATCH"
    RECEIPT_MISMATCH = "RECEIPT_MISMATCH"
    BINDING_HASH_MISMATCH = "BINDING_HASH_MISMATCH"


@dataclass(frozen=True)
class ArchiveInspectionPolicyV2:
    schema_version: int
    policy_version: str
    maximum_entry_count: int
    maximum_total_uncompressed_bytes: int
    maximum_entry_uncompressed_bytes: int
    maximum_compression_ratio: int
    reject_duplicate_regular_files: bool
    allow_compatible_redundant_directories: bool
    reject_nfc_collisions: bool
    reject_casefold_collisions: bool
    policy_hash: str

    @classmethod
    def frozen_default(cls) -> ArchiveInspectionPolicyV2:
        body = {
            "schema_version": 2,
            "policy_version": "m336k.archive-inspection.v2",
            "maximum_entry_count": MAX_ARCHIVE_ENTRIES,
            "maximum_total_uncompressed_bytes": MAX_ARCHIVE_UNCOMPRESSED_BYTES,
            "maximum_entry_uncompressed_bytes": MAX_ARCHIVE_ENTRY_BYTES,
            "maximum_compression_ratio": MAX_COMPRESSION_RATIO,
            "reject_duplicate_regular_files": True,
            "allow_compatible_redundant_directories": True,
            "reject_nfc_collisions": True,
            "reject_casefold_collisions": True,
        }
        return cls(**body, policy_hash=content_hash(body))


@dataclass(frozen=True)
class ArchiveEntryIdentityV2:
    entry_ordinal: int
    canonical_posix_path: str
    original_filename_hash: str
    canonical_path_hash: str
    nfc_path_hash: str
    casefold_path_hash: str
    entry_kind: ArchiveEntryKindV2
    flags: int
    compression_method: int
    crc: int
    compressed_size: int
    uncompressed_size: int
    external_attributes: int
    payload_hash: str | None
    canonical_source_hash: str | None
    entry_metadata_hash: str


@dataclass(frozen=True)
class ArchivePathGroupV2:
    canonical_path_hash: str
    entry_ordinals: tuple[int, ...]
    entry_kinds: tuple[ArchiveEntryKindV2, ...]
    duplicate_class: ArchiveDuplicateClassV2
    payload_equality: bool | None
    metadata_equality: bool
    directory_file_conflict: bool
    downstream_payload_selection_ambiguous: bool
    group_hash: str


@dataclass(frozen=True)
class ArchiveAnomalyV2:
    reason_code: str
    decision: ArchiveInspectionDecisionV2
    entry_ordinals: tuple[int, ...]
    canonical_path_hash: str | None
    anomaly_hash: str


@dataclass(frozen=True)
class ArchiveInspectionReceiptV2:
    schema_version: int
    archive_policy_hash: str
    source_jar_hash: str
    entry_count: int
    total_uncompressed_bytes: int
    java_entry_count: int
    legal_document_count: int
    entries: tuple[ArchiveEntryIdentityV2, ...]
    path_groups: tuple[ArchivePathGroupV2, ...]
    anomalies: tuple[ArchiveAnomalyV2, ...]
    accepted_java_entry_manifest_hash: str
    legal_document_manifest_hash: str
    decision: ArchiveInspectionDecisionV2
    receipt_hash: str


@dataclass(frozen=True)
class CandidateArchiveInspectionBinding:
    schema_version: int
    candidate_identity_hash: str
    source_jar_hash: str
    archive_policy_hash: str
    inspection_receipt_hash: str
    accepted_java_entry_manifest_hash: str
    legal_document_manifest_hash: str
    decision: ArchiveInspectionDecisionV2
    binding_hash: str


@dataclass(frozen=True)
class ArchiveBindingVerificationResultV2:
    schema_version: int
    status: ArchiveBindingVerificationStatusV2
    binding_hash: str
    independently_observed_receipt_hash: str | None
    result_hash: str


@dataclass(frozen=True)
class ArchiveInspectionResultV2:
    receipt: ArchiveInspectionReceiptV2
    java_entries: tuple[tuple[str, bytes], ...]
    legal_entries: tuple[tuple[str, bytes], ...]
    license_evidence: tuple[LicenseTextEvidence, ...]


_DRIVE = re.compile(r"^[A-Za-z]:")
_LEGAL_NAMES = frozenset({"license", "license.txt", "license.md"})
_ACCEPTED = frozenset(
    {
        ArchiveInspectionDecisionV2.ACCEPTED,
        ArchiveInspectionDecisionV2.ACCEPTED_WITH_REDUNDANT_DIRECTORY_ENTRIES,
    }
)
_DECISION_PRIORITY = {
    decision: index
    for index, decision in enumerate(
        (
            ArchiveInspectionDecisionV2.REJECTED_MALFORMED,
            ArchiveInspectionDecisionV2.REJECTED_PATH_TRAVERSAL,
            ArchiveInspectionDecisionV2.REJECTED_SYMLINK,
            ArchiveInspectionDecisionV2.REJECTED_ENCRYPTED,
            ArchiveInspectionDecisionV2.REJECTED_SIZE_LIMIT,
            ArchiveInspectionDecisionV2.REJECTED_COMPRESSION_LIMIT,
            ArchiveInspectionDecisionV2.REJECTED_FILE_DIRECTORY_CONFLICT,
            ArchiveInspectionDecisionV2.REJECTED_NORMALIZATION_COLLISION,
            ArchiveInspectionDecisionV2.REJECTED_CONFLICTING_DUPLICATE_FILE,
            ArchiveInspectionDecisionV2.REJECTED_AMBIGUOUS_DUPLICATE_FILE,
            ArchiveInspectionDecisionV2.REJECTED_LICENSE_CONFLICT,
            ArchiveInspectionDecisionV2.REVIEW_REQUIRED_UNKNOWN_ARCHIVE_CONSTRUCT,
            ArchiveInspectionDecisionV2.ACCEPTED_WITH_REDUNDANT_DIRECTORY_ENTRIES,
            ArchiveInspectionDecisionV2.ACCEPTED,
        )
    )
}


def inspect_source_archive_v2(
    raw: bytes,
    *,
    policy: ArchiveInspectionPolicyV2 | None = None,
) -> ArchiveInspectionResultV2:
    """Inspect once, return a total typed decision, and never extract unsafely."""

    active_policy = policy or ArchiveInspectionPolicyV2.frozen_default()
    _verify_policy(active_policy)
    source_hash = bytes_hash(raw)
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        infos = archive.infolist()
    except (zipfile.BadZipFile, OSError, EOFError, RuntimeError):
        return _terminal_result(
            policy=active_policy,
            source_hash=source_hash,
            decision=ArchiveInspectionDecisionV2.REJECTED_MALFORMED,
            anomalies=(("MALFORMED_CENTRAL_DIRECTORY", (), None),),
        )

    entry_rows: list[ArchiveEntryIdentityV2] = []
    anomalies: list[
        tuple[str, ArchiveInspectionDecisionV2, tuple[int, ...], str | None]
    ] = []
    canonical_by_ordinal: dict[int, str] = {}
    total_uncompressed = 0
    payloads: dict[int, bytes] = {}

    if len(infos) > active_policy.maximum_entry_count:
        anomalies.append(
            (
                "ENTRY_COUNT_LIMIT_EXCEEDED",
                ArchiveInspectionDecisionV2.REJECTED_SIZE_LIMIT,
                (),
                None,
            )
        )

    for ordinal, info in enumerate(infos):
        original_name = info.orig_filename
        path, path_reason = _canonical_path(original_name, info.is_dir())
        canonical_by_ordinal[ordinal] = path
        kind = _entry_kind(info)
        path_hash = bytes_hash(path.encode("utf-8", errors="surrogatepass"))
        if path_reason is not None:
            decision = (
                ArchiveInspectionDecisionV2.REJECTED_PATH_TRAVERSAL
                if path_reason
                in {
                    "PATH_TRAVERSAL",
                    "ABSOLUTE_POSIX_PATH",
                    "WINDOWS_DRIVE_PATH",
                    "UNC_PATH",
                    "NUL_IN_PATH",
                }
                else ArchiveInspectionDecisionV2.REJECTED_NORMALIZATION_COLLISION
            )
            anomalies.append((path_reason, decision, (ordinal,), path_hash))
        if info.flag_bits & 0x1:
            anomalies.append(
                (
                    "ENCRYPTED_ENTRY",
                    ArchiveInspectionDecisionV2.REJECTED_ENCRYPTED,
                    (ordinal,),
                    path_hash,
                )
            )
        if kind is ArchiveEntryKindV2.SYMLINK:
            anomalies.append(
                (
                    "SYMLINK_ENTRY",
                    ArchiveInspectionDecisionV2.REJECTED_SYMLINK,
                    (ordinal,),
                    path_hash,
                )
            )
        elif kind is ArchiveEntryKindV2.OTHER:
            anomalies.append(
                (
                    "UNKNOWN_ENTRY_KIND",
                    ArchiveInspectionDecisionV2.REVIEW_REQUIRED_UNKNOWN_ARCHIVE_CONSTRUCT,
                    (ordinal,),
                    path_hash,
                )
            )
        total_uncompressed += info.file_size
        if (
            info.file_size > active_policy.maximum_entry_uncompressed_bytes
            or total_uncompressed > active_policy.maximum_total_uncompressed_bytes
        ):
            anomalies.append(
                (
                    "UNCOMPRESSED_SIZE_LIMIT_EXCEEDED",
                    ArchiveInspectionDecisionV2.REJECTED_SIZE_LIMIT,
                    (ordinal,),
                    path_hash,
                )
            )
        if info.file_size and info.compress_size == 0:
            anomalies.append(
                (
                    "INVALID_ZERO_COMPRESSED_SIZE",
                    ArchiveInspectionDecisionV2.REJECTED_COMPRESSION_LIMIT,
                    (ordinal,),
                    path_hash,
                )
            )
        elif (
            info.compress_size
            and info.file_size / info.compress_size
            > active_policy.maximum_compression_ratio
        ):
            anomalies.append(
                (
                    "COMPRESSION_RATIO_LIMIT_EXCEEDED",
                    ArchiveInspectionDecisionV2.REJECTED_COMPRESSION_LIMIT,
                    (ordinal,),
                    path_hash,
                )
            )

        payload_hash = None
        canonical_source_hash = None
        if (
            kind is ArchiveEntryKindV2.REGULAR_FILE
            and not (info.flag_bits & 0x1)
            and path_reason is None
            and info.file_size <= active_policy.maximum_entry_uncompressed_bytes
            and not (info.file_size and info.compress_size == 0)
        ):
            try:
                with archive.open(info) as stream:
                    payload = stream.read(
                        active_policy.maximum_entry_uncompressed_bytes + 1
                    )
                if len(payload) != info.file_size:
                    raise zipfile.BadZipFile(
                        "entry size differs from central directory"
                    )
                payloads[ordinal] = payload
                payload_hash = bytes_hash(payload)
                if path.endswith(".java"):
                    try:
                        canonical_source_hash = bytes_hash(
                            canonical_source_bytes(payload)
                        )
                    except ValueError:
                        anomalies.append(
                            (
                                "JAVA_SOURCE_ENCODING_MALFORMED",
                                ArchiveInspectionDecisionV2.REJECTED_MALFORMED,
                                (ordinal,),
                                path_hash,
                            )
                        )
            except (
                zipfile.BadZipFile,
                OSError,
                EOFError,
                RuntimeError,
                NotImplementedError,
            ):
                anomalies.append(
                    (
                        "ENTRY_PAYLOAD_UNREADABLE",
                        ArchiveInspectionDecisionV2.REJECTED_MALFORMED,
                        (ordinal,),
                        path_hash,
                    )
                )
        entry_rows.append(
            _entry_identity(
                info=info,
                ordinal=ordinal,
                path=path,
                kind=kind,
                payload_hash=payload_hash,
                canonical_source_hash=canonical_source_hash,
            )
        )

    path_groups, group_anomalies = _path_groups(entry_rows)
    anomalies.extend(group_anomalies)
    anomaly_rows = _anomaly_rows(anomalies)
    decision = _overall_decision(anomaly_rows)

    java_entries: tuple[tuple[str, bytes], ...] = ()
    legal_entries: tuple[tuple[str, bytes], ...] = ()
    licenses: tuple[LicenseTextEvidence, ...] = ()
    if decision in _ACCEPTED:
        unique_files = {
            entry.canonical_posix_path: entry
            for entry in entry_rows
            if entry.entry_kind is ArchiveEntryKindV2.REGULAR_FILE
        }
        java_entries = tuple(
            sorted(
                (
                    path,
                    payloads[entry.entry_ordinal],
                )
                for path, entry in unique_files.items()
                if path.endswith(".java") and entry.entry_ordinal in payloads
            )
        )
        legal_entries = tuple(
            sorted(
                (path, payloads[entry.entry_ordinal])
                for path, entry in unique_files.items()
                if _is_root_license(path) and entry.entry_ordinal in payloads
            )
        )
        try:
            licenses = tuple(
                license_text_evidence(path, payload) for path, payload in legal_entries
            )
        except ValueError:
            anomaly_rows = _anomaly_rows(
                [
                    *anomalies,
                    (
                        "LICENSE_DOCUMENT_MALFORMED",
                        ArchiveInspectionDecisionV2.REJECTED_LICENSE_CONFLICT,
                        (),
                        None,
                    ),
                ]
            )
            decision = _overall_decision(anomaly_rows)
            java_entries = ()
            legal_entries = ()
            licenses = ()
        if len({item.normalized_text_sha256 for item in licenses}) > 1:
            anomaly_rows = _anomaly_rows(
                [
                    *anomalies,
                    (
                        "CONFLICTING_LICENSE_DOCUMENTS",
                        ArchiveInspectionDecisionV2.REJECTED_LICENSE_CONFLICT,
                        (),
                        None,
                    ),
                ]
            )
            decision = _overall_decision(anomaly_rows)
            java_entries = ()
            legal_entries = ()
            licenses = ()

    java_manifest = tuple(
        (path, bytes_hash(payload), len(payload)) for path, payload in java_entries
    )
    legal_manifest = tuple(
        (path, bytes_hash(payload), len(payload)) for path, payload in legal_entries
    )
    receipt = _build_receipt(
        policy=active_policy,
        source_hash=source_hash,
        entry_count=len(infos),
        total_uncompressed=total_uncompressed,
        entries=tuple(entry_rows),
        path_groups=path_groups,
        anomalies=anomaly_rows,
        java_manifest_hash=content_hash(java_manifest),
        legal_manifest_hash=content_hash(legal_manifest),
        java_entry_count=len(java_entries),
        legal_document_count=len(legal_entries),
        decision=decision,
    )
    archive.close()
    return ArchiveInspectionResultV2(receipt, java_entries, legal_entries, licenses)


def build_candidate_archive_inspection_binding(
    *,
    candidate_identity: object,
    result: ArchiveInspectionResultV2,
) -> CandidateArchiveInspectionBinding:
    receipt = result.receipt
    body = {
        "schema_version": 2,
        "candidate_identity_hash": content_hash(candidate_identity),
        "source_jar_hash": receipt.source_jar_hash,
        "archive_policy_hash": receipt.archive_policy_hash,
        "inspection_receipt_hash": receipt.receipt_hash,
        "accepted_java_entry_manifest_hash": receipt.accepted_java_entry_manifest_hash,
        "legal_document_manifest_hash": receipt.legal_document_manifest_hash,
        "decision": receipt.decision,
    }
    return CandidateArchiveInspectionBinding(**body, binding_hash=content_hash(body))


def verify_candidate_archive_inspection_binding(
    *,
    binding: CandidateArchiveInspectionBinding,
    candidate_identity: object,
    source_archive: bytes,
    policy: ArchiveInspectionPolicyV2 | None = None,
) -> ArchiveBindingVerificationResultV2:
    active_policy = policy or ArchiveInspectionPolicyV2.frozen_default()
    status = ArchiveBindingVerificationStatusV2.VERIFIED
    observed = None
    binding_body = asdict(binding)
    claimed = binding_body.pop("binding_hash")
    if content_hash(binding_body) != claimed:
        status = ArchiveBindingVerificationStatusV2.BINDING_HASH_MISMATCH
    elif binding.candidate_identity_hash != content_hash(candidate_identity):
        status = ArchiveBindingVerificationStatusV2.RECEIPT_MISMATCH
    elif binding.source_jar_hash != bytes_hash(source_archive):
        status = ArchiveBindingVerificationStatusV2.SOURCE_HASH_MISMATCH
    elif binding.archive_policy_hash != active_policy.policy_hash:
        status = ArchiveBindingVerificationStatusV2.POLICY_HASH_MISMATCH
    else:
        observed_result = inspect_source_archive_v2(
            source_archive, policy=active_policy
        )
        observed = observed_result.receipt.receipt_hash
        if (
            observed != binding.inspection_receipt_hash
            or observed_result.receipt.decision is not binding.decision
            or observed_result.receipt.accepted_java_entry_manifest_hash
            != binding.accepted_java_entry_manifest_hash
            or observed_result.receipt.legal_document_manifest_hash
            != binding.legal_document_manifest_hash
        ):
            status = ArchiveBindingVerificationStatusV2.RECEIPT_MISMATCH
    body = {
        "schema_version": 2,
        "status": status,
        "binding_hash": binding.binding_hash,
        "independently_observed_receipt_hash": observed,
    }
    return ArchiveBindingVerificationResultV2(**body, result_hash=content_hash(body))


def archive_decision_is_accepted(decision: ArchiveInspectionDecisionV2) -> bool:
    return decision in _ACCEPTED


def public_archive_forensics(result: ArchiveInspectionResultV2) -> dict[str, object]:
    """Return path-hash-only archive facts suitable for repository evidence."""

    receipt = result.receipt
    groups = tuple(
        {
            "canonical_path_hash": group.canonical_path_hash,
            "entry_ordinals": group.entry_ordinals,
            "entry_kinds": tuple(item.value for item in group.entry_kinds),
            "classification": group.duplicate_class.value,
            "payload_equality": group.payload_equality,
            "metadata_equality": group.metadata_equality,
            "directory_file_conflict": group.directory_file_conflict,
            "downstream_payload_selection_ambiguous": (
                group.downstream_payload_selection_ambiguous
            ),
            "entries": tuple(
                {
                    "entry_ordinal": receipt.entries[ordinal].entry_ordinal,
                    "entry_kind": receipt.entries[ordinal].entry_kind.value,
                    "raw_filename_hash": receipt.entries[
                        ordinal
                    ].original_filename_hash,
                    "nfc_filename_hash": receipt.entries[ordinal].nfc_path_hash,
                    "casefold_filename_hash": receipt.entries[
                        ordinal
                    ].casefold_path_hash,
                    "canonical_path_hash": receipt.entries[ordinal].canonical_path_hash,
                    "uncompressed_size": receipt.entries[ordinal].uncompressed_size,
                    "compressed_size": receipt.entries[ordinal].compressed_size,
                    "compression_method": receipt.entries[ordinal].compression_method,
                    "external_attributes": receipt.entries[ordinal].external_attributes,
                    "crc": receipt.entries[ordinal].crc,
                    "payload_hash": receipt.entries[ordinal].payload_hash,
                    "canonical_source_hash": receipt.entries[
                        ordinal
                    ].canonical_source_hash,
                    "entry_metadata_hash": receipt.entries[ordinal].entry_metadata_hash,
                }
                for ordinal in group.entry_ordinals
            ),
            "group_hash": group.group_hash,
        }
        for group in receipt.path_groups
    )
    body = {
        "schema_version": 2,
        "archive_policy_hash": receipt.archive_policy_hash,
        "source_jar_hash": receipt.source_jar_hash,
        "inspection_receipt_hash": receipt.receipt_hash,
        "decision": receipt.decision.value,
        "entry_count": receipt.entry_count,
        "duplicate_group_count": len(groups),
        "unclassified_duplicate_group_count": sum(
            group["classification"]
            == ArchiveDuplicateClassV2.UNRESOLVED_DUPLICATE_KIND.value
            for group in groups
        ),
        "groups": groups,
    }
    return {**body, "forensics_hash": content_hash(body)}


def _verify_policy(policy: ArchiveInspectionPolicyV2) -> None:
    body = asdict(policy)
    claimed = body.pop("policy_hash")
    if (
        policy.schema_version != 2
        or not policy.policy_version
        or min(
            policy.maximum_entry_count,
            policy.maximum_total_uncompressed_bytes,
            policy.maximum_entry_uncompressed_bytes,
            policy.maximum_compression_ratio,
        )
        <= 0
        or not policy.reject_duplicate_regular_files
        or not policy.allow_compatible_redundant_directories
        or not policy.reject_nfc_collisions
        or not policy.reject_casefold_collisions
        or content_hash(body) != claimed
    ):
        raise ValueError("M336K archive policy is invalid")


def _canonical_path(raw: str, directory: bool) -> tuple[str, str | None]:
    if "\x00" in raw:
        return _path_placeholder(raw), "NUL_IN_PATH"
    if raw.startswith(("//", "\\\\")):
        return _path_placeholder(raw), "UNC_PATH"
    if raw.startswith("/"):
        return _path_placeholder(raw), "ABSOLUTE_POSIX_PATH"
    if _DRIVE.match(raw):
        return _path_placeholder(raw), "WINDOWS_DRIVE_PATH"
    normalized = raw.replace("\\", "/")
    parts = normalized.split("/")
    if ".." in parts:
        return _path_placeholder(raw), "PATH_TRAVERSAL"
    if not normalized or normalized == "/":
        return _path_placeholder(raw), "EMPTY_PATH"
    expected = normalized[:-1] if directory and normalized.endswith("/") else normalized
    pure = PurePosixPath(expected)
    canonical = pure.as_posix()
    if canonical in {"", "."}:
        return _path_placeholder(raw), "EMPTY_PATH"
    if "\\" in raw or canonical != expected:
        return canonical, "NON_CANONICAL_SEPARATOR_OR_SEGMENT"
    return canonical, None


def _path_placeholder(raw: str) -> str:
    return f"__invalid__/{bytes_hash(raw.encode('utf-8', errors='surrogatepass'))}"


def _entry_kind(info: zipfile.ZipInfo) -> ArchiveEntryKindV2:
    mode = (info.external_attr >> 16) & 0xFFFF
    if mode and stat.S_ISLNK(mode):
        return ArchiveEntryKindV2.SYMLINK
    if info.is_dir() or info.orig_filename.endswith(("/", "\\")):
        return ArchiveEntryKindV2.DIRECTORY
    if not mode or stat.S_ISREG(mode):
        return ArchiveEntryKindV2.REGULAR_FILE
    return ArchiveEntryKindV2.OTHER


def _entry_identity(
    *,
    info: zipfile.ZipInfo,
    ordinal: int,
    path: str,
    kind: ArchiveEntryKindV2,
    payload_hash: str | None,
    canonical_source_hash: str | None,
) -> ArchiveEntryIdentityV2:
    nfc = unicodedata.normalize("NFC", path)
    body = {
        "entry_ordinal": ordinal,
        "canonical_posix_path": path,
        "original_filename_hash": bytes_hash(
            info.orig_filename.encode("utf-8", errors="surrogatepass")
        ),
        "canonical_path_hash": bytes_hash(path.encode("utf-8", errors="surrogatepass")),
        "nfc_path_hash": bytes_hash(nfc.encode("utf-8", errors="surrogatepass")),
        "casefold_path_hash": bytes_hash(
            nfc.casefold().encode("utf-8", errors="surrogatepass")
        ),
        "entry_kind": kind,
        "flags": info.flag_bits,
        "compression_method": info.compress_type,
        "crc": info.CRC,
        "compressed_size": info.compress_size,
        "uncompressed_size": info.file_size,
        "external_attributes": info.external_attr,
        "payload_hash": payload_hash,
        "canonical_source_hash": canonical_source_hash,
    }
    return ArchiveEntryIdentityV2(**body, entry_metadata_hash=content_hash(body))


def _path_groups(entries: list[ArchiveEntryIdentityV2]):
    grouped: dict[str, list[ArchiveEntryIdentityV2]] = {}
    for entry in entries:
        grouped.setdefault(entry.canonical_posix_path, []).append(entry)
    results: list[ArchivePathGroupV2] = []
    anomalies = []
    used_sets: set[tuple[int, ...]] = set()
    for members in grouped.values():
        if len(members) < 2:
            continue
        group, decision = _classify_path_group(members)
        results.append(group)
        used_sets.add(group.entry_ordinals)
        anomalies.append(
            (
                group.duplicate_class.value,
                decision,
                group.entry_ordinals,
                group.canonical_path_hash,
            )
        )
    aliases = (
        (
            ArchiveDuplicateClassV2.NFC_PATH_COLLISION,
            ArchiveInspectionDecisionV2.REJECTED_NORMALIZATION_COLLISION,
            lambda item: item.nfc_path_hash,
        ),
        (
            ArchiveDuplicateClassV2.CASEFOLD_PATH_COLLISION,
            ArchiveInspectionDecisionV2.REJECTED_NORMALIZATION_COLLISION,
            lambda item: item.casefold_path_hash,
        ),
    )
    for classification, decision, key in aliases:
        alias_groups: dict[str, list[ArchiveEntryIdentityV2]] = {}
        for entry in entries:
            alias_groups.setdefault(key(entry), []).append(entry)
        for members in alias_groups.values():
            ordinals = tuple(item.entry_ordinal for item in members)
            distinct = {item.canonical_posix_path for item in members}
            if len(members) < 2 or len(distinct) < 2 or ordinals in used_sets:
                continue
            group = _group(members, classification)
            results.append(group)
            used_sets.add(ordinals)
            anomalies.append(
                (
                    classification.value,
                    decision,
                    ordinals,
                    group.canonical_path_hash,
                )
            )
    return (
        tuple(sorted(results, key=lambda item: (item.entry_ordinals, item.group_hash))),
        anomalies,
    )


def _classify_path_group(members: list[ArchiveEntryIdentityV2]):
    kinds = {item.entry_kind for item in members}
    payloads = {item.payload_hash for item in members if item.payload_hash is not None}
    unreadable_regular = any(
        item.entry_kind is ArchiveEntryKindV2.REGULAR_FILE and item.payload_hash is None
        for item in members
    )
    if unreadable_regular:
        classification = ArchiveDuplicateClassV2.MALFORMED_DUPLICATE_ENTRY
        decision = ArchiveInspectionDecisionV2.REJECTED_MALFORMED
    elif kinds == {ArchiveEntryKindV2.DIRECTORY, ArchiveEntryKindV2.REGULAR_FILE}:
        classification = ArchiveDuplicateClassV2.FILE_DIRECTORY_PATH_CONFLICT
        decision = ArchiveInspectionDecisionV2.REJECTED_FILE_DIRECTORY_CONFLICT
    elif kinds == {ArchiveEntryKindV2.DIRECTORY}:
        compatible = (
            len(
                {
                    (item.flags, item.compression_method, item.external_attributes)
                    for item in members
                }
            )
            == 1
        )
        classification = (
            ArchiveDuplicateClassV2.REDUNDANT_IDENTICAL_DIRECTORY_ENTRY
            if compatible
            else ArchiveDuplicateClassV2.DUPLICATE_DIRECTORY_METADATA_CONFLICT
        )
        decision = (
            ArchiveInspectionDecisionV2.ACCEPTED_WITH_REDUNDANT_DIRECTORY_ENTRIES
            if compatible
            else ArchiveInspectionDecisionV2.REVIEW_REQUIRED_UNKNOWN_ARCHIVE_CONSTRUCT
        )
    elif kinds == {ArchiveEntryKindV2.REGULAR_FILE}:
        identical = len(payloads) == 1
        classification = (
            ArchiveDuplicateClassV2.DUPLICATE_IDENTICAL_REGULAR_FILE
            if identical
            else ArchiveDuplicateClassV2.DUPLICATE_CONFLICTING_REGULAR_FILE
        )
        decision = (
            ArchiveInspectionDecisionV2.REJECTED_AMBIGUOUS_DUPLICATE_FILE
            if identical
            else ArchiveInspectionDecisionV2.REJECTED_CONFLICTING_DUPLICATE_FILE
        )
    else:
        classification = ArchiveDuplicateClassV2.UNRESOLVED_DUPLICATE_KIND
        decision = ArchiveInspectionDecisionV2.REVIEW_REQUIRED_UNKNOWN_ARCHIVE_CONSTRUCT
    return _group(members, classification), decision


def _group(
    members: list[ArchiveEntryIdentityV2], classification: ArchiveDuplicateClassV2
) -> ArchivePathGroupV2:
    kinds = tuple(item.entry_kind for item in members)
    regular_payloads = tuple(
        item.payload_hash
        for item in members
        if item.entry_kind is ArchiveEntryKindV2.REGULAR_FILE
    )
    payload_equality = len(set(regular_payloads)) == 1 if regular_payloads else None
    metadata_equality = (
        len(
            {
                (
                    item.entry_kind,
                    item.flags,
                    item.compression_method,
                    item.external_attributes,
                )
                for item in members
            }
        )
        == 1
    )
    body = {
        "canonical_path_hash": members[0].canonical_path_hash,
        "entry_ordinals": tuple(item.entry_ordinal for item in members),
        "entry_kinds": kinds,
        "duplicate_class": classification,
        "payload_equality": payload_equality,
        "metadata_equality": metadata_equality,
        "directory_file_conflict": set(kinds)
        == {ArchiveEntryKindV2.DIRECTORY, ArchiveEntryKindV2.REGULAR_FILE},
        "downstream_payload_selection_ambiguous": (
            set(kinds) == {ArchiveEntryKindV2.REGULAR_FILE}
            and len(set(regular_payloads)) > 1
        ),
    }
    return ArchivePathGroupV2(**body, group_hash=content_hash(body))


def _anomaly_rows(values):
    rows = []
    seen = set()
    for reason, decision, ordinals, path_hash in values:
        key = (reason, decision, tuple(ordinals), path_hash)
        if key in seen:
            continue
        seen.add(key)
        body = {
            "reason_code": reason,
            "decision": decision,
            "entry_ordinals": tuple(ordinals),
            "canonical_path_hash": path_hash,
        }
        rows.append(ArchiveAnomalyV2(**body, anomaly_hash=content_hash(body)))
    return tuple(
        sorted(
            rows,
            key=lambda item: (
                item.entry_ordinals,
                item.reason_code,
                item.canonical_path_hash or "",
            ),
        )
    )


def _overall_decision(
    anomalies: tuple[ArchiveAnomalyV2, ...],
) -> ArchiveInspectionDecisionV2:
    if not anomalies:
        return ArchiveInspectionDecisionV2.ACCEPTED
    return min(
        (item.decision for item in anomalies), key=_DECISION_PRIORITY.__getitem__
    )


def _build_receipt(
    *,
    policy,
    source_hash,
    entry_count,
    total_uncompressed,
    entries,
    path_groups,
    anomalies,
    java_manifest_hash,
    legal_manifest_hash,
    java_entry_count,
    legal_document_count,
    decision,
):
    body = {
        "schema_version": 2,
        "archive_policy_hash": policy.policy_hash,
        "source_jar_hash": source_hash,
        "entry_count": entry_count,
        "total_uncompressed_bytes": total_uncompressed,
        "java_entry_count": java_entry_count,
        "legal_document_count": legal_document_count,
        "entries": entries,
        "path_groups": path_groups,
        "anomalies": anomalies,
        "accepted_java_entry_manifest_hash": java_manifest_hash,
        "legal_document_manifest_hash": legal_manifest_hash,
        "decision": decision,
    }
    return ArchiveInspectionReceiptV2(**body, receipt_hash=content_hash(body))


def _terminal_result(*, policy, source_hash, decision, anomalies):
    anomaly_rows = _anomaly_rows(
        [
            (reason, decision, ordinals, path_hash)
            for reason, ordinals, path_hash in anomalies
        ]
    )
    receipt = _build_receipt(
        policy=policy,
        source_hash=source_hash,
        entry_count=0,
        total_uncompressed=0,
        entries=(),
        path_groups=(),
        anomalies=anomaly_rows,
        java_manifest_hash=content_hash(()),
        legal_manifest_hash=content_hash(()),
        java_entry_count=0,
        legal_document_count=0,
        decision=decision,
    )
    return ArchiveInspectionResultV2(receipt, (), (), ())


def _is_root_license(path: str) -> bool:
    pure = PurePosixPath(path)
    return len(pure.parts) <= 2 and pure.name.casefold() in _LEGAL_NAMES
