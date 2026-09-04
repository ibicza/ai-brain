"""Compare all platform-independent M-33.6c exact-I18 artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

_FILES = (
    "preparation/candidate_authority.json",
    "preparation/license_forensics.json",
    "preparation/selector_receipt.json",
    "preparation/source_use_authorization.json",
    "preparation/preparation_summary.json",
    "production/production_output.json",
    "production/component_manifest.json",
    "production/packability_report.json",
    "production/trust_closure.json",
    "production/production_counts.json",
    "production/candidate_replay.json",
    "evaluation/evaluation_report.json",
    "evaluation/license_authenticity_breakdown.json",
    "evaluation/runtime_proof.json",
    "evaluation/oracle/semantic_goldens.json",
    "evaluation/oracle/target_census.json",
)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _platform_independent(relative: str, value):
    if relative == "evaluation/runtime_proof.json":
        value = dict(value)
        value.pop("exact_query_performance", None)
        value.pop("report_hash", None)
    return value


def _tree(root: Path) -> tuple[tuple[str, str], ...]:
    return tuple(
        (item.relative_to(root).as_posix(), bytes_hash(item.read_bytes()))
        for item in sorted(
            (value for value in root.rglob("*") if value.is_file()),
            key=lambda value: value.relative_to(root).as_posix().encode("utf-8"),
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--karina", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M-33.6c platform comparison output exists")
    windows = args.windows.resolve(strict=True)
    karina = args.karina.resolve(strict=True)
    comparisons = []
    differences = []
    for relative in _FILES:
        left = windows / relative
        right = karina / relative
        left_value = _platform_independent(relative, _read(left))
        right_value = _platform_independent(relative, _read(right))
        left_hash = content_hash(left_value)
        right_hash = content_hash(right_value)
        equal = left_value == right_value
        comparisons.append((relative, left_hash, right_hash, equal))
        if not equal:
            differences.append(relative)
    left_tree = _tree(windows / "production/candidate_pack")
    right_tree = _tree(karina / "production/candidate_pack")
    pack_equal = left_tree == right_tree
    comparisons.append(
        (
            "production/candidate_pack",
            content_hash(left_tree),
            content_hash(right_tree),
            pack_equal,
        )
    )
    if not pack_equal:
        differences.append("production/candidate_pack")
    body = {
        "schema_version": 1,
        "comparison_count": len(comparisons),
        "comparisons": tuple(comparisons),
        "platform_independent_differences": tuple(sorted(differences)),
        "platform_independent_difference_count": len(differences),
        "status": "PASS" if not differences else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json({**body, "report_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if differences:
        raise SystemExit("M-33.6c platform-independent artifacts differ")


if __name__ == "__main__":
    main()
