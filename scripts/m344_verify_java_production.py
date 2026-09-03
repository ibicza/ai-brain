from __future__ import annotations

import argparse
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.java_production_replay import (
    verify_compiled_java_production_standalone,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack", type=Path)
    args = parser.parse_args()
    print(canonical_json(verify_compiled_java_production_standalone(args.pack)))


if __name__ == "__main__":
    main()
