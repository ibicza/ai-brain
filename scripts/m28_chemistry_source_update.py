import argparse
import json
from pathlib import Path

from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.domains.chemistry.source_update import run_source_update_simulation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    report = run_source_update_simulation(
        ChemistryDomainService.open(args.root), args.target
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
