"""Create the external post-commit F28 attestation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336k2_protocol import (
    M336K2FreezeManifest,
    M336K2FrozenComponent,
    attest_committed_f28,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument("--freeze-manifest", type=Path, required=True)
    parser.add_argument("--exact-f28-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M336K2 post-F28 attestation output must be fresh")
    value = json.loads(
        args.freeze_manifest.resolve(strict=True).read_text(encoding="utf-8")
    )
    value["components"] = tuple(
        M336K2FrozenComponent(**item) for item in value["components"]
    )
    value["self_reference_safe_exclusions"] = tuple(
        value["self_reference_safe_exclusions"]
    )
    freeze = M336K2FreezeManifest(**value)
    result = attest_committed_f28(
        args.repository,
        args.git_executable,
        freeze_manifest=freeze,
        exact_f28_sha=args.exact_f28_sha,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        canonical_json(asdict(result)) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
