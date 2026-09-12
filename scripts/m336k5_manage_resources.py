"""Create path-free M336K5 resource and storage-reservation receipts."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError
from ai_brain.stage3.acquisition.m336k5_resources import (
    M336K5ResourceMonitor,
    allocate_m336k5_storage_reservation,
    build_m336k5_resource_budget_receipt,
    release_m336k5_storage_reservation,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    allocate = commands.add_parser("allocate")
    allocate.add_argument("--reservation", type=Path, required=True)
    allocate.add_argument("--reservation-bytes", type=int, required=True)
    allocate.add_argument("--output", type=Path, required=True)
    sample = commands.add_parser("sample-budget")
    sample.add_argument("--ledger", type=Path, required=True)
    sample.add_argument("--filesystem-root", type=Path, required=True)
    sample.add_argument("--private-root", type=Path, required=True)
    sample.add_argument("--temp-root", type=Path, required=True)
    sample.add_argument("--phase", required=True)
    sample.add_argument("--frozen-storage-budget-bytes", type=int, required=True)
    sample.add_argument("--output", type=Path, required=True)
    release = commands.add_parser("release")
    release.add_argument("--reservation", type=Path, required=True)
    release.add_argument("--reservation-receipt", type=Path, required=True)
    release.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "allocate":
        receipt = allocate_m336k5_storage_reservation(
            args.reservation, reservation_bytes=args.reservation_bytes
        )
        write_canonical_json(args.output, asdict(receipt))
    elif args.command == "sample-budget":
        monitor = M336K5ResourceMonitor(
            ledger=args.ledger,
            filesystem_root=args.filesystem_root,
            private_root=args.private_root,
            temp_root=args.temp_root,
        )
        monitor.sample(args.phase)
        receipt = build_m336k5_resource_budget_receipt(
            monitor.samples,
            frozen_storage_budget_bytes=args.frozen_storage_budget_bytes,
        )
        write_canonical_json(args.output, asdict(receipt))
        if receipt.status != "PASS":
            raise M336K2ProtocolError("M336K5 resource budget failed")
    else:
        reservation = _verified_receipt(args.reservation_receipt)
        path = args.reservation.resolve(strict=True)
        if (
            reservation.get("status") != "PASS"
            or reservation.get("sparse") is not False
            or path.stat().st_size != reservation.get("reservation_bytes")
        ):
            raise M336K2ProtocolError("M336K5 reservation release input changed")
        release_m336k5_storage_reservation(path)
        body = {
            "schema_version": 1,
            "contract_role": "PUBLIC_SAFE_M336K5_STORAGE_RESERVATION_RELEASE",
            "storage_reservation_receipt_hash": reservation["receipt_hash"],
            "released_bytes": reservation["reservation_bytes"],
            "status": "PASS",
        }
        write_canonical_json(args.output, {**body, "receipt_hash": content_hash(body)})


def _verified_receipt(path: Path) -> dict:
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("M336K5 resource receipt is not an object")
    body = dict(value)
    claimed = body.pop("receipt_hash", None)
    if not isinstance(claimed, str) or content_hash(body) != claimed:
        raise M336K2ProtocolError("M336K5 resource receipt hash changed")
    return value


if __name__ == "__main__":
    main()
