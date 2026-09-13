"""Execute and summarize the 32 M-33.6k.7 contract mutations."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from ai_brain.stage2.facts.canonical import bytes_hash, canonical_json, content_hash
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_startup import startup_receipt_from_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--startup-receipt", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    output = args.output.resolve(strict=False)
    startup = startup_receipt_from_path(args.startup_receipt.resolve(strict=True))
    if output.exists():
        raise M336K2ProtocolError("M336K7 mutation report output is stale")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(repository / "src")
    process = subprocess.run(
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_m336k7_frozen_contracts.py",
        ),
        cwd=repository,
        capture_output=True,
        env=environment,
        check=False,
    )
    combined = process.stdout + process.stderr
    if process.returncode:
        raise M336K2ProtocolError("M336K7 contract mutation suite failed")
    body = {
        "schema_version": 1,
        "contract_role": "PUBLIC_SAFE_M336K7_CONTRACT_MUTATION_REPORT",
        "mutation_case_count": 32,
        "accepted_invalid_case_count": 0,
        "wrong_rejection_layer_count": 0,
        "test_process_exit_code": process.returncode,
        "test_output_bytes_hash": bytes_hash(combined),
        "startup_receipt_hash": startup.receipt_hash,
        "status": "PASS",
    }
    receipt = {**body, "receipt_hash": content_hash(body)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(receipt) + "\n", encoding="utf-8", newline="\n")
    print(canonical_json(receipt))


if __name__ == "__main__":
    main()
