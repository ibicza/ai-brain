"""Compare sealed platform-independent M-33.6 production artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash


def _load(path: Path, name: str):
    return json.loads((path / name).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--karina", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("platform comparison output exists")
    names = (
        "production_output.json",
        "component_manifest.json",
        "packability_report.json",
        "trust_closure.json",
        "production_counts.json",
        "candidate_replay.json",
    )
    differences = []
    component_hashes = []
    for name in names:
        left = _load(args.windows, name)
        right = _load(args.karina, name)
        left_hash = content_hash(left)
        right_hash = content_hash(right)
        component_hashes.append((name, left_hash, right_hash))
        if left != right:
            differences.append(name)
    windows_summary = _load(args.windows, "production_summary.json")
    karina_summary = _load(args.karina, "production_summary.json")
    summary_keys = (
        "production_output_hash",
        "production_batch_hash",
        "component_manifest_hash",
        "candidate_pack_hash",
        "candidate_tree_hash",
        "candidate_replay_hash",
        "candidate_replay_status",
        "production_evaluator_dependency_count",
        "production_golden_read_count",
        "torch_imported",
        "status",
    )
    for key in summary_keys:
        if windows_summary[key] != karina_summary[key]:
            differences.append(f"production_summary.{key}")
    body = {
        "schema_version": 1,
        "component_hashes": tuple(component_hashes),
        "platform_independent_differences": tuple(sorted(differences)),
        "platform_independent_difference_count": len(differences),
        "windows_production_output_hash": windows_summary["production_output_hash"],
        "karina_production_output_hash": karina_summary["production_output_hash"],
        "status": "PASS" if not differences else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json({**body, "report_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if differences:
        raise SystemExit("M-33.6 platform-independent production differs")


if __name__ == "__main__":
    main()
