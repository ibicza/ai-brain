"""Run exact-F20 oracle-free production from the verified M-33.6e selection."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336e_disclosed_qualification import (
    materialize_selected_source_snapshot,
)
from ai_brain.stage3.acquisition.m336e_identity import (
    source_entry_binding_manifest_from_dict,
)
from ai_brain.stage3.acquisition.m336e_selectability import (
    selectable_source_census_from_dict,
    selected_source_manifest_from_dict,
    selector_feasibility_proof_from_dict,
    selector_receipt_from_dict,
    verify_selector_result_without_invocation,
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _require_clean_exact_f20(repository: Path, f20_sha: str) -> None:
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
    if head != f20_sha or len(head) != 40 or status:
        raise ValueError("production requires a clean exact-F20 worktree")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--feasibility-proof", type=Path, required=True)
    parser.add_argument("--selected-manifest", type=Path, required=True)
    parser.add_argument("--selector-receipt", type=Path, required=True)
    parser.add_argument("--f20-sha", required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    _require_clean_exact_f20(repository, args.f20_sha)
    if args.output.exists():
        raise FileExistsError("fresh production output already exists")
    bindings = source_entry_binding_manifest_from_dict(
        _load(args.bindings.resolve(strict=True))
    )
    census = selectable_source_census_from_dict(_load(args.census.resolve(strict=True)))
    proof = selector_feasibility_proof_from_dict(
        _load(args.feasibility_proof.resolve(strict=True)), census
    )
    selected = selected_source_manifest_from_dict(
        _load(args.selected_manifest.resolve(strict=True))
    )
    selector = selector_receipt_from_dict(
        _load(args.selector_receipt.resolve(strict=True))
    )
    if selector.f20_sha != args.f20_sha:
        raise ValueError("production selector is not bound to exact F20")
    verify_selector_result_without_invocation(
        census, proof, bindings, selected, selector
    )
    with tempfile.TemporaryDirectory(prefix="m336e-selected-") as temporary:
        source_root = Path(temporary) / "selected"
        materialize_selected_source_snapshot(
            vault_root=args.vault.resolve(strict=True),
            binding_manifest=bindings,
            selected_manifest=selected,
            destination=source_root,
        )
        subprocess.run(
            (
                sys.executable,
                str(repository / "scripts/m336_run_oracle_free_production.py"),
                "--source-root",
                str(source_root),
                "--output",
                str(args.output),
                "--platform",
                args.platform,
            ),
            cwd=repository,
            check=True,
        )
    summary = _load(args.output / "production_summary.json")
    counts = _load(args.output / "production_counts.json")
    process = _load(args.output / "production_process_audit.json")
    files = _load(args.output / "production_file_access_audit.json")
    state = _load(args.output / "production_state_audit.json")
    nonzero_process = sum(
        value
        for name, value in process.items()
        if name.endswith(("count", "attempts")) and isinstance(value, int)
    )
    nonzero_state = sum(
        value
        for name, value in state.items()
        if name.endswith(("count", "attempts")) and isinstance(value, int)
    )
    if (
        summary["platform"] != args.platform
        or summary["status"] != "PASS"
        or summary["candidate_replay_status"] != "PASS"
        or summary["production_evaluator_dependency_count"] != 0
        or summary["production_golden_read_count"] != 0
        or summary["torch_imported"] is not False
        or counts["post_trust_pack_failures"] != 0
        or nonzero_process
        or nonzero_state
        or files["forbidden_read_count"] != 0
    ):
        raise ValueError(
            "oracle-free exact-F20 production did not pass isolation gates"
        )
    body = {
        "schema_version": 2,
        "platform": args.platform,
        "f20_sha": args.f20_sha,
        "selected_manifest_hash": selected.manifest_hash,
        "selector_receipt_hash": selector.receipt_hash,
        "production_output_hash": summary["production_output_hash"],
        "production_batch_hash": summary["production_batch_hash"],
        "candidate_pack_hash": summary["candidate_pack_hash"],
        "candidate_tree_hash": summary["candidate_tree_hash"],
        "candidate_replay_hash": summary["candidate_replay_hash"],
        "candidate_replay_status": summary["candidate_replay_status"],
        "production_completed_before_evaluator": True,
        "production_evaluator_read_count": 0,
        "production_golden_read_count": 0,
        "production_network_access_count": 0,
        "post_trust_pack_failure_count": 0,
        "status": "PASS",
    }
    (args.output / "m336e_production_execution.json").write_text(
        canonical_json({**body, "seal_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
