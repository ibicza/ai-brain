"""Externally verify Q25 against the exact pre-scanned evidence bytes."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)
from ai_brain.stage3.acquisition.m336j_evidence import (
    q25_staging_receipt_from_dict,
    verify_m336j_post_q25_commit,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--staging-receipt", type=Path, required=True)
    parser.add_argument("--exact-r25c-sha", required=True)
    parser.add_argument("--exact-q25-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M336J post-Q25 output must be fresh")
    value = strict_json_file(args.staging_receipt)
    receipt = q25_staging_receipt_from_dict(value)
    result = verify_m336j_post_q25_commit(
        repository=args.repository,
        git_executable=args.git_executable,
        staging_root=args.staging,
        staging_receipt=receipt,
        exact_r25c_sha=args.exact_r25c_sha,
        exact_q25_sha=args.exact_q25_sha,
    )
    write_canonical_json(args.output, asdict(result))


if __name__ == "__main__":
    main()
