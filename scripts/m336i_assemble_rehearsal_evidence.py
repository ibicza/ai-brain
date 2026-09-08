"""Bind external M-33.6i rehearsal artifacts for independent readiness."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_brain.stage2.facts.canonical import content_hash
from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rehearsal-kind",
        choices=("DISCLOSED", "COUNT_NEUTRAL", "AUTHORIZED"),
        required=True,
    )
    for name in (
        "windows_rehearsal_receipt",
        "karina_rehearsal_receipt",
        "windows_production_root",
        "karina_production_root",
        "independent_evaluation",
        "staging_root",
        "staging_manifest",
        "staging_receipt",
        "sealed_vault",
        "output",
    ):
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, required=True)
    parser.add_argument("--authorized-acquisition-rehearsal-receipt", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M336I rehearsal evidence manifest must be fresh")
    required_paths = (
        args.windows_rehearsal_receipt,
        args.karina_rehearsal_receipt,
        args.windows_production_root,
        args.karina_production_root,
        args.independent_evaluation,
        args.staging_root,
        args.staging_manifest,
        args.staging_receipt,
        args.sealed_vault,
    )
    if any(not path.exists() for path in required_paths):
        raise ValueError("M336I rehearsal evidence input is missing")
    if (args.rehearsal_kind == "AUTHORIZED") != bool(
        args.authorized_acquisition_rehearsal_receipt
    ):
        raise ValueError("M336I authorized rehearsal evidence binding is inconsistent")
    body = {
        "schema_version": 1,
        "contract_role": "PRIVATE_M336I_REHEARSAL_EVIDENCE_BINDINGS",
        "rehearsal_kind": args.rehearsal_kind,
        "windows_rehearsal_receipt": str(
            args.windows_rehearsal_receipt.resolve(strict=True)
        ),
        "karina_rehearsal_receipt": str(
            args.karina_rehearsal_receipt.resolve(strict=True)
        ),
        "windows_production_root": str(
            args.windows_production_root.resolve(strict=True)
        ),
        "karina_production_root": str(args.karina_production_root.resolve(strict=True)),
        "independent_evaluation": str(args.independent_evaluation.resolve(strict=True)),
        "staging_root": str(args.staging_root.resolve(strict=True)),
        "staging_manifest": str(args.staging_manifest.resolve(strict=True)),
        "staging_receipt": str(args.staging_receipt.resolve(strict=True)),
        "sealed_vault": str(args.sealed_vault.resolve(strict=True)),
        "authorized_acquisition_rehearsal_receipt": (
            str(args.authorized_acquisition_rehearsal_receipt.resolve(strict=True))
            if args.authorized_acquisition_rehearsal_receipt
            else None
        ),
    }
    write_canonical_json(args.output, {**body, "manifest_hash": content_hash(body)})


if __name__ == "__main__":
    main()
