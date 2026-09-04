"""Verify the exact four-commit M-33.6d freeze/evidence protocol."""

from __future__ import annotations

import argparse
import subprocess
from itertools import pairwise
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash

E18 = "38082dd1eab82ebfff46ad3c55f5021068909f83"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--r19", required=True)
    parser.add_argument("--f19", required=True)
    parser.add_argument("--h19", required=True)
    parser.add_argument("--e19")
    parser.add_argument("--upstream-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    if args.output.exists():
        raise FileExistsError("fresh commit protocol report exists")
    chain = (E18, args.r19, args.f19, args.h19, *((args.e19,) if args.e19 else ()))
    parent_equal = all(
        _git(root, "rev-parse", f"{child}^") == parent
        for parent, child in pairwise(chain)
    )
    merge_count = int(
        _git(root, "rev-list", "--min-parents=2", f"{E18}..{chain[-1]}", "--count")
    )
    h19_paths = tuple(
        _git(root, "diff", "--name-only", args.f19, args.h19).splitlines()
    )
    h19_forbidden = tuple(
        path
        for path in h19_paths
        if not path.startswith(
            ("evaluation/m336d_final_java/", "artifacts/acquisition/disclosed_java/")
        )
    )
    e19_paths = (
        tuple(_git(root, "diff", "--name-only", args.h19, args.e19).splitlines())
        if args.e19
        else ()
    )
    e19_forbidden = tuple(
        path
        for path in e19_paths
        if not path.startswith(("evaluation/m336d_final_java/e19/", "docs/m336d_"))
        and path != "runs/m336d_final_report.md"
    )
    head = _git(root, "rev-parse", "HEAD^{commit}")
    remote = _git(root, "rev-parse", f"{args.upstream_ref}^{{commit}}")
    body = {
        "schema_version": 1,
        "chain": chain,
        "parent_chain_exact": parent_equal,
        "merge_commit_count": merge_count,
        "h19_changed_paths": h19_paths,
        "h19_forbidden_path_count": len(h19_forbidden),
        "e19_changed_paths": e19_paths,
        "e19_forbidden_path_count": len(e19_forbidden),
        "head_upstream_remote_equal": head == remote == chain[-1],
        "status": "PASS"
        if parent_equal
        and not merge_count
        and not h19_forbidden
        and not e19_forbidden
        and head == remote == chain[-1]
        else "FAIL",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json({**body, "report_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if body["status"] != "PASS":
        raise SystemExit("M-33.6d commit protocol failed")


if __name__ == "__main__":
    main()
