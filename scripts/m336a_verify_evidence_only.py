"""Fail closed unless E16 differs from I16 only by approved evidence paths."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import PurePosixPath

ALLOWED = (
    "docs/m336a_license_freeze_repair_report.md",
    "docs/m336a_performance_report.md",
    "docs/m336a_historical_freeze_recheck.md",
    "docs/m336a_windows_timeout_forensics.md",
    "runs/m336a_license_freeze_repair_report.md",
    "runs/m336a_final_gate",
)
FORBIDDEN = (
    "src",
    "scripts",
    "tools",
    "tests",
    "schemas",
    "pyproject.toml",
    "uv.lock",
    "evaluation/m336a_disclosed_provenance",
)


def _under(path: str, prefixes) -> bool:
    value = PurePosixPath(path)
    return any(
        value == PurePosixPath(prefix) or PurePosixPath(prefix) in value.parents
        for prefix in prefixes
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--i16-sha", required=True)
    parser.add_argument("--e16-sha", default="HEAD")
    args = parser.parse_args()
    changed = tuple(
        line
        for line in subprocess.run(
            ["git", "diff", "--name-only", args.i16_sha, args.e16_sha],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        if line
    )
    invalid = tuple(path for path in changed if not _under(path, ALLOWED))
    forbidden = tuple(path for path in changed if _under(path, FORBIDDEN))
    if not changed or invalid or forbidden:
        raise ValueError(
            f"E16 evidence-only diff failed: changed={changed}, invalid={invalid}, forbidden={forbidden}"
        )
    print(f"PASS: {len(changed)} evidence-only paths")


if __name__ == "__main__":
    main()
