"""Create a names/metadata-only untouched-candidate cache census."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336e_metadata_pool import (
    scan_m336e_local_cache_names,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True)
    parser.add_argument(
        "--root",
        action="append",
        nargs=2,
        metavar=("CACHE_CLASS", "PATH"),
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("cache-census output already exists")
    roots = tuple((name, Path(path).resolve()) for name, path in args.root)
    report = scan_m336e_local_cache_names(roots, platform=args.platform)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(report) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
