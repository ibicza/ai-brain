"""Verify the exact no-merge E19-R20-Q20-F20-H20-E20 chain and path scopes."""

from __future__ import annotations

import argparse
import subprocess
from itertools import pairwise
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash

E19 = "74f7740aea907cd2b4a7e0b885a5d4c60e7aa2db"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args), cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _paths(root: Path, left: str, right: str) -> tuple[str, ...]:
    return tuple(_git(root, "diff", "--name-only", left, right).splitlines())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--r20", required=True)
    parser.add_argument("--q20", required=True)
    parser.add_argument("--f20", required=True)
    parser.add_argument("--h20", required=True)
    parser.add_argument("--e20", required=True)
    parser.add_argument("--upstream-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("fresh M-33.6e commit protocol report exists")
    chain = (E19, args.r20, args.q20, args.f20, args.h20, args.e20)
    parent_equal = all(
        _git(root, "rev-parse", f"{child}^") == parent
        for parent, child in pairwise(chain)
    )
    merge_count = int(
        _git(root, "rev-list", "--min-parents=2", f"{E19}..{args.e20}", "--count")
    )
    phase_paths = {
        name: _paths(root, left, right)
        for name, left, right in (
            ("r20", E19, args.r20),
            ("q20", args.r20, args.q20),
            ("f20", args.q20, args.f20),
            ("h20", args.f20, args.h20),
            ("e20", args.h20, args.e20),
        )
    }
    allowed = {
        "q20": ("evaluation/m336e_final_java/q20/", "docs/m336e_"),
        "f20": (
            "artifacts/acquisition/m336e_freeze_v4/",
            "artifacts/authority/m336e_user_authority_v1.txt",
            "docs/m336e_",
        ),
        "h20": (
            "evaluation/m336e_final_java/h20/",
            "artifacts/acquisition/disclosed_java/",
            "docs/m336e_",
        ),
        "e20": (
            "evaluation/m336e_final_java/e20/",
            "docs/m336e_",
            "runs/m336e_final_report.md",
        ),
    }
    forbidden = {
        phase: tuple(
            path for path in phase_paths[phase] if not path.startswith(prefixes)
        )
        for phase, prefixes in allowed.items()
    }
    head = _git(root, "rev-parse", "HEAD^{commit}")
    upstream = _git(root, "rev-parse", f"{args.upstream_ref}^{{commit}}")
    body = {
        "schema_version": 2,
        "chain": chain,
        "parent_chain_exact": parent_equal,
        "merge_commit_count": merge_count,
        "phase_changed_paths": tuple(sorted(phase_paths.items())),
        "forbidden_phase_paths": tuple(sorted(forbidden.items())),
        "forbidden_phase_path_count": sum(len(value) for value in forbidden.values()),
        "head_upstream_remote_equal": head == upstream == args.e20,
    }
    report = {
        **body,
        "status": "PASS"
        if parent_equal
        and merge_count == 0
        and not body["forbidden_phase_path_count"]
        and head == upstream == args.e20
        else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json({**report, "report_hash": content_hash(report)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if report["status"] != "PASS":
        raise SystemExit("M-33.6e commit protocol failed")


if __name__ == "__main__":
    main()
