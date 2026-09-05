"""Run the exact bounded source leak scan over one or more public trees."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336d_leak_scan import scan_fresh_source_leaks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--public", type=Path, action="append", required=True)
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--base-sha")
    parser.add_argument("--head-sha")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh source-leak report already exists")
    range_values = (args.repository, args.base_sha, args.head_sha)
    if any(range_values) and not all(range_values):
        raise ValueError("Git-object leak scan requires repository, base, and head")
    public_roots = tuple(path.resolve(strict=True) for path in args.public)
    git_rows = ()
    with tempfile.TemporaryDirectory(prefix="m336e-reachable-blobs-") as temporary:
        if all(range_values):
            repository = args.repository.resolve(strict=True)
            base = _git_text(repository, "rev-parse", f"{args.base_sha}^{{commit}}")
            head = _git_text(repository, "rev-parse", f"{args.head_sha}^{{commit}}")
            if base != args.base_sha or head != args.head_sha:
                raise ValueError("Git-object leak scan commit binding mismatch")
            object_lines = _git_text(
                repository, "rev-list", "--objects", f"{base}..{head}"
            ).splitlines()
            materialized = Path(temporary)
            rows = []
            for index, line in enumerate(object_lines):
                object_id, _, logical_path = line.partition(" ")
                if _git_text(repository, "cat-file", "-t", object_id) != "blob":
                    continue
                raw = subprocess.run(
                    ("git", "cat-file", "blob", object_id),
                    cwd=repository,
                    check=True,
                    capture_output=True,
                ).stdout
                suffix = Path(logical_path).suffix if logical_path else ".blob"
                target = materialized / f"{index:06d}-{object_id}{suffix}"
                target.write_bytes(raw)
                rows.append((object_id, logical_path, len(raw)))
            git_rows = tuple(rows)
            public_roots = (*public_roots, materialized)
        report = scan_fresh_source_leaks(
            args.vault.resolve(strict=True),
            public_roots,
        )
    report_body = dict(report)
    report_body.pop("report_hash")
    report_body.update(
        {
            "git_base_sha": args.base_sha or "NOT_REQUESTED",
            "git_head_sha": args.head_sha or "NOT_REQUESTED",
            "reachable_git_blob_count": len(git_rows),
            "reachable_git_blob_manifest_hash": content_hash(git_rows),
        }
    )
    report = {**report_body, "report_hash": content_hash(report_body)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(report) + "\n", encoding="utf-8", newline="\n"
    )
    if report["status"] != "PASS":
        raise SystemExit("M-33.6e public tree contains fresh source material")


def _git_text(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


if __name__ == "__main__":
    main()
