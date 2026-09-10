"""Capture a public, path-free M-33.6k.2 local Python environment manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336k2_execution import (
    build_m336k2_python_environment_manifest,
)
from ai_brain.stage3.acquisition.m336k2_protocol import M336K2ProtocolError


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--python-executable", type=Path, required=True)
    parser.add_argument("--git-executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output.exists() or output.is_relative_to(repository):
        raise M336K2ProtocolError(
            "M336K2 environment output must be fresh and external"
        )
    manifest = build_m336k2_python_environment_manifest(
        repository=repository,
        python_executable=args.python_executable,
        git_executable=args.git_executable,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(canonical_json(manifest) + "\n", encoding="utf-8", newline="\n")
    print(canonical_json(manifest))


if __name__ == "__main__":
    main()
