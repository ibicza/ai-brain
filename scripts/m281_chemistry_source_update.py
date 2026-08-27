from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.domains.chemistry.source_update_v2 import (
    run_source_update_matrix,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run M-28.1 source update matrix")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    service = ChemistryDomainService.open(args.root)
    report = run_source_update_matrix(service, args.work_dir)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
