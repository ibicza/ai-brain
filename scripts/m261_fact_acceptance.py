from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.facts.acceptance_v2 import run_m261_acceptance


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the deterministic M-26.1 acceptance pack"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run_m261_acceptance(args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
