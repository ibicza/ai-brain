"""Collect hash-bound M-33.6e timing and memory measurements."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measurement", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh performance summary already exists")
    rows = []
    for path in args.measurement:
        source = path.resolve(strict=True)
        value = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError(f"{source} must contain a JSON object")
        rows.append(
            {
                "measurement_id": source.stem,
                "source_sha256": bytes_hash(source.read_bytes()),
                "reported_platform": value.get("platform", "cross-platform"),
                "reported_status": value.get("status", "MEASURED"),
                "measurement_hash": value.get(
                    "report_hash",
                    value.get("receipt_hash", bytes_hash(source.read_bytes())),
                ),
            }
        )
    rows = tuple(
        sorted(rows, key=lambda item: (item["measurement_id"], item["source_sha256"]))
    )
    body = {
        "schema_version": 2,
        "measurement_count": len(rows),
        "measurements": rows,
        "all_measurements_present": bool(rows),
        "status": "PASS" if rows else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json({**body, "report_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
