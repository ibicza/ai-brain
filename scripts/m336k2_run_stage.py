"""Execute one typed, state-bound M-33.6k.2 route stage."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_brain.stage3.acquisition.m336k2_stage import run_m336k2_stage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--startup-receipt", type=Path)
    args = parser.parse_args()
    run_m336k2_stage(
        request_path=args.request.resolve(strict=True),
        event=args.event,
        receipt_path=args.receipt.resolve(strict=False),
        startup_receipt_path=(
            args.startup_receipt.resolve(strict=True)
            if args.startup_receipt is not None
            else None
        ),
    )


if __name__ == "__main__":
    main()
