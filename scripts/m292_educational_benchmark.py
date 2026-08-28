"""Run separated M-29.2 benchmarks and optional offline compilation timing."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from time import perf_counter

from ai_brain.stage2.domains.chemistry.service import ChemistryDomainService
from ai_brain.stage2.education.benchmark_v2 import run_m291_runtime_benchmark
from ai_brain.stage2.education.benchmark_v3 import run_m292_stage_benchmark
from ai_brain.stage2.education.catalog_compiler import compile_catalog_v2
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
        default=Path("artifacts/education/m292/catalog_v3.json"),
    )
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=1_000)
    parser.add_argument("--include-offline-compile", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="m292-benchmark-") as directory:
        root = Path(directory)
        runtime_chemistry = root / "runtime-chemistry"
        shutil.copytree(args.chemistry_root.resolve(), runtime_chemistry)
        service = EducationalService.open(
            runtime_chemistry, args.store, catalog_path=args.catalog
        )
        separated = run_m292_stage_benchmark(service, samples=args.samples)
        identical = run_m291_runtime_benchmark(service, interaction_count=10_000)
        result = {
            "status": "PASS",
            "separated": separated,
            "identical_e7_comparison_benchmark": identical,
            "offline_catalog_compilation": None,
        }
        if args.include_offline_compile:
            chemistry_copy = root / "chemistry"
            shutil.copytree(args.chemistry_root.resolve(), chemistry_copy)
            chemistry = ChemistryDomainService.open(chemistry_copy)
            started = perf_counter()
            compilation = compile_catalog_v2(
                chemistry,
                root / "catalog_v3.json",
                entry_count=2_000,
                audit_path=root / "audit.jsonl",
            )
            result["offline_catalog_compilation"] = {
                **compilation,
                "wall_seconds": perf_counter() - started,
            }
    resolved = args.output.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    print(canonical_json({"status": result["status"], "output": str(resolved)}))


if __name__ == "__main__":
    main()
