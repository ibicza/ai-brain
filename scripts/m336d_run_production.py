"""Materialize sealed selections transiently and run oracle-free production."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336d_final_pipeline import (
    materialize_selected_sources,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--selected-manifest", type=Path, required=True)
    parser.add_argument("--selector-receipt", type=Path, required=True)
    parser.add_argument("--f19-sha", required=True)
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("fresh production output already exists")
    selected = json.loads(args.selected_manifest.read_text(encoding="utf-8"))
    selector = json.loads(args.selector_receipt.read_text(encoding="utf-8"))
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
    selected_body = dict(selected)
    selected_hash = selected_body.pop("manifest_hash")
    selector_body = dict(selector)
    selector_hash = selector_body.pop("receipt_hash")
    if (
        head != args.f19_sha
        or len(head) != 40
        or status
        or content_hash(selected_body) != selected_hash
        or content_hash(selector_body) != selector_hash
        or selector["f19_sha"] != head
        or selector["selected_manifest_hash"] != selected_hash
        or selector["selector_invocation_count"] != 1
        or selector["selector_rerun_count"] != 0
    ):
        raise ValueError("production requires clean exact-F19 selector evidence")
    if selected["file_count"] != 180 or selected["root_count"] < 3:
        raise ValueError("production selection violates the F19 policy")
    distribution = tuple(tuple(item) for item in selected["root_distribution"])
    if (
        sum(count for _family, count in distribution) != 180
        or len(distribution) != selected["root_count"]
        or max(count for _family, count in distribution) / 180 > 0.35
    ):
        raise ValueError("production selection violates frozen balance invariants")
    with tempfile.TemporaryDirectory(prefix="m336d-selected-") as temporary:
        source_root = Path(temporary) / "selected"
        materialize_selected_sources(
            args.vault.resolve(strict=True), selected, source_root
        )
        command = (
            sys.executable,
            str(repository / "scripts/m336_run_oracle_free_production.py"),
            "--source-root",
            str(source_root),
            "--output",
            str(args.output),
            "--platform",
            args.platform,
        )
        subprocess.run(command, cwd=repository, check=True)
    summary = json.loads(
        (args.output / "production_summary.json").read_text(encoding="utf-8")
    )
    body = {
        "schema_version": 1,
        "platform": args.platform,
        "f19_sha": args.f19_sha,
        "selected_manifest_hash": selected["manifest_hash"],
        "production_output_hash": summary["production_output_hash"],
        "candidate_pack_hash": summary["candidate_pack_hash"],
        "candidate_tree_hash": summary["candidate_tree_hash"],
        "candidate_replay_status": summary["candidate_replay_status"],
        "production_evaluator_dependency_count": summary[
            "production_evaluator_dependency_count"
        ],
        "production_completed_before_evaluator": True,
        "network_access_count": 0,
        "golden_read_count": summary["production_golden_read_count"],
        "status": summary["status"],
    }
    (args.output / "m336d_production_seal.json").write_text(
        canonical_json({**body, "seal_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
