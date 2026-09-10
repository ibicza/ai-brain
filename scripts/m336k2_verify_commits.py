"""Verify the exact native M-33.6k.2 Q28/F28/H28/E28 protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336k2_publication import (
    publication_contract_from_dict,
    verify_m336k2_commit_protocol,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument("--exact-q28-sha", required=True)
    parser.add_argument("--exact-f28-sha", required=True)
    parser.add_argument("--exact-h28-sha", required=True)
    parser.add_argument("--exact-e28-sha", required=True)
    parser.add_argument("--contract", type=Path)
    args = parser.parse_args()
    contract = (
        publication_contract_from_dict(
            json.loads(args.contract.resolve(strict=True).read_text(encoding="utf-8"))
        )
        if args.contract is not None
        else None
    )
    print(
        canonical_json(
            verify_m336k2_commit_protocol(
                repository=args.repository,
                git_executable=args.git_executable,
                exact_q28_sha=args.exact_q28_sha,
                exact_f28_sha=args.exact_f28_sha,
                exact_h28_sha=args.exact_h28_sha,
                exact_e28_sha=args.exact_e28_sha,
                contract=contract,
            )
        )
    )


if __name__ == "__main__":
    main()
