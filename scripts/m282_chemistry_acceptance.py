from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.domains.chemistry.acceptance_v3 import (
    run_m282_acceptance,
    write_m282_acceptance,
)
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService


def main() -> None:
    parser = argparse.ArgumentParser(description="Run M-28.2 provenance acceptance")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_m282_acceptance(ChemistryDomainService.open(args.root), args.work_dir)
    if args.output:
        write_m282_acceptance(report, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
