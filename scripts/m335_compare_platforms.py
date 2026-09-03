"""Compare M-33.5 platform-independent development artifacts byte-for-byte."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

FILES = (
    "production_output.json",
    "production_counts.json",
    "packability_report.json",
    "component_manifest.json",
    "component_roots.json",
    "candidate_replay.json",
    "candidate_installation.json",
    "runtime_query_probes.json",
    "evaluation_report.json",
)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _tree(root: Path) -> tuple[tuple[str, str], ...]:
    return tuple(
        (item.relative_to(root).as_posix(), bytes_hash(item.read_bytes()))
        for item in sorted(
            (value for value in root.rglob("*") if value.is_file()),
            key=lambda value: value.relative_to(root).as_posix().encode("utf-8"),
        )
    )


def _matrix_components(path: Path):
    report = _read(path)
    return tuple(
        (
            item["case"],
            item["platform_independent"],
            item["component_roots_hash"],
        )
        for item in report["cases"]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--karina", type=Path, required=True)
    parser.add_argument("--windows-matrix", type=Path, required=True)
    parser.add_argument("--karina-matrix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    windows = args.windows.resolve(strict=True)
    karina = args.karina.resolve(strict=True)
    differences = []
    comparisons = []
    for relative in FILES:
        left = windows / relative
        right = karina / relative
        left_hash = bytes_hash(left.read_bytes())
        right_hash = bytes_hash(right.read_bytes())
        equal = left_hash == right_hash
        comparisons.append((relative, left_hash, right_hash, equal))
        if not equal:
            differences.append((relative, left_hash, right_hash))
    for relative in ("candidate_pack",):
        left_tree = _tree(windows / relative)
        right_tree = _tree(karina / relative)
        left_hash = content_hash(left_tree)
        right_hash = content_hash(right_tree)
        equal = left_tree == right_tree
        comparisons.append((relative, left_hash, right_hash, equal))
        if not equal:
            differences.append((relative, left_hash, right_hash))
    windows_matrix = _matrix_components(args.windows_matrix.resolve(strict=True))
    karina_matrix = _matrix_components(args.karina_matrix.resolve(strict=True))
    matrix_equal = windows_matrix == karina_matrix
    comparisons.append(
        (
            "determinism_matrix_platform_independent_components",
            content_hash(windows_matrix),
            content_hash(karina_matrix),
            matrix_equal,
        )
    )
    if not matrix_equal:
        differences.append(
            (
                "determinism_matrix_platform_independent_components",
                content_hash(windows_matrix),
                content_hash(karina_matrix),
            )
        )
    component_rows = _read(windows / "component_roots.json")["components"]
    peer_component_rows = _read(karina / "component_roots.json")["components"]
    first_stage = "NONE"
    for left, right in zip(component_rows, peer_component_rows, strict=False):
        if left != right:
            first_stage = left["stage"]
            break
    if len(component_rows) != len(peer_component_rows) and first_stage == "NONE":
        first_stage = "COMPONENT_COUNT"
    body = {
        "schema_version": 1,
        "comparison_count": len(comparisons),
        "comparisons": tuple(comparisons),
        "difference_count": len(differences),
        "differences": tuple(differences),
        "component_manifests_byte_identical": bytes_hash(
            (windows / "component_manifest.json").read_bytes()
        )
        == bytes_hash((karina / "component_manifest.json").read_bytes()),
        "candidate_pack_byte_identical": _tree(windows / "candidate_pack")
        == _tree(karina / "candidate_pack"),
        "first_divergent_stage": first_stage,
        "status": "PASS" if not differences and first_stage == "NONE" else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json({**body, "report_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if body["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
