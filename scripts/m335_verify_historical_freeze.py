"""Replay the F13/H13/E13 Git freeze with role-aware disclosure semantics."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.java_freeze_protocol import (
    verify_java_git_freeze_protocol,
)

BASE = "f83a4b72de5843d699f971932b0dd28c872ab533"
F13 = "af7657883fdb2c5ce47c3d82798ef7969b747c8c"
H13 = "3f42cb044daadf29f9c1a1c69ca4706f15f8c75b"
E13 = "f1599585c7b45e73eb3ba3cd9113155188eb6d26"
EXCLUDED_M33 = "b94c17dc8b1026fe9e338b5fc0a4926b23d68a39"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify_java_git_freeze_protocol(
        args.repository.resolve(strict=True),
        base_sha=BASE,
        f13_sha=F13,
        h13_sha=H13,
        e13_sha=E13,
        excluded_m33_sha=EXCLUDED_M33,
        branch=E13,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(asdict(report)) + "\n", encoding="utf-8", newline="\n"
    )
    if not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
