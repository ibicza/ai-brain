"""Canonical source identity and portable sealed-vault primitives for M-33.6e."""

from __future__ import annotations

import re
import stat
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash

M336E_SOURCE_ENTRY_SCHEMA_VERSION = 1
M336E_PORTABLE_VAULT_SCHEMA_VERSION = 2
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DRIVE = re.compile(r"[A-Za-z]:")


@dataclass(frozen=True, order=True)
class CanonicalVaultPath:
    """A relative NFC POSIX path with one portable byte ordering."""

    canonical_posix_path: str

    @classmethod
    def parse(cls, value: str | bytes) -> CanonicalVaultPath:
        if isinstance(value, bytes):
            text = value.decode("utf-8", errors="strict")
        elif isinstance(value, str):
            text = value
        else:
            raise TypeError("canonical vault path must be UTF-8 bytes or text")
        if "\x00" in text:
            raise ValueError("canonical vault path contains NUL")
        text = text.replace("\\", "/")
        if text.startswith("/") or _DRIVE.match(text):
            raise ValueError("canonical vault path must be relative")
        raw_parts = text.split("/")
        if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
            raise ValueError("canonical vault path contains an unsafe component")
        parts = tuple(unicodedata.normalize("NFC", part) for part in raw_parts)
        canonical = "/".join(parts)
        if not canonical or canonical.startswith("/") or _DRIVE.match(canonical):
            raise ValueError("canonical vault path must be a relative POSIX path")
        return cls(canonical)

    @property
    def order_key(self) -> bytes:
        return self.canonical_posix_path.encode("utf-8")

    def __str__(self) -> str:
        return self.canonical_posix_path


def canonical_vault_paths(values) -> tuple[CanonicalVaultPath, ...]:
    """Canonicalize a collection and reject logical/casefold collisions."""

    paths = tuple(CanonicalVaultPath.parse(value) for value in values)
    exact: dict[str, int] = {}
    folded: dict[str, str] = {}
    for path in paths:
        value = path.canonical_posix_path
        exact[value] = exact.get(value, 0) + 1
        prior = folded.setdefault(value.casefold(), value)
        if prior != value:
            raise ValueError("canonical vault paths contain a casefold collision")
    if any(count != 1 for count in exact.values()):
        raise ValueError("canonical vault paths contain an NFC/separator collision")
    return tuple(sorted(paths, key=lambda item: item.order_key))


@dataclass(frozen=True)
class SourceEntryId:
    schema_version: int
    candidate_family_id: str
    source_jar_sha256: str
    canonical_archive_relative_path: str
    raw_source_sha256: str
    canonical_source_sha256: str
    identity_hash: str


def build_source_entry_id(
    *,
    candidate_family_id: str,
    source_jar_sha256: str,
    archive_relative_path: str | bytes,
    raw_source_sha256: str,
    canonical_source_sha256: str,
) -> SourceEntryId:
    if not candidate_family_id or candidate_family_id != unicodedata.normalize(
        "NFC", candidate_family_id
    ):
        raise ValueError("candidate family identity is empty or non-NFC")
    if "/" in candidate_family_id or "\\" in candidate_family_id:
        raise ValueError("candidate family identity contains a separator")
    hashes = (source_jar_sha256, raw_source_sha256, canonical_source_sha256)
    if any(_SHA256.fullmatch(value) is None for value in hashes):
        raise ValueError("source entry identity contains an invalid SHA-256")
    archive_path = CanonicalVaultPath.parse(archive_relative_path)
    body = {
        "schema_version": M336E_SOURCE_ENTRY_SCHEMA_VERSION,
        "candidate_family_id": candidate_family_id,
        "source_jar_sha256": source_jar_sha256,
        "canonical_archive_relative_path": archive_path.canonical_posix_path,
        "raw_source_sha256": raw_source_sha256,
        "canonical_source_sha256": canonical_source_sha256,
    }
    return SourceEntryId(**body, identity_hash=content_hash(body))


def verify_source_entry_id(value: SourceEntryId) -> None:
    rebuilt = build_source_entry_id(
        candidate_family_id=value.candidate_family_id,
        source_jar_sha256=value.source_jar_sha256,
        archive_relative_path=value.canonical_archive_relative_path,
        raw_source_sha256=value.raw_source_sha256,
        canonical_source_sha256=value.canonical_source_sha256,
    )
    if rebuilt != value:
        raise ValueError("source entry identity does not match its bound fields")


