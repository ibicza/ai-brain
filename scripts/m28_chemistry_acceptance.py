import argparse
import json
from pathlib import Path

from ai_brain.stage2.domains.chemistry.acceptance import (
    run_acceptance,
    write_acceptance,
)
from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_acceptance(ChemistryDomainService.open(args.root))
    if args.output:
        write_acceptance(report, args.output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
