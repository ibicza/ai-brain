"""Compare platform-independent M-33.6b disclosed rehearsal evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336b_readiness import verify_hashed_raw_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--karina", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    left = json.loads(args.windows.read_text(encoding="utf-8"))
    right = json.loads(args.karina.read_text(encoding="utf-8"))
    verify_hashed_raw_report(left)
    verify_hashed_raw_report(right)
    ignored = {"platform", "report_hash"}
    left_stable = {key: value for key, value in left.items() if key not in ignored}
    right_stable = {key: value for key, value in right.items() if key not in ignored}
    differences = tuple(
        key
        for key in sorted(set(left_stable) | set(right_stable))
        if left_stable.get(key) != right_stable.get(key)
    )
    body = {
        "schema_version": 1,
        "windows_report_hash": left["report_hash"],
        "karina_report_hash": right["report_hash"],
        "compared_field_count": len(set(left_stable) | set(right_stable)),
        "different_fields": differences,
        "difference_count": len(differences),
        "status": "PASS" if not differences else "FAIL",
    }
    report = {**body, "report_hash": content_hash(body)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(report) + "\n", encoding="utf-8", newline="\n"
    )
    if differences:
        raise SystemExit("M-33.6b rehearsal differs across platforms")


if __name__ == "__main__":
    main()
