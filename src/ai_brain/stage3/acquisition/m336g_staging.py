"""Immutable pre-publication staging for M-33.6g public evidence trees."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336d_leak_scan import scan_fresh_source_leaks
from ai_brain.stage3.acquisition.m336g_publication import (
    JAVA_PUBLIC_PACK_ENTRY_CONTRACTS,
    PUBLIC_ROLES,
    ArtifactConfidentialityRole,
    _is_reparse_point,
    _reject_private_payload,
    _strict_json_bytes,
    verify_java_public_candidate_pack,
)


@dataclass(frozen=True)
class PublicStagingEntry:
    relative_path: str
    artifact_role: str
    byte_length: int
    sha256: str
    contract_hash: str
    row_hash: str


@dataclass(frozen=True)
class PublicStagingManifest:
    schema_version: int
    entries: tuple[PublicStagingEntry, ...]
    file_count: int
    candidate_pack_tree_hash: str
    installed_pack_tree_hash: str
    staging_tree_hash: str
    manifest_hash: str


@dataclass(frozen=True)
class PublicStagingValidationReceipt:
    schema_version: int
    contract_role: str
    staging_manifest_hash: str
    prospective_git_tree_hash: str
    leak_report_hash: str
    public_pack_integrity_receipt_hash: str
    installed_pack_integrity_receipt_hash: str
    post_scan_modified_file_count: int
    unscanned_committed_file_count: int
    scanned_file_omitted_from_manifest_count: int
    status: str
    receipt_hash: str


def _rows(root: Path) -> tuple[tuple[str, int, str], ...]:
    return tuple(
        (
            path.relative_to(root).as_posix(),
            path.stat().st_size,
            bytes_hash(path.read_bytes()),
        )
        for path in sorted(
            (item for item in root.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
        )
    )


def _pack_tree(root: Path) -> str:
    return content_hash(_rows(root))


def validate_public_staging(
    *,
    staging_root: Path,
    artifact_roles: dict[str, ArtifactConfidentialityRole],
    sealed_vault_root: Path,
    candidate_pack_relative_path: str,
    installed_pack_relative_path: str,
    prospective_git_tree_hash: str,
    prospective_git_entries: tuple[tuple[str, int, str], ...] | None = None,
) -> tuple[PublicStagingManifest, PublicStagingValidationReceipt]:
    """Validate one immutable staging snapshot and fail on any post-scan change."""

    root = staging_root.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("public staging root is unsafe")
    if any(item.is_symlink() or _is_reparse_point(item) for item in root.rglob("*")):
        raise ValueError("public staging contains a link or reparse point")
    before = _rows(root)
    paths = {item[0] for item in before}
    if paths != set(artifact_roles):
        raise ValueError("public staging role/file denominator mismatch")
    if any(role not in PUBLIC_ROLES for role in artifact_roles.values()):
        raise ValueError("private or unknown role entered public staging")
    for relative_path, _byte_length, _sha256 in before:
        path = root.joinpath(*relative_path.split("/"))
        if path.suffix.casefold() == ".json":
            _reject_private_payload(_strict_json_bytes(path.read_bytes()))
    candidate = (root / candidate_pack_relative_path).resolve(strict=True)
    installed = (root / installed_pack_relative_path).resolve(strict=True)
    if not candidate.is_relative_to(root) or not installed.is_relative_to(root):
        raise ValueError("staged candidate/install root escapes staging")
    candidate_receipt = verify_java_public_candidate_pack(candidate)
    installed_receipt = verify_java_public_candidate_pack(installed)
    candidate_rows = _rows(candidate)
    installed_rows = _rows(installed)
    if candidate_rows != installed_rows:
        raise ValueError("installed pack differs from exact staged candidate pack")
    leak = scan_fresh_source_leaks(sealed_vault_root, root)
    if leak["status"] != "PASS":
        raise ValueError("public staging leak scan failed")
    pack_contracts = {
        item.entry_name: item.contract_hash for item in JAVA_PUBLIC_PACK_ENTRY_CONTRACTS
    }
    entries = []
    for relative_path, byte_length, sha256 in before:
        role = artifact_roles[relative_path]
        name = relative_path.rsplit("/", 1)[-1]
        contract_hash = pack_contracts.get(
            name, content_hash(("m336g.public-staging.v1", relative_path, role.value))
        )
        body = {
            "relative_path": relative_path,
            "artifact_role": role.value,
            "byte_length": byte_length,
            "sha256": sha256,
            "contract_hash": contract_hash,
        }
        entries.append(PublicStagingEntry(**body, row_hash=content_hash(body)))
    manifest_body = {
        "schema_version": 1,
        "entries": tuple(entries),
        "file_count": len(entries),
        "candidate_pack_tree_hash": _pack_tree(candidate),
        "installed_pack_tree_hash": _pack_tree(installed),
        "staging_tree_hash": content_hash(before),
    }
    manifest = PublicStagingManifest(
        **manifest_body, manifest_hash=content_hash(manifest_body)
    )
    after = _rows(root)
    modified = len(set(before) ^ set(after))
    prospective = before if prospective_git_entries is None else prospective_git_entries
    prospective_by_path = {item[0]: item for item in prospective}
    before_by_path = {item[0]: item for item in before}
    if len(prospective_by_path) != len(prospective):
        raise ValueError("prospective Git manifest contains duplicate paths")
    unscanned = len(set(prospective_by_path) - set(before_by_path)) + sum(
        prospective_by_path[name] != before_by_path[name]
        for name in set(prospective_by_path) & set(before_by_path)
    )
    omitted = len(set(before_by_path) - set(prospective_by_path))
    if not isinstance(prospective_git_tree_hash, str) or len(
        prospective_git_tree_hash
    ) not in {40, 64}:
        raise ValueError("prospective Git tree hash has an invalid identity")
    body = {
        "schema_version": 1,
        "contract_role": ArtifactConfidentialityRole.PUBLIC_SAFE_RECEIPT.value,
        "staging_manifest_hash": manifest.manifest_hash,
        "prospective_git_tree_hash": prospective_git_tree_hash,
        "leak_report_hash": leak["report_hash"],
        "public_pack_integrity_receipt_hash": candidate_receipt.receipt_hash,
        "installed_pack_integrity_receipt_hash": installed_receipt.receipt_hash,
        "post_scan_modified_file_count": modified,
        "unscanned_committed_file_count": unscanned,
        "scanned_file_omitted_from_manifest_count": omitted,
        "status": "PASS" if not (modified + unscanned + omitted) else "FAIL",
    }
    receipt = PublicStagingValidationReceipt(**body, receipt_hash=content_hash(body))
    if receipt.status != "PASS":
        raise ValueError("public staging changed after its leak scan")
    return manifest, receipt
