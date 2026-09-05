"""Append every downloaded M-33.6e identity to the tracked public registry."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.java_disclosed_registry import (
    DEFAULT_REGISTRY_ROOT,
    DisclosedJavaMaterialEntry,
    append_disclosed_java_entries_v2,
    load_disclosed_java_registry,
    verify_disclosed_java_registry,
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _require_exact_f20(repository: Path, f20_sha: str, registry: Path) -> None:
    head = subprocess.run(
        ("git", "rev-parse", "HEAD^{commit}"),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != f20_sha or len(head) != 40:
        raise ValueError("registry append requires exact F20")
    try:
        registry_relative = registry.resolve(strict=True).relative_to(repository)
    except ValueError as exc:
        raise ValueError(
            "public registry must be inside the exact F20 worktree"
        ) from exc
    changed = subprocess.run(
        ("git", "status", "--porcelain=v1", "--", str(registry_relative)),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if changed:
        raise ValueError("registry append requires an unchanged F20 registry")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--disclosure-append", type=Path, required=True)
    parser.add_argument("--f20-sha", required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    registry = args.registry.resolve(strict=True)
    _require_exact_f20(repository, args.f20_sha, registry)
    if args.output.exists():
        raise FileExistsError("fresh registry append receipt already exists")
    verify_disclosed_java_registry(registry)
    previous = load_disclosed_java_registry(registry)
    previous_bytes = {
        path.name: bytes_hash(path.read_bytes())
        for path in (registry / "entries").glob("*.json")
    }
    disclosure = _load(args.disclosure_append.resolve(strict=True))
    rows = tuple(DisclosedJavaMaterialEntry(**item) for item in disclosure["entries"])
    if (
        not rows
        or disclosure["downloaded_candidate_count"] != len(rows)
        or disclosure["all_downloaded_candidates_included"] is not True
    ):
        raise ValueError("disclosure append does not cover every downloaded candidate")
    manifest, receipt = append_disclosed_java_entries_v2(
        registry,
        rows,
        acquisition_run_id="m336e.fresh-java.global-acquisition.v1",
        f20_sha=args.f20_sha,
    )
    verify_disclosed_java_registry(registry)
    unchanged = all(
        bytes_hash((registry / "entries" / name).read_bytes()) == digest
        for name, digest in previous_bytes.items()
    )
    if (
        len(previous) != 30
        or not unchanged
        or manifest.entry_hashes[:30] != tuple(item.entry_hash for item in previous)
    ):
        raise ValueError("registry append did not preserve its exact E19 prefix")
    args.output.mkdir(parents=True)
    (args.output / "append_receipt.json").write_text(
        canonical_json(asdict(receipt)) + "\n", encoding="utf-8", newline="\n"
    )
    body = {
        "schema_version": 2,
        "append_receipt_hash": receipt.receipt_hash,
        "all_previous_entry_bytes_unchanged": unchanged,
        "original_six_entries_preserved": True,
        "exact_thirty_entry_prefix_preserved": True,
        "status": "PASS",
    }
    (args.output / "verification.json").write_text(
        canonical_json({**body, "report_hash": content_hash(body)}) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
