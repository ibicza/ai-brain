"""Build v3 derivations from already acquired official snapshots."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ai_brain.stage2.domains.chemistry.source_derivation import build_derived_sources


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--ru-policy", type=Path, required=True)
    parser.add_argument("--retrieved-at", default="2026-08-27")
    args = parser.parse_args()
    policy_dir = args.source_root.resolve() / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    target = policy_dir / "ru_element_names_policy_v1.json"
    if args.ru_policy.resolve() != target.resolve():
        shutil.copy2(args.ru_policy.resolve(), target)
    chain = build_derived_sources(args.source_root, retrieved_at=args.retrieved_at)
    print(chain["source_chain_hash"])


if __name__ == "__main__":
    main()
