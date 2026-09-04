"""Record candidate source-cache presence using names and file metadata only."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336d_final_pipeline import scan_local_cache_names


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("windows", "karina"), required=True)
    parser.add_argument("--root", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh local-cache receipt already exists")
    roots = []
    for value in args.root:
        label, separator, raw_path = value.partition("=")
        if separator != "=" or not label or not raw_path:
            raise ValueError("cache root must be CLASS=PATH")
        roots.append((label, Path(raw_path)))
    report = scan_local_cache_names(tuple(roots), platform=args.platform)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(report) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
