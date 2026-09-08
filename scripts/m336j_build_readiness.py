"""Build independent public-safe M-33.6j exact-R25 readiness evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)
from ai_brain.stage3.acquisition.m336j_readiness import (
    readiness_request_from_dict,
    verify_m336j_ready_for_final_freeze,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M336J readiness output must be fresh")
    request = readiness_request_from_dict(strict_json_file(args.request))
    result = verify_m336j_ready_for_final_freeze(request)
    write_canonical_json(args.output, asdict(result))


if __name__ == "__main__":
    main()
