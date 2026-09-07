"""Native M336F selected-source materialization for the M-33.6h route."""

from __future__ import annotations

import stat
from dataclasses import asdict, dataclass
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, content_hash
from ai_brain.stage3.acquisition.m336e_identity import (
    CanonicalVaultPath,
    SourceEntryBindingManifest,
    verify_source_entry_binding_manifest,
)
from ai_brain.stage3.acquisition.m336f_compilation_closure import (
    JavaCompilationClosureFeasibilityProof,
    JavaCompilationClosureManifest,
    verify_java_compilation_closure_feasibility_proof,
    verify_java_compilation_closure_manifest,
)
from ai_brain.stage3.acquisition.m336f_selection import (
    M336FSelectedSourceManifest,
    M336FSelectorReceipt,
    verify_m336f_selection,
)
from ai_brain.stage3.acquisition.maven_provenance import canonical_source_bytes


@dataclass(frozen=True)
class M336HMaterializedSourceSnapshotReceipt:
    schema_version: int
    contract_role: str
    selected_manifest_hash: str
    selector_receipt_hash: str
    binding_manifest_hash: str
    closure_manifest_hash: str
    feasibility_proof_hash: str
    file_count: int
    semantic_file_count: int
    closure_support_file_count: int
    verified_source_entry_id_count: int
    verified_raw_hash_count: int
    verified_canonical_hash_count: int
    verified_production_document_identity_count: int
    snapshot_tree_hash: str
    status: str
    receipt_hash: str


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _document_identity(family: str, selected_path: str, raw_hash: str) -> str:
    body = {
        "schema_version": 2,
        "bundle_id": "m336-final-java",
        "relative_path": selected_path,
        "bytes_hash": raw_hash,
    }
    return f"m336-final-java.document.{content_hash(body)[:32]}"


def _ensure_external_destination(
    destination: Path,
    *,
    git_worktrees: tuple[Path, ...],
    public_roots: tuple[Path, ...],
) -> Path:
    target = destination.resolve(strict=False)
    if target.exists():
        raise FileExistsError("M336H selected snapshot destination already exists")
    forbidden = tuple(
        item.resolve(strict=item.exists()) for item in (*git_worktrees, *public_roots)
    )
    if any(target == root or target.is_relative_to(root) for root in forbidden):
        raise ValueError("M336H selected snapshot targets a worktree or public root")
    parent = target.parent.resolve(strict=True)
    if parent.is_symlink() or _is_reparse_point(parent):
        raise ValueError("M336H selected snapshot parent is a link or reparse point")
    return target


