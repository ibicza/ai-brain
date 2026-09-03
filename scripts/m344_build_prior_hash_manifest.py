"""Build the F13 prior/development Java source hash denylist."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, action="append", required=True)
    parser.add_argument("--hash", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("prior hash manifest already exists")
    if not all(len(value) == 64 for value in args.hash):
        raise ValueError("explicit prior hash is invalid")
    hashes = tuple(
        sorted(
            {*args.hash}
            | {
                bytes_hash(path.read_bytes())
                for root in args.root
                for path in root.resolve(strict=True).rglob("*.java")
            }
        )
    )
    body = {
        "schema_version": 1,
        "purpose": "m344-final-source-prior-and-development-denylist",
        "snapshot_bytes_hashes": hashes,
        "snapshot_hash_count": len(hashes),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json({**body, "manifest_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
