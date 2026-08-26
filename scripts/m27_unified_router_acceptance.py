from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.router.acceptance import run_m27_acceptance


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run_m27_acceptance(args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
