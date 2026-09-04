"""Compare M-33.6d disclosed pre-freeze outputs across Windows and Karina."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash

_PLATFORM_CONTEXT = frozenset({"platform_summary.json", "evidence_manifest.json"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--karina", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    windows = args.windows.resolve(strict=True)
    karina = args.karina.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("M-33.6d cross-platform output already exists")
    left = _manifest(windows)
    right = _manifest(karina)
    if set(left) != set(right):
        raise ValueError("Windows/Karina pre-freeze path sets differ")
    rows = tuple(
        {
            "relative_path": path,
            "windows_sha256": left[path],
            "karina_sha256": right[path],
            "equal": left[path] == right[path],
        }
        for path in sorted(left)
        if path not in _PLATFORM_CONTEXT
    )
    contextual = tuple(
        {
            "relative_path": path,
            "windows_sha256": left[path],
            "karina_sha256": right[path],
            "expected_platform_context": True,
        }
        for path in sorted(_PLATFORM_CONTEXT)
    )
    difference_count = sum(not row["equal"] for row in rows)
    body = {
        "schema_version": 1,
        "comparison_count": len(rows),
        "comparisons": rows,
        "platform_context_artifacts": contextual,
        "platform_independent_difference_count": difference_count,
        "status": "PASS" if difference_count == 0 and rows else "FAIL",
    }
    result = {**body, "report_hash": content_hash(body)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(result) + "\n", encoding="utf-8", newline="\n")


def _manifest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): bytes_hash(path.read_bytes())
        for path in root.rglob("*")
        if path.is_file()
    }


if __name__ == "__main__":
    main()