def source_entry_id_from_dict(value: dict) -> SourceEntryId:
    """Deserialize one SourceEntryId without accepting schema drift."""

    expected = {
        "schema_version",
        "candidate_family_id",
        "source_jar_sha256",
        "canonical_archive_relative_path",
        "raw_source_sha256",
        "canonical_source_sha256",
        "identity_hash",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("SourceEntryId fields differ from the frozen schema")
    result = SourceEntryId(**value)
    verify_source_entry_id(result)
    return result


@dataclass(frozen=True)
class SourceEntryBinding:
    schema_version: int
    source_entry_id: SourceEntryId
    archive_path: str
    scm_path: str
    vault_path: str
    selected_path: str
    production_document_identity: str
    binding_hash: str


def build_source_entry_binding(
    *,
    source_entry_id: SourceEntryId,
    archive_path: str | bytes,
    scm_path: str | bytes,
    vault_path: str | bytes,
    selected_path: str | bytes,
    production_document_identity: str,
) -> SourceEntryBinding:
    verify_source_entry_id(source_entry_id)
    paths = tuple(
        CanonicalVaultPath.parse(value)
        for value in (archive_path, scm_path, vault_path, selected_path)
    )
    if paths[0].canonical_posix_path != source_entry_id.canonical_archive_relative_path:
        raise ValueError("source binding archive path differs from SourceEntryId")
    if (
        not production_document_identity
        or production_document_identity
        != unicodedata.normalize("NFC", production_document_identity)
    ):
        raise ValueError("production document identity is empty or non-NFC")
    body = {
        "schema_version": M336E_SOURCE_ENTRY_SCHEMA_VERSION,
        "source_entry_id": source_entry_id,
        "archive_path": paths[0].canonical_posix_path,
        "scm_path": paths[1].canonical_posix_path,
        "vault_path": paths[2].canonical_posix_path,
        "selected_path": paths[3].canonical_posix_path,
        "production_document_identity": production_document_identity,
    }
    return SourceEntryBinding(**body, binding_hash=content_hash(body))


def verify_source_entry_binding(value: SourceEntryBinding) -> None:
    rebuilt = build_source_entry_binding(
        source_entry_id=value.source_entry_id,
        archive_path=value.archive_path,
        scm_path=value.scm_path,
        vault_path=value.vault_path,
        selected_path=value.selected_path,
        production_document_identity=value.production_document_identity,
    )
    if rebuilt != value:
        raise ValueError("source entry binding does not match its fields")


def source_entry_binding_from_dict(value: dict) -> SourceEntryBinding:
    """Deserialize one path-domain binding with a typed nested identity."""

    expected = {
        "schema_version",
        "source_entry_id",
        "archive_path",
        "scm_path",
        "vault_path",
        "selected_path",
        "production_document_identity",
        "binding_hash",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("SourceEntryBinding fields differ from the frozen schema")
    result = SourceEntryBinding(
        **{
            **value,
            "source_entry_id": source_entry_id_from_dict(value["source_entry_id"]),
        }
    )
    verify_source_entry_binding(result)
    return result


@dataclass(frozen=True)
class SourceEntryBindingManifest:
    schema_version: int
    bindings: tuple[SourceEntryBinding, ...]
    binding_count: int
    manifest_hash: str


def build_source_entry_binding_manifest(
    bindings,
) -> SourceEntryBindingManifest:
    values = tuple(bindings)
    for binding in values:
        verify_source_entry_binding(binding)
    if len({item.binding_hash for item in values}) != len(values):
        raise ValueError("source entry binding manifest contains a duplicate binding")
    if len({item.source_entry_id.identity_hash for item in values}) != len(values):
        raise ValueError("source entry identity is bound more than once")
    # Archive and SCM paths are scoped by their candidate/source artifact.  The
    # same conventional path (for example module-info.java) may legitimately
    # occur in two unrelated archives.  Vault and selected paths are global
    # domains and therefore must be collision-free across the whole manifest.
    for field in ("archive_path", "scm_path"):
        scoped_exact: set[tuple[str, str]] = set()
        scoped_folded: dict[tuple[str, str], str] = {}
        for item in values:
            path = CanonicalVaultPath.parse(getattr(item, field))
            exact_key = (
                item.source_entry_id.candidate_family_id,
                path.canonical_posix_path,
            )
            if exact_key in scoped_exact:
                raise ValueError(f"source binding {field} is mapped more than once")
            scoped_exact.add(exact_key)
            folded_key = (exact_key[0], exact_key[1].casefold())
            prior = scoped_folded.setdefault(folded_key, exact_key[1])
            if prior != path.canonical_posix_path:
                raise ValueError(
                    f"source binding {field} contains a casefold collision"
                )
    for field in ("vault_path", "selected_path"):
        canonical_vault_paths(getattr(item, field) for item in values)
    if len({item.production_document_identity for item in values}) != len(values):
        raise ValueError("several source entries map to one production document")
    folded_documents: dict[str, str] = {}
    for binding in values:
        document = binding.production_document_identity
        prior = folded_documents.setdefault(document.casefold(), document)
        if prior != document:
            raise ValueError(
                "production document identities contain a casefold collision"
            )
    ordered = tuple(
        sorted(
            values, key=lambda item: bytes.fromhex(item.source_entry_id.identity_hash)
        )
    )
    body = {
        "schema_version": M336E_SOURCE_ENTRY_SCHEMA_VERSION,
        "bindings": ordered,
        "binding_count": len(ordered),
    }
    return SourceEntryBindingManifest(**body, manifest_hash=content_hash(body))


def verify_source_entry_binding_manifest(value: SourceEntryBindingManifest) -> None:
    if build_source_entry_binding_manifest(value.bindings) != value:
        raise ValueError("source entry binding manifest is invalid")


def source_entry_binding_manifest_from_dict(value: dict) -> SourceEntryBindingManifest:
    """Deserialize the complete binding manifest with exact recursive fields."""

    expected = {"schema_version", "bindings", "binding_count", "manifest_hash"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("source binding manifest fields differ from the frozen schema")
    if not isinstance(value["bindings"], list | tuple):
        raise TypeError("source binding manifest bindings must be an array")
    result = SourceEntryBindingManifest(
        schema_version=value["schema_version"],
        bindings=tuple(
            source_entry_binding_from_dict(item) for item in value["bindings"]
        ),
        binding_count=value["binding_count"],
        manifest_hash=value["manifest_hash"],
    )
    verify_source_entry_binding_manifest(result)
    return result


@dataclass(frozen=True)
class PortableVaultManifestRow:
    canonical_path: str
    byte_size: int
    sha256: str
    row_hash: str


@dataclass(frozen=True)
class PortableVaultManifest:
    schema_version: int
    rows: tuple[PortableVaultManifestRow, ...]
    file_count: int
    portable_tree_hash: str
    manifest_hash: str


def build_portable_vault_manifest(root: Path) -> PortableVaultManifest:
    resolved_root = root.resolve(strict=True)
    discovered = tuple(resolved_root.rglob("*"))
    _reject_link_or_reparse(discovered)
    physical = tuple(item for item in discovered if item.is_file())
    relative = tuple(item.relative_to(resolved_root).as_posix() for item in physical)
    canonical = canonical_vault_paths(relative)
    by_name = {
        CanonicalVaultPath.parse(
            item.relative_to(resolved_root).as_posix()
        ).canonical_posix_path: item
        for item in physical
    }
    rows = []
    for path in canonical:
        physical_path = by_name[path.canonical_posix_path]
        raw = physical_path.read_bytes()
        row_body = {
            "canonical_path": path.canonical_posix_path,
            "byte_size": len(raw),
            "sha256": bytes_hash(raw),
        }
        rows.append(
            PortableVaultManifestRow(**row_body, row_hash=content_hash(row_body))
        )
    ordered = tuple(rows)
    tree_rows = tuple(
        (row.canonical_path, row.sha256, row.byte_size) for row in ordered
    )
    body = {
        "schema_version": M336E_PORTABLE_VAULT_SCHEMA_VERSION,
        "rows": ordered,
        "file_count": len(ordered),
        "portable_tree_hash": content_hash(tree_rows),
    }
    return PortableVaultManifest(**body, manifest_hash=content_hash(body))


def verify_portable_vault_manifest(root: Path, manifest: PortableVaultManifest) -> None:
    for row in manifest.rows:
        path = CanonicalVaultPath.parse(row.canonical_path)
        body = {
            "canonical_path": path.canonical_posix_path,
            "byte_size": row.byte_size,
            "sha256": row.sha256,
        }
        if (
            row.byte_size < 0
            or _SHA256.fullmatch(row.sha256) is None
            or content_hash(body) != row.row_hash
        ):
            raise ValueError("portable vault manifest row is invalid")
    canonical_vault_paths(row.canonical_path for row in manifest.rows)
    if (
        tuple(sorted(manifest.rows, key=lambda row: row.canonical_path.encode("utf-8")))
        != manifest.rows
    ):
        raise ValueError("portable vault manifest uses non-canonical ordering")
    tree_rows = tuple(
        (row.canonical_path, row.sha256, row.byte_size) for row in manifest.rows
    )
    body = asdict(manifest)
    claimed = body.pop("manifest_hash")
    if (
        manifest.schema_version != M336E_PORTABLE_VAULT_SCHEMA_VERSION
        or manifest.file_count != len(manifest.rows)
        or content_hash(tree_rows) != manifest.portable_tree_hash
        or content_hash(body) != claimed
    ):
        raise ValueError("portable vault manifest invariants failed")
    actual = build_portable_vault_manifest(root)
    if actual != manifest:
        raise ValueError("portable vault physical/canonical manifest differs")


def portable_vault_manifest_from_dict(value: dict) -> PortableVaultManifest:
    """Deserialize a portable manifest and verify all content-derived fields."""

    expected = {
        "schema_version",
        "rows",
        "file_count",
        "portable_tree_hash",
        "manifest_hash",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("portable vault manifest fields differ from the frozen schema")
    row_fields = {"canonical_path", "byte_size", "sha256", "row_hash"}
    if not isinstance(value["rows"], list | tuple):
        raise TypeError("portable vault manifest rows must be an array")
    rows = []
    for item in value["rows"]:
        if not isinstance(item, dict) or set(item) != row_fields:
            raise ValueError("portable vault row fields differ from the frozen schema")
        rows.append(PortableVaultManifestRow(**item))
    result = PortableVaultManifest(
        schema_version=value["schema_version"],
        rows=tuple(rows),
        file_count=value["file_count"],
        portable_tree_hash=value["portable_tree_hash"],
        manifest_hash=value["manifest_hash"],
    )
    # Validate the host-independent structure here.  Physical equality remains
    # the responsibility of verify_portable_vault_manifest(root, result).
    for row in result.rows:
        path = CanonicalVaultPath.parse(row.canonical_path)
        body = {
            "canonical_path": path.canonical_posix_path,
            "byte_size": row.byte_size,
            "sha256": row.sha256,
        }
        if (
            not isinstance(row.byte_size, int)
            or isinstance(row.byte_size, bool)
            or row.byte_size < 0
            or _SHA256.fullmatch(row.sha256) is None
            or content_hash(body) != row.row_hash
        ):
            raise ValueError("portable vault manifest row is invalid")
    canonical_vault_paths(row.canonical_path for row in result.rows)
    tree_rows = tuple(
        (row.canonical_path, row.sha256, row.byte_size) for row in result.rows
    )
    body = asdict(result)
    claimed = body.pop("manifest_hash")
    if (
        result.schema_version != M336E_PORTABLE_VAULT_SCHEMA_VERSION
        or result.file_count != len(result.rows)
        or tuple(
            sorted(result.rows, key=lambda row: row.canonical_path.encode("utf-8"))
        )
        != result.rows
        or content_hash(tree_rows) != result.portable_tree_hash
        or content_hash(body) != claimed
    ):
        raise ValueError("portable vault manifest invariants failed")
    return result


def _reject_link_or_reparse(paths) -> None:
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    for path in paths:
        if path.is_symlink() or bool(
            getattr(path.stat(), "st_file_attributes", 0) & reparse
        ):
            raise ValueError("portable vault contains a symlink/reparse escape")
