"""Build and verify the shared M-33.6e portable vault manifest."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336e_identity import (
    build_portable_vault_manifest,
    verify_portable_vault_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh portable vault report already exists")
    manifest = build_portable_vault_manifest(args.vault.resolve(strict=True))
    verify_portable_vault_manifest(args.vault.resolve(strict=True), manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(asdict(manifest)) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
