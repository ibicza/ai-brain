"""Stdlib-only target for testing pre-dispatch M336K13 launcher attestation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _write(path: Path, value: dict) -> None:
    payload = (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--validation-receipt", type=Path)
    parser.add_argument("--post-freeze-validation-receipt", type=Path)
    parser.add_argument("--reservation-release-receipt", type=Path)
    parser.add_argument("--startup-receipt", type=Path, required=True)
    parser.add_argument("--actual-launcher-plan-receipt", type=Path, required=True)
    args = parser.parse_args()
    startup = args.startup_receipt.resolve(strict=True).read_bytes()
    actual = args.actual_launcher_plan_receipt.resolve(strict=True).read_bytes()
    body = {
        "request_bytes_hash": hashlib.sha256(
            args.request.resolve(strict=True).read_bytes()
        ).hexdigest(),
        "startup_bytes_hash": hashlib.sha256(startup).hexdigest(),
        "actual_launcher_bytes_hash": hashlib.sha256(actual).hexdigest(),
        "operation": "validate" if args.validate_only else "execute",
        "status": "PASS",
    }
    if args.validate_only:
        if args.validation_receipt is None:
            raise RuntimeError("validation output is absent")
        _write(args.validation_receipt, body)
    else:
        args.post_freeze_validation_receipt.resolve(strict=True)
        if args.reservation_release_receipt is None:
            raise RuntimeError("execute output is absent")
        _write(args.reservation_release_receipt, body)


if __name__ == "__main__":
    main()
