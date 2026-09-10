"""Materialize the typed prospective M-33.6k.2 F28 tree."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336k2_freeze import materialize_m336k2_f28


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.resolve(strict=True).read_text(encoding="utf-8"))
    expected = {
        "repository",
        "git_executable",
        "exact_implementation_tip",
        "exact_q28_sha",
        "readiness",
        "component_sources",
    }
    if not isinstance(request, dict) or set(request) != expected:
        raise ValueError("M336K2 F28 request fields changed")
    result = materialize_m336k2_f28(
        repository=Path(request["repository"]),
        git_executable=Path(request["git_executable"]),
        exact_implementation_tip=request["exact_implementation_tip"],
        exact_q28_sha=request["exact_q28_sha"],
        readiness=Path(request["readiness"]),
        component_sources={
            name: Path(path) for name, path in request["component_sources"].items()
        },
        output=args.output,
    )
    print(canonical_json(asdict(result)))


if __name__ == "__main__":
    main()
