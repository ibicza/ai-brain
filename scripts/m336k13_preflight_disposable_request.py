"""Run M-33.6k.13 branch authority before allocating a large reservation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336k13_rehearsal import (
    M336K13RehearsalBranchAuthorityReceipt,
    build_m336k13_pre_reservation_authorization_projection,
    verify_m336k_rehearsal_branch_authority,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, action="append", default=[])
    parser.add_argument("--projection-output", type=Path, action="append", default=[])
    parser.add_argument("--implementation-tip")
    args = parser.parse_args()
    request = json.loads(args.request.resolve(strict=True).read_text(encoding="utf-8"))
    profile_id = request.get("official_profile_id")
    decision = verify_m336k_rehearsal_branch_authority(
        namespace=request.get("protocol_namespace", "m336k5"),
        disposable_branch=request.get("disposable_branch"),
        official_admission_only=request.get("official_admission_only", False),
        profile_id=profile_id,
    )
    receipt = M336K13RehearsalBranchAuthorityReceipt.build(decision)
    projection = None
    if args.projection_output:
        projection = build_m336k13_pre_reservation_authorization_projection(
            exact_implementation_tip=(
                args.implementation_tip or request.get("base_sha", "")
            ),
            disposable_label=request.get("disposable_label"),
            namespace=request.get("protocol_namespace", "m336k5"),
            disposable_branch=request.get("disposable_branch"),
            profile_id=profile_id,
        )
    for path in args.receipt_output:
        _write_once(path, receipt.canonical_object())
    for path in args.projection_output:
        _write_once(path, projection)
    print(
        canonical_json(
            {
                "branch_authority_receipt": receipt.canonical_object(),
                **(
                    {"authorization_projection": projection}
                    if projection is not None
                    else {}
                ),
            }
        )
    )


def _write_once(path: Path, value: dict) -> None:
    target = path.resolve(strict=False)
    if target.exists():
        raise FileExistsError("M336K13 preflight evidence must be fresh")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
