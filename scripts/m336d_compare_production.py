"""Compare all platform-neutral M-33.6d production artifacts byte-for-byte."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

PLATFORM_SPECIFIC = frozenset(
    {
        "production_performance.json",
        "production_process_audit.json",
        "production_file_access_audit.json",
        "production_state_audit.json",
        "m336d_production_seal.json",
        "production_summary.json",
    }
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--karina", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh production comparison exists")
    left = _rows(args.windows.resolve(strict=True))
    right = _rows(args.karina.resolve(strict=True))
    paths = tuple(sorted(set(left) | set(right)))
    differences = tuple(
        path
        for path in paths
        if path not in PLATFORM_SPECIFIC and left.get(path) != right.get(path)
    )
    body = {
        "schema_version": 1,
        "platform_neutral_artifact_count": sum(
            path not in PLATFORM_SPECIFIC for path in paths
        ),
        "platform_independent_difference_count": len(differences),
        "different_paths": differences,
        "windows_tree_hash": content_hash(tuple(sorted(left.items()))),
        "karina_tree_hash": content_hash(tuple(sorted(right.items()))),
        "status": "PASS" if not differences else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json({**body, "report_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if differences:
        raise SystemExit("platform-neutral production artifacts differ")


def _rows(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): bytes_hash(path.read_bytes())
        for path in root.rglob("*")
        if path.is_file()
    }


if __name__ == "__main__":
    main()
