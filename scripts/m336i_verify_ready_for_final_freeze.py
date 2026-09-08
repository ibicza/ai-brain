"""Verify M-33.6i pre-freeze readiness from bound, executable evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage3.acquisition.m336h_contracts import (
    strict_json_file,
    write_canonical_json,
)
from ai_brain.stage3.acquisition.m336i_readiness import (
    readiness_request_from_dict,
    verify_m336i_ready_for_final_freeze,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M336I readiness output must be fresh")
    value = strict_json_file(args.request)
    if not isinstance(value, dict):
        raise TypeError("M336I readiness request must be an object")
    result = verify_m336i_ready_for_final_freeze(readiness_request_from_dict(value))
    write_canonical_json(args.output, result)
    print(
        json.dumps({"status": result.status, "readiness_hash": result.readiness_hash})
    )


if __name__ == "__main__":
    main()
