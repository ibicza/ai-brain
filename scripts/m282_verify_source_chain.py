from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_brain.stage2.domains.chemistry.source_derivation import verify_source_chain


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify M-28.2 source chain v3")
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_source_chain(args.source_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
