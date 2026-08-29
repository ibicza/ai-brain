"""Verify F12/H12/E12 path boundaries and the immutable final selector seal."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

ROOT = Path(__file__).resolve().parents[1]
FROZEN_PREFIXES = ("src/", "schemas/", "scripts/", "tests/", "config/")
FROZEN_FILES = {"pyproject.toml", "uv.lock"}
EVIDENCE_PREFIXES = ("runs/", "docs/", ".code-review-graph/")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--f12", required=True)
    parser.add_argument("--h12")
    parser.add_argument("--e12")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    selectors_path = ROOT / "config/m33_final_source_selectors.json"
    selectors_bytes = selectors_path.read_bytes()
    selectors = json.loads(selectors_bytes)
    _verify_selectors(selectors)
    h12_changes = _changed(args.f12, args.h12) if args.h12 else ()
    frozen_changes = tuple(
        item
        for item in h12_changes
        if item in FROZEN_FILES or item.startswith(FROZEN_PREFIXES)
    )
    e12_changes = _changed(args.h12, args.e12) if args.h12 and args.e12 else ()
    forbidden_e12 = tuple(
        item for item in e12_changes if not item.startswith(EVIDENCE_PREFIXES)
    )
    result = {
        "status": ("PASS" if not frozen_changes and not forbidden_e12 else "FAIL"),
        "f12": args.f12,
        "h12": args.h12,
        "e12": args.e12,
        "selector_bytes_hash": bytes_hash(selectors_bytes),
        "h12_changed_paths": h12_changes,
        "h12_frozen_changes": frozen_changes,
        "e12_changed_paths": e12_changes,
        "e12_forbidden_changes": forbidden_e12,
    }
    result = {**result, "report_hash": content_hash(result)}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            canonical_json(result) + "\n", encoding="utf-8", newline="\n"
        )
    print(canonical_json(result))
    return 0 if result["status"] == "PASS" else 1


def _changed(start: str, end: str | None) -> tuple[str, ...]:
    if not end:
        return ()
    process = subprocess.run(
        ["git", "diff", "--name-only", f"{start}..{end}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(item for item in process.stdout.splitlines() if item)


def _verify_selectors(value: dict) -> None:
    if value["final_source_seal_version"] != 1 or len(value["sets"]) != 4:
        raise ValueError("final source seal identity is invalid")
    if value["task_schema"] != {
        "biology": 125,
        "history": 100,
        "java": 125,
        "kinematics": 150,
        "minimum_semantically_unique": 500,
    }:
        raise ValueError("final task schema changed")
    if value["thresholds"]["wrong_automatically_trusted"] != 0:
        raise ValueError("trusted precision threshold changed")
    for source_set in value["sets"]:
        for resource in source_set["resources"]:
            if any(
                marker in json.dumps(resource)
                for marker in ("@concept", "@api", "@test")
            ):
                raise ValueError("final selector contains compiler annotation")


if __name__ == "__main__":
    raise SystemExit(main())
