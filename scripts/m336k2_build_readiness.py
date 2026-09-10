"""Build an exact, public-safe M-33.6k.2 Q28 readiness receipt."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ai_brain.stage2.facts.canonical import canonical_json
from ai_brain.stage3.acquisition.m336k2_readiness import (
    M336K2ReadinessEvidence,
    build_m336k2_readiness,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("M336K2 readiness output must be fresh")
    request = json.loads(args.request.resolve(strict=True).read_text(encoding="utf-8"))
    expected = {
        "repository",
        "git_executable",
        "exact_implementation_tip",
        "evidence",
        "final_destinations",
    }
    if not isinstance(request, dict) or set(request) != expected:
        raise ValueError("M336K2 readiness request fields changed")
    repository = Path(request["repository"]).resolve(strict=True)
    output = args.output.resolve(strict=False)
    if output.is_relative_to(repository):
        raise ValueError("M336K2 readiness output must remain outside Git")
    evidence = tuple(
        M336K2ReadinessEvidence(
            name=name,
            path=Path(binding["path"]),
            hash_field=binding["hash_field"],
            expected_status=binding["expected_status"],
        )
        for name, binding in sorted(request["evidence"].items())
    )
    result = build_m336k2_readiness(
        repository=repository,
        git_executable=Path(request["git_executable"]),
        exact_implementation_tip=request["exact_implementation_tip"],
        evidence=evidence,
        final_destinations={
            name: Path(value) for name, value in request["final_destinations"].items()
        },
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        canonical_json(asdict(result)) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
