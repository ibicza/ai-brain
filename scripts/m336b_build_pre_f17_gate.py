"""Build the M-33.6b pre-F17 gate from verified raw reports."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336b_readiness import (
    M336BPreFreezeDecision,
    evaluate_m336b_pre_freeze_gate,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("readiness input must be an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in (
        "windows-rehearsal",
        "karina-rehearsal",
        "platform-comparison",
        "windows-quality",
        "karina-quality",
        "source-access-audit",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = {
        "windows_rehearsal": _load(args.windows_rehearsal),
        "karina_rehearsal": _load(args.karina_rehearsal),
        "platform_comparison": _load(args.platform_comparison),
        "windows_quality": _load(args.windows_quality),
        "karina_quality": _load(args.karina_quality),
        "source_access_audit": _load(args.source_access_audit),
    }
    gate = evaluate_m336b_pre_freeze_gate(reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(asdict(gate)) + "\n", encoding="utf-8", newline="\n"
    )
    if gate.decision is not M336BPreFreezeDecision.READY_TO_CREATE_F17:
        raise SystemExit("M-33.6b Phase-0 gate is BLOCKED")


if __name__ == "__main__":
    main()
