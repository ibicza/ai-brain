"""Run M-29.1 acceptance and runtime performance evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from ai_brain.stage2.education.acceptance_v2 import run_m291_acceptance
from ai_brain.stage2.education.benchmark_v2 import run_m291_runtime_benchmark
from ai_brain.stage2.education.catalog import EducationalCatalogV2
from ai_brain.stage2.education.service import EducationalService
from ai_brain.stage2.facts.canonical import canonical_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chemistry-root",
        type=Path,
        default=Path("artifacts/domains/chemistry/m29"),
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("artifacts/education/m291/catalog_v2.json"),
    )
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=Path("tests/fixtures/m291_independent_student_errors.jsonl"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--performance-output", type=Path)
    args = parser.parse_args()
    service = EducationalService.open(
        args.chemistry_root, args.store, catalog_path=args.catalog
    )
    result = run_m291_acceptance(service, args.fixtures)
    _write(args.output, result)
    if args.performance_output:
        started = perf_counter()
        loaded = EducationalCatalogV2.load(args.catalog, service.chemistry)
        catalog_load_seconds = perf_counter() - started
        performance = run_m291_runtime_benchmark(service, interaction_count=10_000)
        performance["precompiled_catalog_load_seconds"] = catalog_load_seconds
        performance["precompiled_catalog_entry_count"] = len(loaded.entries)
        _write(
            args.performance_output,
            performance,
        )
    print(
        canonical_json(
            {
                "status": result["status"],
                "output": str(args.output.resolve()),
                "performance_output": (
                    str(args.performance_output.resolve())
                    if args.performance_output
                    else None
                ),
            }
        )
    )


def _write(path: Path, value) -> None:
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
