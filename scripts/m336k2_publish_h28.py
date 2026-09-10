"""Invoke the native M-33.6k.2 H28 source-free publisher."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336k2_publication import (
    publication_contract_from_dict,
    stage_m336k2_h28_publication,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument("--exact-f28-sha", required=True)
    parser.add_argument("--production-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract", type=Path)
    args = parser.parse_args()
    contract = (
        publication_contract_from_dict(
            json.loads(args.contract.resolve(strict=True).read_text(encoding="utf-8"))
        )
        if args.contract is not None
        else None
    )
    result = stage_m336k2_h28_publication(
        repository=args.repository,
        git_executable=args.git_executable,
        exact_f28_sha=args.exact_f28_sha,
        production_source=args.production_source,
        output=args.output,
        contract=contract,
    )
    print(canonical_json(asdict(result)))


if __name__ == "__main__":
    main()
