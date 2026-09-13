"""Run the authoritative M-33.6k.6 persistent-capsule liveness verifier."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336k6_capsule import (
    verify_m336k6_persistent_capsule,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capsule", type=Path, required=True)
    parser.add_argument("--phase", required=True)
    args = parser.parse_args()
    receipt = verify_m336k6_persistent_capsule(
        args.capsule.resolve(strict=True), phase=args.phase
    )
    print(canonical_json(asdict(receipt)))


if __name__ == "__main__":
    main()
