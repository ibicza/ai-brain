"""Verify that the prospective or committed E18 delta is evidence-only."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash

_ALLOWED_EXACT = frozenset(
    {
        "docs/m336c_performance_report.md",
        "docs/m336c_spdx_contract_repair_report.md",
        "runs/m336c_spdx_contract_repair_report.md",
    }
)
_ALLOWED_PREFIXES = ("runs/m336c_final_gate/", "runs/m336c_development/")
_FORBIDDEN_PREFIXES = ("src/", "scripts/", "tools/", "tests/", "schemas/")
_FORBIDDEN_EXACT = frozenset({"pyproject.toml", "uv.lock"})


def _git(root: Path, *args: str) -> tuple[str, ...]:
    return tuple(
        line
        for line in subprocess.run(
            ("git", *args),
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.splitlines()
        if line
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--i18-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    output = args.output.resolve(strict=False)
    relative_output = output.relative_to(root).as_posix()
    changed = set(_git(root, "diff", "--name-only", args.i18_sha))
    changed.update(_git(root, "diff", "--cached", "--name-only", args.i18_sha))
    changed.add(relative_output)
    ordered = tuple(sorted(changed))
    forbidden = tuple(
        path
        for path in ordered
        if path in _FORBIDDEN_EXACT
        or path.startswith(_FORBIDDEN_PREFIXES)
        or not (path in _ALLOWED_EXACT or path.startswith(_ALLOWED_PREFIXES))
    )
    body = {
        "schema_version": 1,
        "i18_sha": args.i18_sha,
        "changed_paths": ordered,
        "changed_path_count": len(ordered),
        "forbidden_paths": forbidden,
        "forbidden_path_count": len(forbidden),
        "status": "PASS" if not forbidden else "FAIL",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        canonical_json({**body, "report_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if forbidden:
        raise SystemExit("M-33.6c evidence-only diff failed")


if __name__ == "__main__":
    main()
