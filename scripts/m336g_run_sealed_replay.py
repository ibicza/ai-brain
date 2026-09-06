"""Run one fresh-process M-33.6g sealed-vault production replay."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336g_publication import (
    sealed_java_replay_input_manifest_from_dict,
)
from ai_brain.stage3.acquisition.m336g_replay import (
    run_sealed_java_production_replay,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-pack", type=Path, required=True)
    parser.add_argument("--private-manifest", type=Path, required=True)
    parser.add_argument("--sealed-vault", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("sealed replay public receipt already exists")
    manifest = sealed_java_replay_input_manifest_from_dict(
        json.loads(
            args.private_manifest.resolve(strict=True).read_text(encoding="utf-8")
        )
    )
    receipt = run_sealed_java_production_replay(
        public_pack_root=args.candidate_pack,
        private_manifest=manifest,
        sealed_vault_root=args.sealed_vault,
        javac_executable=args.javac.resolve(strict=True),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(asdict(receipt)) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
