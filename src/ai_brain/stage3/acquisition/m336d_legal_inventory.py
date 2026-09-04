"""Complete, bounded legal-document inventory before role classification."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336d_spdx_expression import (
    LicenseApplicabilityScope,
    LicenseScopeKind,
)
from ai_brain.stage3.acquisition.spdx_license import (
    LicenseDocumentRole,
    SPDXLicenseMatcher,
    classify_license_document,
    normalize_spdx_bytes,
)

_LEGAL_NAME = re.compile(
    r"^(?:licen[cs]e(?:\..*)?|copying(?:\..*)?|notice(?:\..*)?|copyright(?:\..*)?|"
    r"third[-_ ]?party(?:\..*)?|dependencies(?:\..*)?)$",
    re.IGNORECASE,
)
_LEGAL_DIRECTORY = frozenset({"licenses", "legal", "vendor"})
_TEXT_SUFFIXES = frozenset({"", ".txt", ".md", ".rst", ".adoc"})
_ANCHORS = (
    "spdx-license-identifier:",
    "apache license",
    "permission is hereby granted",
    "gnu general public license",
    "redistribution and use in source and binary forms",
)


@dataclass(frozen=True)
class LegalDocumentContainer:
    container_id: str
    raw_archive: bytes


@dataclass(frozen=True)
class LegalDocumentInventoryRow:
    container_id: str
    path: str
    raw_sha256: str
    normalized_sha256: str
    byte_size: int
    candidate_role: LicenseDocumentRole
    role_evidence: str
    spdx_match_receipt_hash: str
    spdx_match_status: str
    spdx_license_id: str | None
    applicability_scope: LicenseApplicabilityScope
    selected_as_project_license: bool
    reason: str
    receipt_hash: str


@dataclass(frozen=True)
class LegalDocumentInventory:
    rows: tuple[LegalDocumentInventoryRow, ...]
    discovered_document_count: int
    classified_document_count: int
    unknown_role_count: int
    unclassified_document_count: int
    inventory_hash: str


def inventory_legal_documents(
    containers: tuple[LegalDocumentContainer, ...],
    *,
    matcher: SPDXLicenseMatcher | None = None,
) -> LegalDocumentInventory:
    matcher = matcher or SPDXLicenseMatcher()
    rows = []
    seen = set()
    for container in sorted(containers, key=lambda item: item.container_id):
        if not container.container_id or container.container_id in seen:
            raise ValueError(
                "legal-document container IDs must be non-empty and unique"
            )
        seen.add(container.container_id)
        with zipfile.ZipFile(io.BytesIO(container.raw_archive)) as archive:
            archive_paths = set()
            for info in sorted(archive.infolist(), key=lambda item: item.filename):
                if info.is_dir():
                    continue
                path = _canonical_archive_path(info.filename)
                collision_key = path.casefold()
                if collision_key in archive_paths:
                    raise ValueError(
                        "legal-document archive has a duplicate/casefold path"
                    )
                archive_paths.add(collision_key)
                raw = archive.read(info)
                reason = _discovery_reason(path, raw)
                if reason is None:
                    continue
                role = classify_license_document(path)
                scope = _scope_for(path, role)
                match = matcher.match(
                    raw, source_document=f"{container.container_id}/{path}"
                )
                selected = role in {
                    LicenseDocumentRole.PROJECT_LICENSE,
                    LicenseDocumentRole.MODULE_LICENSE,
                }
                body = {
                    "container_id": container.container_id,
                    "path": path,
                    "raw_sha256": bytes_hash(raw),
                    "normalized_sha256": bytes_hash(normalize_spdx_bytes(raw)),
                    "byte_size": len(raw),
                    "candidate_role": role,
                    "role_evidence": reason,
                    "spdx_match_receipt_hash": match.receipt_hash,
                    "spdx_match_status": match.match_status.value,
                    "spdx_license_id": match.template_license_id,
                    "applicability_scope": scope,
                    "selected_as_project_license": selected,
                    "reason": (
                        "ROLE_AND_SCOPE_CLASSIFIED"
                        if role is not LicenseDocumentRole.UNKNOWN_LICENSE_DOCUMENT
                        else "UNKNOWN_LICENSE_DOCUMENT_REVIEW_REQUIRED"
                    ),
                }
                rows.append(
                    LegalDocumentInventoryRow(**body, receipt_hash=content_hash(body))
                )
    ordered = tuple(sorted(rows, key=lambda item: (item.container_id, item.path)))
    unknown = sum(
        item.candidate_role is LicenseDocumentRole.UNKNOWN_LICENSE_DOCUMENT
        for item in ordered
    )
    body = {
        "rows": ordered,
        "discovered_document_count": len(ordered),
        "classified_document_count": len(ordered),
        "unknown_role_count": unknown,
        "unclassified_document_count": 0,
    }
    return LegalDocumentInventory(**body, inventory_hash=content_hash(body))


def _discovery_reason(path: str, raw: bytes) -> str | None:
    pure = PurePosixPath(path)
    name = pure.name
    if _LEGAL_NAME.fullmatch(name):
        return "LEGAL_FILENAME_PATTERN"
    if any(part.casefold() in _LEGAL_DIRECTORY for part in pure.parts[:-1]):
        return "LEGAL_DIRECTORY_PATTERN"
    if (
        len(pure.parts) <= 4
        and pure.suffix.casefold() in _TEXT_SUFFIXES
        and len(raw) <= 131072
    ):
        text = raw.decode("utf-8", errors="ignore").casefold()
        if any(anchor in text for anchor in _ANCHORS):
            return "BOUNDED_STRONG_LICENSE_CONTENT_ANCHOR"
    return None


def _scope_for(path: str, role: LicenseDocumentRole) -> LicenseApplicabilityScope:
    pure = PurePosixPath(path)
    if role is LicenseDocumentRole.MODULE_LICENSE:
        return LicenseApplicabilityScope.build(
            LicenseScopeKind.MODULE_PATH, PurePosixPath(*pure.parts[:-1]).as_posix()
        )
    return LicenseApplicabilityScope.build(LicenseScopeKind.PROJECT_ROOT)


def _canonical_archive_path(value: str) -> str:
    if "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise ValueError("legal-document archive path is not relative POSIX text")
    path = PurePosixPath(value)
    if ".." in path.parts or path.as_posix() != value:
        raise ValueError("legal-document archive path is not canonical")
    return value
