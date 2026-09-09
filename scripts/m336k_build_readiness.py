"""Build source-free exact-R27 M-33.6k readiness evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k_readiness import (
    build_m336k_readiness_gate,
)


def _load(path: Path, hash_field: str) -> dict:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    body = dict(value)
    claimed = body.pop(hash_field, None)
    if claimed is None or content_hash(body) != claimed:
        raise ValueError(f"invalid M336K readiness input: {path.name}")
    return value


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--exact-r27-sha", required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--windows-quality", type=Path, required=True)
    parser.add_argument("--karina-quality", type=Path, required=True)
    parser.add_argument("--final-ledger", type=Path, required=True)
    parser.add_argument("--final-vault", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output.exists():
        raise FileExistsError("M336K readiness output must be fresh")
    if output.is_relative_to(repository):
        raise ValueError("M336K readiness evidence must remain outside Git")
    if (
        _git(repository, "rev-parse", "HEAD^{commit}") != args.exact_r27_sha
        or _git(repository, "status", "--porcelain=v1")
        or args.final_ledger.resolve(strict=False).exists()
        or args.final_vault.resolve(strict=False).exists()
    ):
        raise ValueError(
            "M336K readiness requires clean exact R27 and unspent final state"
        )
    qualification = args.qualification.resolve(strict=True)
    comparison = args.comparison.resolve(strict=True)
    gate = build_m336k_readiness_gate(
        exact_r27_sha=args.exact_r27_sha,
        archive_campaign=_load(
            qualification / "archive_mutation_campaign.json", "receipt_hash"
        ),
        mixed_campaign=_load(
            qualification / "mixed_candidate_fault_campaign.json", "receipt_hash"
        ),
        inventory=_load(qualification / "f26_candidate_inventory.json", "receipt_hash"),
        disclosure=_load(qualification / "f26_disclosure_recovery.json", "report_hash"),
        candidate_rehearsal=_load(
            qualification / "disclosed_rehearsal_summary.json", "report_hash"
        ),
        full_route_rehearsal=_load(
            comparison / "disclosed_full_route_rehearsal.json", "report_hash"
        ),
        cross_platform=_load(comparison / "cross_platform_report.json", "report_hash"),
        source_leak=_load(comparison / "source_leak_report.json", "report_hash"),
        windows_quality=_load(args.windows_quality, "receipt_hash"),
        karina_quality=_load(args.karina_quality, "receipt_hash"),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        canonical_json(asdict(gate)) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
