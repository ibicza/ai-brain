"""Verify and materialize the Windows selector result on Karina without selecting."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_disclosed_qualification import (
    load_strict_json,
    materialize_selected_source_snapshot,
)
from ai_brain.stage3.acquisition.m336e_identity import (
    portable_vault_manifest_from_dict,
    source_entry_binding_manifest_from_dict,
    verify_portable_vault_manifest,
)
from ai_brain.stage3.acquisition.m336e_selectability import (
    selectable_source_census_from_dict,
    selected_source_manifest_from_dict,
    selector_feasibility_proof_from_dict,
    selector_receipt_from_dict,
    verify_selector_result_without_invocation,
)


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--portable-vault-manifest", type=Path, required=True)
    parser.add_argument("--binding-manifest", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--feasibility-proof", type=Path, required=True)
    parser.add_argument("--selected-manifest", type=Path, required=True)
    parser.add_argument("--selector-receipt", type=Path, required=True)
    parser.add_argument("--selected-source-output", type=Path, required=True)
    parser.add_argument("--verification-output", type=Path, required=True)
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    head = subprocess.run(
        ("git", "rev-parse", "HEAD^{commit}"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ("git", "status", "--porcelain=v1"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if head != args.expected_head or len(head) != 40 or status:
        raise ValueError("verify-only selection requires a clean exact worktree")
    worktree_output = subprocess.run(
        ("git", "worktree", "list", "--porcelain"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    worktrees = tuple(
        Path(line.removeprefix("worktree ")).resolve(strict=True)
        for line in worktree_output.splitlines()
        if line.startswith("worktree ")
    )
    vault = args.vault.resolve(strict=True)
    selected_output = args.selected_source_output.resolve()
    verification_output = args.verification_output.resolve()
    if any(
        root == selected_output or root in selected_output.parents for root in worktrees
    ):
        raise ValueError(
            "selected raw source output must remain outside the repository"
        )
    if repository == verification_output or repository in verification_output.parents:
        raise ValueError("verify-only receipt must be written outside the repository")
    if selected_output.exists() or verification_output.exists():
        raise FileExistsError("verify-only outputs must be new")

    portable = portable_vault_manifest_from_dict(
        load_strict_json(args.portable_vault_manifest.resolve(strict=True))
    )
    bindings = source_entry_binding_manifest_from_dict(
        load_strict_json(args.binding_manifest.resolve(strict=True))
    )
    census = selectable_source_census_from_dict(
        load_strict_json(args.census.resolve(strict=True))
    )
    proof = selector_feasibility_proof_from_dict(
        load_strict_json(args.feasibility_proof.resolve(strict=True)), census
    )
    selected = selected_source_manifest_from_dict(
        load_strict_json(args.selected_manifest.resolve(strict=True))
    )
    selector = selector_receipt_from_dict(
        load_strict_json(args.selector_receipt.resolve(strict=True))
    )

    verify_portable_vault_manifest(vault, portable)
    verify_selector_result_without_invocation(
        census, proof, bindings, selected, selector
    )
    materialize_selected_source_snapshot(
        vault_root=vault,
        binding_manifest=bindings,
        selected_manifest=selected,
        destination=selected_output,
    )
    body = {
        "schema_version": 1,
        "status": "PASS",
        "verification_mode": "VERIFY_ONLY_NO_SELECTOR_INVOCATION",
        "portable_vault_manifest_hash": portable.manifest_hash,
        "portable_vault_tree_hash": portable.portable_tree_hash,
        "binding_manifest_hash": bindings.manifest_hash,
        "selectability_census_hash": census.census_hash,
        "feasibility_proof_hash": proof.proof_hash,
        "selected_manifest_hash": selected.manifest_hash,
        "selector_receipt_hash": selector.receipt_hash,
        "verified_selected_file_count": selected.file_count,
        "verified_selected_root_count": selected.root_count,
        "selector_reservation_count_on_verifier": 0,
        "selector_invocation_count_on_verifier": 0,
        "selector_rerun_count_on_verifier": 0,
    }
    verification_output.mkdir(parents=True)
    _write(
        verification_output / "selector_verify_only_receipt.json",
        {**body, "receipt_hash": content_hash(body)},
    )


if __name__ == "__main__":
    main()
