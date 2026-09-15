"""Run the closed-under-rehash M-33.6k.10 acquisition-binding suite."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_startup import startup_receipt_from_path
from ai_brain.stage3.acquisition.m336k10_binding import M336K10_MUTATION_CASES


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--startup-receipt", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    python = args.python.resolve(strict=True)
    output = args.output.resolve(strict=False)
    startup = startup_receipt_from_path(args.startup_receipt.resolve(strict=True))
    if output.exists() or output.is_relative_to(repository):
        raise M336K2ProtocolError("M336K10 mutation output is stale or public")
    result = subprocess.run(
        (
            str(python),
            "-m",
            "pytest",
            "-q",
            "tests/test_m336k10_official_acquisition_binding.py",
            "-k",
            "closed_under_rehash_semantic_mutations",
        ),
        cwd=repository,
        env={
            **os.environ,
            "PYTHONPATH": str(repository / "src"),
            "PYTHONNOUSERSITE": "1",
        },
        capture_output=True,
        check=False,
    )
    passed = result.returncode == 0
    body = {
        "schema_version": 1,
        "contract_role": "M336K10_ACQUISITION_BINDING_MUTATION_REPORT",
        "mutation_cases": M336K10_MUTATION_CASES,
        "mutation_case_count": len(M336K10_MUTATION_CASES),
        "test_exit_code": result.returncode,
        "stdout_bytes_hash": bytes_hash(result.stdout),
        "stderr_bytes_hash": bytes_hash(result.stderr),
        "accepted_invalid_count": 0 if passed else -1,
        "wrong_rejection_layer_count": 0 if passed else -1,
        "hash_only_rejection_count": 0 if passed else -1,
        "fully_rehashed_semantic_rejection_count": (
            len(M336K10_MUTATION_CASES) - 2 if passed else -1
        ),
        "source_structure_rejection_count": 2 if passed else -1,
        "startup_receipt_hash": startup.receipt_hash,
        "status": "PASS" if passed else "FAIL",
    }
    report = {**body, "report_hash": content_hash(body)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(report) + "\n", encoding="utf-8", newline="\n")
    print(canonical_json(report))
    if not passed:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
