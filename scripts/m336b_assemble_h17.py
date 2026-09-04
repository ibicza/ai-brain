"""Create the H17 role manifest and schema-bound disclosure report."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.java_freeze_roles import (
    build_final_artifact_role_manifest,
    dump_final_artifact_role_manifest,
    verify_schema_bound_disclosure,
)


def _paths(root: Path, f17: str):
    changed = subprocess.run(
        ("git", "diff", "--name-only", "--diff-filter=ACMR", f17),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    untracked = subprocess.run(
        ("git", "ls-files", "--others", "--exclude-standard"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return tuple(sorted(set(changed) | set(untracked)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--f17-sha", required=True)
    parser.add_argument("--evaluation-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    evaluation = args.evaluation_root.resolve()
    role_path = evaluation / "role_manifest.json"
    disclosure_path = evaluation / "disclosure_report.json"
    if role_path.exists() or disclosure_path.exists():
        raise FileExistsError("H17 role outputs must not exist")
    relative_role = role_path.relative_to(root).as_posix()
    relative_disclosure = disclosure_path.relative_to(root).as_posix()
    paths = tuple(
        sorted({*_paths(root, args.f17_sha), relative_role, relative_disclosure})
    )
    artifacts = {
        path: (root / path).read_bytes()
        if (root / path).exists()
        else b'{"report_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}\n'
        for path in paths
    }
    manifest = build_final_artifact_role_manifest(artifacts)
    role_path.parent.mkdir(parents=True, exist_ok=True)
    role_path.write_bytes(dump_final_artifact_role_manifest(manifest))
    artifacts[relative_role] = role_path.read_bytes()
    disclosure = verify_schema_bound_disclosure(artifacts, manifest)
    disclosure_path.write_text(
        canonical_json(asdict(disclosure)) + "\n", encoding="utf-8", newline="\n"
    )
    artifacts[relative_disclosure] = disclosure_path.read_bytes()
    final = verify_schema_bound_disclosure(artifacts, manifest)
    if final != disclosure or not final.passed:
        raise ValueError("H17 disclosure report is not self-consistent")


if __name__ == "__main__":
    main()
