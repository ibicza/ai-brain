"""Compare platform outputs from the shared portable-vault verifier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--karina", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh portable vault comparison already exists")
    windows = json.loads(args.windows.read_text(encoding="utf-8"))
    karina = json.loads(args.karina.read_text(encoding="utf-8"))
    windows_rows = {row["canonical_path"]: row for row in windows["rows"]}
    karina_rows = {row["canonical_path"]: row for row in karina["rows"]}
    physical_differences = tuple(
        sorted(
            path
            for path in set(windows_rows) | set(karina_rows)
            if windows_rows.get(path) != karina_rows.get(path)
        )
    )
    canonical_difference = int(windows["rows"] != karina["rows"])
    tree_difference = int(windows["portable_tree_hash"] != karina["portable_tree_hash"])
    body = {
        "schema_version": 2,
        "windows_file_count": windows["file_count"],
        "karina_file_count": karina["file_count"],
        "physical_difference_count": len(physical_differences),
        "physical_different_paths": physical_differences,
        "canonical_manifest_difference_count": canonical_difference,
        "portable_tree_hash_difference_count": tree_difference,
        "windows_portable_tree_hash": windows["portable_tree_hash"],
        "karina_portable_tree_hash": karina["portable_tree_hash"],
        "status": (
            "PASS"
            if not physical_differences
            and not canonical_difference
            and not tree_difference
            else "FAIL"
        ),
    }
    result = {**body, "report_hash": content_hash(body)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(result) + "\n", encoding="utf-8", newline="\n"
    )
    if result["status"] != "PASS":
        raise SystemExit("portable vault differs between platforms")


if __name__ == "__main__":
    main()
