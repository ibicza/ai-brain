"""Build non-self-referential M-33.6j Q25 evidence staging."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage3.acquisition.m336h_contracts import write_canonical_json
from ai_brain.stage3.acquisition.m336j_evidence import build_m336j_q25_staging


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qualification-inputs", type=Path, required=True)
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--exact-r25c-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        raise FileExistsError("M336J Q25 staging receipt must be fresh")
    receipt = build_m336j_q25_staging(
        qualification_input_root=args.qualification_inputs,
        readiness_result=args.readiness,
        output_root=args.output,
        exact_r25c_sha=args.exact_r25c_sha,
    )
    write_canonical_json(args.receipt, asdict(receipt))


if __name__ == "__main__":
    main()