def materialize_m336f_selected_source_snapshot(
    *,
    sealed_vault_root: Path,
    bindings: SourceEntryBindingManifest,
    selected_manifest: M336FSelectedSourceManifest,
    selector_receipt: M336FSelectorReceipt,
    closure_manifest: JavaCompilationClosureManifest,
    closure_proof: JavaCompilationClosureFeasibilityProof,
    destination: Path,
    git_worktrees: tuple[Path, ...] = (),
    public_roots: tuple[Path, ...] = (),
) -> M336HMaterializedSourceSnapshotReceipt:
    """Verify the complete M336F witness before atomically creating its snapshot."""

    vault = sealed_vault_root.resolve(strict=True)
    if not vault.is_dir() or vault.is_symlink() or _is_reparse_point(vault):
        raise ValueError("M336H sealed vault root is unsafe")
    target = _ensure_external_destination(
        destination, git_worktrees=git_worktrees, public_roots=public_roots
    )
    verify_source_entry_binding_manifest(bindings)
    verify_java_compilation_closure_manifest(closure_manifest)
    verify_java_compilation_closure_feasibility_proof(closure_proof)
    verify_m336f_selection(selected_manifest, selector_receipt, closure_proof)
    if (
        selected_manifest.closure_manifest_hash != closure_manifest.manifest_hash
        or selected_manifest.feasibility_proof_hash != closure_proof.proof_hash
        or selected_manifest.binding_manifest_hash != bindings.manifest_hash
        or closure_proof.closure_manifest_hash != closure_manifest.manifest_hash
    ):
        raise ValueError("M336H materialization inputs are not hash-bound")

    selected_rows = tuple(selected_manifest.files)
    selected_paths = tuple(item.selected_path for item in selected_rows)
    selected_ids = tuple(item.source_entry_identity_hash for item in selected_rows)
    if len(selected_paths) != len(set(selected_paths)):
        raise ValueError("M336H selected manifest contains a duplicate path")
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("M336H selected manifest contains a duplicate SourceEntryId")
    canonical_paths = tuple(
        CanonicalVaultPath.parse(item).canonical_posix_path for item in selected_paths
    )
    if canonical_paths != selected_paths:
        raise ValueError("M336H selected manifest path is not canonical")
    witness = set(closure_proof.witness_source_units)
    if set(selected_paths) != witness:
        raise ValueError("M336H selected path set differs from closure witness")
    closure_by_path = {item.source_unit_id: item for item in closure_manifest.files}
    if not witness <= set(closure_by_path):
        raise ValueError("M336H closure witness contains a missing closure file")
    binding_by_path = {item.selected_path: item for item in bindings.bindings}
    if not witness <= set(binding_by_path):
        raise ValueError("M336H closure witness contains an unbound source file")

    payloads: list[tuple[str, bytes, str]] = []
    for row in selected_rows:
        binding = binding_by_path[row.selected_path]
        identity = binding.source_entry_id
        closure = closure_by_path[row.selected_path]
        expected_role = (
            "SELECTED_SEMANTIC_FILE"
            if row.selected_path
            in {
                item.source_unit_id
                for item in closure_manifest.files
                if item.at_least_one_declaration_can_be_trusted
            }
            and row.selection_role == "SELECTED_SEMANTIC_FILE"
            else row.selection_role
        )
        if (
            row.source_entry_identity_hash != identity.identity_hash
            or row.candidate_root != identity.candidate_family_id
            or row.candidate_root != closure.candidate_root
            or row.canonical_path != identity.canonical_archive_relative_path
            or row.selected_path != binding.selected_path
            or row.selection_role
            not in {"SELECTED_SEMANTIC_FILE", "SELECTED_CLOSURE_SUPPORT_FILE"}
            or expected_role != row.selection_role
        ):
            raise ValueError(
                "M336H selected row differs from its bound source identity"
            )
        source = vault.joinpath(*binding.vault_path.split("/"))
        resolved = source.resolve(strict=True)
        if (
            not resolved.is_relative_to(vault)
            or source.is_symlink()
            or _is_reparse_point(source)
            or not resolved.is_file()
        ):
            raise ValueError("M336H selected source escapes the sealed vault")
        raw = resolved.read_bytes()
        canonical = canonical_source_bytes(raw)
        raw_hash = bytes_hash(raw)
        if (
            raw_hash != identity.raw_source_sha256
            or bytes_hash(canonical) != identity.canonical_source_sha256
            or _document_identity(row.candidate_root, row.selected_path, raw_hash)
            != binding.production_document_identity
        ):
            raise ValueError("M336H selected source bytes or document identity changed")
        payloads.append((row.selected_path, raw, identity.identity_hash))

    target.mkdir(parents=False)
    try:
        for relative, raw, _identity in payloads:
            output = target.joinpath(*relative.split("/"))
            output.parent.mkdir(parents=True, exist_ok=True)
            resolved_parent = output.parent.resolve(strict=True)
            if not resolved_parent.is_relative_to(target.resolve(strict=True)):
                raise ValueError("M336H selected snapshot destination escapes")
            output.write_bytes(raw)
        observed = tuple(
            sorted(
                (
                    path.relative_to(target).as_posix(),
                    bytes_hash(path.read_bytes()),
                )
                for path in target.rglob("*.java")
                if path.is_file()
            )
        )
        expected = tuple(sorted((path, bytes_hash(raw)) for path, raw, _id in payloads))
        if observed != expected or len(observed) != selected_manifest.file_count:
            raise ValueError("M336H selected snapshot denominator changed")
    except BaseException:
        for path in sorted(target.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        target.rmdir()
        raise
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_RECEIPT",
        "selected_manifest_hash": selected_manifest.manifest_hash,
        "selector_receipt_hash": selector_receipt.receipt_hash,
        "binding_manifest_hash": bindings.manifest_hash,
        "closure_manifest_hash": closure_manifest.manifest_hash,
        "feasibility_proof_hash": closure_proof.proof_hash,
        "file_count": len(payloads),
        "semantic_file_count": selected_manifest.semantic_file_count,
        "closure_support_file_count": selected_manifest.closure_support_file_count,
        "verified_source_entry_id_count": len(payloads),
        "verified_raw_hash_count": len(payloads),
        "verified_canonical_hash_count": len(payloads),
        "verified_production_document_identity_count": len(payloads),
        "snapshot_tree_hash": content_hash(observed),
        "status": "PASS",
    }
    return M336HMaterializedSourceSnapshotReceipt(
        **body, receipt_hash=content_hash(body)
    )


def materialization_receipt_from_dict(
    value: dict,
) -> M336HMaterializedSourceSnapshotReceipt:
    if set(value) != set(M336HMaterializedSourceSnapshotReceipt.__dataclass_fields__):
        raise ValueError("M336H materialization receipt schema changed")
    receipt = M336HMaterializedSourceSnapshotReceipt(**value)
    body = asdict(receipt)
    claimed = body.pop("receipt_hash")
    if content_hash(body) != claimed or receipt.status != "PASS":
        raise ValueError("M336H materialization receipt is invalid")
    return receipt
