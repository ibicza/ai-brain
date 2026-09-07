"""Verify the exact M-33.6h readiness receipt before a future F23."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_brain.stage3.acquisition.m336h_contracts import strict_json_file
from ai_brain.stage3.acquisition.m336h_route import readiness_from_dict


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readiness", type=Path, required=True)
    parser.add_argument("--expected-r23-identity", required=True)
    parser.add_argument("--expected-q23-identity", required=True)
    args = parser.parse_args()
    value = strict_json_file(args.readiness)
    if not isinstance(value, dict):
        raise TypeError("M336H readiness must be an object")
    readiness = readiness_from_dict(value)
    if (
        readiness.r23_implementation_identity != args.expected_r23_identity
        or readiness.q23_evidence_identity != args.expected_q23_identity
    ):
        raise ValueError("M336H readiness is not bound to exact R23/Q23")
    print("READY_FOR_FRESH_FREEZE")


if __name__ == "__main__":
    main()
