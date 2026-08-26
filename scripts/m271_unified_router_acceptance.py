from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.router.acceptance_v2 import run_m271_acceptance


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the M-27.1 hardening battery")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run_m271_acceptance(args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
