"""Run the executable M-33.6k.9 controller-admission mutation suite."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k9_admission import (
    M336K9_ADMISSION_MUTATION_CASES,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    python = args.python.resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output.exists() or output.is_relative_to(repository):
        raise M336K2ProtocolError("M336K9 mutation output is stale or public")
    result = subprocess.run(
        (
            str(python),
            "-m",
            "pytest",
            "-q",
            "tests/test_m336k9_controller_admission.py",
        ),
        cwd=repository,
        capture_output=True,
        check=False,
    )
    body = {
        "schema_version": 1,
        "contract_role": "M336K9_CONTROLLER_ADMISSION_MUTATION_REPORT",
        "mutation_cases": M336K9_ADMISSION_MUTATION_CASES,
        "mutation_case_count": len(M336K9_ADMISSION_MUTATION_CASES),
        "test_exit_code": result.returncode,
        "stdout_bytes_hash": bytes_hash(result.stdout),
        "stderr_bytes_hash": bytes_hash(result.stderr),
        "accepted_invalid_count": 0 if result.returncode == 0 else -1,
        "wrong_rejection_layer_count": 0 if result.returncode == 0 else -1,
        "status": "PASS" if result.returncode == 0 else "FAIL",
    }
    report = {**body, "report_hash": content_hash(body)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(report) + "\n", encoding="utf-8", newline="\n")
    print(canonical_json(report))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
